from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.db import fetch_market_candles, fetch_smc_labels
from app.services.market_memory_engine import record_snapshot
from app.services.scenario_engine import generate_market_scenarios
from app.services.timeframe_hierarchy_engine import generate_timeframe_hierarchy

SUPPORTED_TIMEFRAMES = ["1m", "3m", "5m", "15m", "1H", "4H"]

LABEL_WEIGHTS = {
    "BOS": 1.0,
    "CHOCH": 0.95,
    "LIQUIDITY_SWEEP": 0.85,
    "FVG": 0.7,
}

TIMEFRAME_WEIGHTS = {
    "1m": 1,
    "3m": 2,
    "5m": 3,
    "15m": 5,
    "1H": 8,
    "4H": 13,
}

LOOKBACK_MINUTES = {
    "1m": 240,
    "3m": 360,
    "5m": 720,
    "15m": 2 * 24 * 60,
    "1H": 7 * 24 * 60,
    "4H": 30 * 24 * 60,
}

STRUCTURE_PRIORITY = ("BOS", "CHOCH", "LIQUIDITY_SWEEP", "FVG")
_SNAPSHOT_STORE: dict[tuple[str, str, str], dict[str, Any]] = {}
_SNAPSHOT_LOCK = Lock()


def build_multi_timeframe_snapshot(
    market_type: str,
    instrument: str,
    selected_timeframe: str = "1m",
) -> dict[str, Any]:
    normalized_market = market_type.upper()
    normalized_instrument = instrument.upper()
    normalized_timeframe = _normalize_timeframe(selected_timeframe)

    timeframe_results = {
        timeframe: _build_timeframe_snapshot(
            normalized_market,
            normalized_instrument,
            timeframe,
        )
        for timeframe in SUPPORTED_TIMEFRAMES
    }
    alignment = compute_timeframe_alignment(timeframe_results)
    structure_chain = derive_structure_chain(timeframe_results)
    public_timeframes = {
        timeframe: _public_timeframe_payload(payload)
        for timeframe, payload in timeframe_results.items()
    }
    structure_confidence = _weighted_structure_confidence(public_timeframes)
    snapshot = {
        "market_type": normalized_market,
        "instrument": normalized_instrument,
        "selected_timeframe": normalized_timeframe,
        "timeframes": public_timeframes,
        "structure_chain": structure_chain,
        "lower_timeframe_structure": structure_chain["lower_timeframe_structure"],
        "middle_timeframe_structure": structure_chain["middle_timeframe_structure"],
        "higher_timeframe_structure": structure_chain["higher_timeframe_structure"],
        "regime": compute_market_regime(timeframe_results, alignment, structure_chain),
        "structure_quality": _structure_quality(public_timeframes),
        "structure_confidence": structure_confidence,
        "alignment_score": alignment["alignment_score"],
        "alignment": alignment,
    }
    snapshot["decision"] = derive_decision_state(snapshot)
    snapshot["decision_strength"] = snapshot["decision"]["decision_strength"]
    snapshot["validation_triggers"] = derive_validation_triggers(snapshot)
    snapshot["metrics"] = {
        "structure_confidence": snapshot["structure_confidence"],
        "alignment_score": snapshot["alignment_score"],
        "decision_strength": snapshot["decision_strength"],
    }
    snapshot["narrative"] = generate_market_narrative(snapshot)
    snapshot["executive_summary"] = generate_executive_summary(snapshot)
    snapshot["timeframe_hierarchy"] = generate_timeframe_hierarchy(snapshot)
    snapshot["scenarios"] = generate_market_scenarios(snapshot)
    snapshot["memory"] = _record_market_memory(snapshot)
    previous = _get_previous_snapshot(
        normalized_market,
        normalized_instrument,
        normalized_timeframe,
    )
    snapshot["evolution"] = compare_intelligence_snapshots(previous, snapshot)
    _persist_latest_snapshot(snapshot)
    return snapshot


def _record_market_memory(snapshot: dict[str, Any]) -> dict[str, Any]:
    try:
        result = record_snapshot(snapshot)
        return {
            "status": result.get("status", "unknown"),
            "id": result.get("id"),
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "message": str(exc),
        }


def build_intelligence_evolution(
    market_type: str,
    instrument: str,
    selected_timeframe: str = "1m",
) -> dict[str, Any]:
    snapshot = build_multi_timeframe_snapshot(
        market_type=market_type,
        instrument=instrument,
        selected_timeframe=selected_timeframe,
    )
    return {
        "market_type": snapshot["market_type"],
        "instrument": snapshot["instrument"],
        "selected_timeframe": snapshot["selected_timeframe"],
        "evolution": snapshot["evolution"],
    }


def compare_intelligence_snapshots(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    if not previous:
        return {
            "has_previous": False,
            "summary": "No previous intelligence snapshot available yet.",
            "regime_change": {
                "previous": "",
                "current": current.get("regime", ""),
                "changed": False,
            },
            "decision_change": {
                "previous": "",
                "current": current.get("decision", {}).get("state", ""),
                "changed": False,
            },
            "timeframe_changes": [],
            "confidence_change": {
                "previous": None,
                "current": current.get("structure_confidence", 0),
                "delta": None,
            },
        }

    current_states = _timeframe_state_map(current)
    previous_states = previous.get("timeframe_states", {})
    timeframe_changes = []
    for timeframe in SUPPORTED_TIMEFRAMES:
        previous_state = previous_states.get(timeframe, "")
        current_state = current_states.get(timeframe, "")
        if previous_state != current_state:
            current_payload = current.get("timeframes", {}).get(timeframe, {})
            timeframe_changes.append(
                {
                    "timeframe": timeframe,
                    "previous_state": _title_state(previous_state),
                    "current_state": _title_state(current_state),
                    "driver": current_payload.get("primary_signal", ""),
                }
            )

    previous_confidence = float(previous.get("structure_confidence") or 0)
    current_confidence = float(current.get("structure_confidence") or 0)
    regime_change = {
        "previous": previous.get("market_regime", ""),
        "current": current.get("regime", ""),
        "changed": previous.get("market_regime", "") != current.get("regime", ""),
    }
    decision_change = {
        "previous": previous.get("decision_state", ""),
        "current": current.get("decision", {}).get("state", ""),
        "changed": previous.get("decision_state", "") != current.get("decision", {}).get("state", ""),
    }

    return {
        "has_previous": True,
        "summary": _evolution_summary(
            regime_change,
            decision_change,
            timeframe_changes,
            previous_confidence,
            current_confidence,
            current,
        ),
        "regime_change": regime_change,
        "decision_change": decision_change,
        "timeframe_changes": timeframe_changes,
        "confidence_change": {
            "previous": round(previous_confidence, 2),
            "current": round(current_confidence, 2),
            "delta": round(current_confidence - previous_confidence, 2),
        },
    }


def derive_timeframe_structure(
    labels: list[dict[str, Any]],
    candles: list[dict[str, Any]],
    timeframe: str = "1m",
) -> dict[str, Any]:
    latest_candle = candles[0] if candles else {}
    enriched = [_enriched_label(label, timeframe, latest_candle) for label in labels]
    structural = [
        label for label in enriched if label["family"] in STRUCTURE_PRIORITY
    ]
    if not latest_candle:
        return _empty_structure("INSUFFICIENT", "No candles available for this timeframe.")
    if not structural:
        return _empty_structure("INSUFFICIENT", "No recent structure labels available.")

    primary = _primary_structure_signal(structural)
    primary_side = primary["direction"]
    opposing_side = "BEARISH" if primary_side == "BULLISH" else "BULLISH"
    supporting = [
        label
        for label in structural
        if label["direction"] == primary_side and label["id"] != primary["id"]
    ]
    conflicting = [
        label for label in structural if label["direction"] == opposing_side
    ]

    support_score = sum(label["effective_score"] for label in supporting)
    conflict_score = max(
        (label["effective_score"] for label in conflicting),
        default=0.0,
    )
    primary_score = primary["effective_score"]
    structure_state = _structure_state(primary)
    conflict_ratio = conflict_score / max(primary_score + support_score, 0.01)
    latest_conflict_time = max(
        (_timestamp_sort_key(label.get("timestamp", "")) for label in conflicting),
        default=0.0,
    )
    primary_time = _timestamp_sort_key(primary.get("timestamp", ""))

    if primary_side == "NEUTRAL":
        structure_state = "RANGING"
    elif (
        conflicting
        and latest_conflict_time > primary_time
        and conflict_score >= primary_score * 0.9
    ) or conflict_score >= primary_score * 1.35:
        structure_state = "CONFLICTED"
    elif primary_score < 0.18 and support_score < 0.15:
        structure_state = "INSUFFICIENT"

    reason = _structure_reason(primary, supporting, conflicting, structure_state)
    confidence_breakdown = _structure_confidence_breakdown(
        primary,
        support_score,
        conflict_score,
        latest_candle,
        labels,
        structure_state,
    )
    confidence = confidence_breakdown["final"]

    return {
        "structure": _structure_side(structure_state),
        "structure_state": structure_state,
        "primary_signal": primary["label_type"],
        "primary_signal_time": primary["timestamp"],
        "primary_confidence": primary["confidence"],
        "primary_age": primary["age"],
        "primary_effective_score": round(primary_score, 3),
        "supporting_signals": [_public_signal(label) for label in supporting[:4]],
        "conflicting_signals": [_public_signal(label) for label in conflicting[:4]],
        "conflict_ratio": round(conflict_ratio, 2),
        "confidence": confidence,
        "confidence_breakdown": confidence_breakdown,
        "reason": reason,
    }


def compute_timeframe_alignment(timeframe_results: dict[str, Any]) -> dict[str, Any]:
    bullish_weight = 0.0
    bearish_weight = 0.0
    neutral_weight = 0.0
    aligned_timeframes: list[str] = []
    conflicting_timeframes: list[str] = []

    weighted_confidence_total = 0.0
    weighted_confidence_weight = 0.0
    dominant_confidence_total = 0.0
    dominant_confidence_weight = 0.0

    for timeframe in SUPPORTED_TIMEFRAMES:
        payload = timeframe_results.get(timeframe, {})
        side = _bias_side(payload.get("bias"))
        confidence = float(payload.get("confidence") or 0)
        weight = TIMEFRAME_WEIGHTS[timeframe]
        directional_weight = weight * confidence
        weighted_confidence_total += confidence * weight
        weighted_confidence_weight += weight
        if side == "BULLISH":
            bullish_weight += directional_weight
        elif side == "BEARISH":
            bearish_weight += directional_weight
        else:
            neutral_weight += weight * max(confidence, 0.1)

    dominant_side = _dominant_weighted_side(bullish_weight, bearish_weight)
    for timeframe in SUPPORTED_TIMEFRAMES:
        payload = timeframe_results.get(timeframe, {})
        side = _bias_side(payload.get("bias"))
        if dominant_side != "NEUTRAL" and side == dominant_side:
            aligned_timeframes.append(timeframe)
            dominant_confidence_total += float(payload.get("confidence") or 0) * TIMEFRAME_WEIGHTS[timeframe]
            dominant_confidence_weight += TIMEFRAME_WEIGHTS[timeframe]
        elif dominant_side != "NEUTRAL" and side in {"BULLISH", "BEARISH"}:
            conflicting_timeframes.append(timeframe)

    directional_total = bullish_weight + bearish_weight
    directional_agreement = 0.0
    if directional_total > 0:
        directional_agreement = max(bullish_weight, bearish_weight) / directional_total
    average_confidence = (
        weighted_confidence_total / weighted_confidence_weight
        if weighted_confidence_weight
        else 0.0
    )
    dominant_average_confidence = (
        dominant_confidence_total / dominant_confidence_weight
        if dominant_confidence_weight
        else 0.0
    )
    alignment_score = directional_agreement * dominant_average_confidence

    close_conflict = (
        min(bullish_weight, bearish_weight) / directional_total
        if directional_total > 0
        else 0.0
    )
    higher_side = _dominant_side(
        [timeframe_results.get(tf, {}).get("bias", "NEUTRAL") for tf in ("15m", "1H", "4H")]
    )
    lower_side = _dominant_side(
        [timeframe_results.get(tf, {}).get("bias", "NEUTRAL") for tf in ("1m", "3m", "5m")]
    )
    if (
        higher_side != "NEUTRAL"
        and lower_side != "NEUTRAL"
        and higher_side != lower_side
    ) or close_conflict >= 0.42:
        conflict_level = "HIGH"
    elif close_conflict >= 0.25 or conflicting_timeframes:
        conflict_level = "MEDIUM"
    else:
        conflict_level = "LOW"

    return {
        "bullish_weight": round(bullish_weight, 2),
        "bearish_weight": round(bearish_weight, 2),
        "neutral_weight": round(neutral_weight, 2),
        "score": round(alignment_score, 2),
        "bullish_count": sum(
            1 for result in timeframe_results.values() if _bias_side(result.get("bias")) == "BULLISH"
        ),
        "bearish_count": sum(
            1 for result in timeframe_results.values() if _bias_side(result.get("bias")) == "BEARISH"
        ),
        "neutral_count": sum(
            1 for result in timeframe_results.values() if _bias_side(result.get("bias")) == "NEUTRAL"
        ),
        "dominant_bias": _bias_name(dominant_side, bullish_weight, bearish_weight),
        "alignment_score": round(alignment_score, 2),
        "directional_agreement": round(directional_agreement, 2),
        "average_confidence": round(average_confidence, 2),
        "conflict_level": conflict_level,
        "aligned_timeframes": aligned_timeframes,
        "conflicting_timeframes": conflicting_timeframes,
        "reason": _alignment_reason(
            dominant_side,
            aligned_timeframes,
            conflicting_timeframes,
            alignment_score,
            average_confidence,
        ),
    }


def derive_structure_chain(timeframe_results: dict[str, Any]) -> dict[str, Any]:
    order = ["4H", "1H", "15m", "5m", "3m", "1m"]
    chain = [
        {
            "timeframe": timeframe,
            "state": timeframe_results.get(timeframe, {}).get("structure_state", "INSUFFICIENT"),
        }
        for timeframe in order
    ]
    lower = _group_structure(timeframe_results, ("1m", "3m", "5m"))
    middle = _group_structure(timeframe_results, ("15m", "1H"))
    higher = _group_structure(timeframe_results, ("4H",))

    if higher == "BULLISH" and lower == "BEARISH" and middle == "BEARISH":
        chain_state = "BEARISH_PULLBACK_AGAINST_HTF"
        interpretation = (
            "Higher timeframe remains bullish while lower and middle timeframes "
            "have shifted bearish."
        )
    elif higher == "BEARISH" and lower == "BULLISH" and middle == "BULLISH":
        chain_state = "BULLISH_PULLBACK_AGAINST_HTF"
        interpretation = (
            "Higher timeframe remains bearish while lower and middle timeframes "
            "have shifted bullish."
        )
    elif lower == middle == higher and lower in {"BULLISH", "BEARISH"}:
        chain_state = f"{lower}_CHAIN_ALIGNED"
        interpretation = f"Lower, middle, and higher timeframes align {lower.lower()}."
    elif "INSUFFICIENT" in {lower, middle, higher}:
        chain_state = "INSUFFICIENT_CHAIN"
        interpretation = "One or more timeframe groups lack sufficient structure."
    else:
        chain_state = "CONFLICTED_CHAIN"
        interpretation = (
            f"Lower={lower}, middle={middle}, and higher={higher} are not aligned."
        )

    return {
        "chain": chain,
        "interpretation": interpretation,
        "chain_state": chain_state,
        "lower_timeframe_structure": lower,
        "middle_timeframe_structure": middle,
        "higher_timeframe_structure": higher,
    }


def compute_market_regime(
    timeframe_results: dict[str, Any],
    alignment: dict[str, Any],
    structure_chain: dict[str, Any] | None = None,
) -> str:
    structure_chain = structure_chain or derive_structure_chain(timeframe_results)
    chain_state = structure_chain.get("chain_state", "")
    if chain_state == "BEARISH_PULLBACK_AGAINST_HTF":
        return "BEARISH_PULLBACK"
    if chain_state == "BULLISH_PULLBACK_AGAINST_HTF":
        return "BULLISH_PULLBACK"

    continuation_weight = {"BULLISH": 0.0, "BEARISH": 0.0}
    transition_weight = {"BULLISH": 0.0, "BEARISH": 0.0}
    conflicted_weight = 0.0
    insufficient_weight = 0.0
    for timeframe in SUPPORTED_TIMEFRAMES:
        payload = timeframe_results.get(timeframe, {})
        state = str(payload.get("structure_state", "")).upper()
        side = _structure_side(state)
        weight = TIMEFRAME_WEIGHTS[timeframe] * float(payload.get("confidence") or 0)
        if state.endswith("_CONTINUATION") and side in continuation_weight:
            continuation_weight[side] += weight
        elif state.endswith("_TRANSITION") and side in transition_weight:
            transition_weight[side] += weight
        elif state == "CONFLICTED":
            conflicted_weight += weight
        elif state in {"INSUFFICIENT", "RANGING"}:
            insufficient_weight += TIMEFRAME_WEIGHTS[timeframe] * 0.2

    conflict_level = str(alignment.get("conflict_level", "MEDIUM")).upper()
    dominant_side = _bias_side(alignment.get("dominant_bias"))
    alignment_score = float(alignment.get("alignment_score") or 0)
    transition_total = transition_weight["BULLISH"] + transition_weight["BEARISH"]
    continuation_total = continuation_weight["BULLISH"] + continuation_weight["BEARISH"]
    directional_total = continuation_total + transition_total

    if directional_total <= 0 and insufficient_weight > 0:
        return "INSUFFICIENT"
    if conflict_level == "HIGH" or conflicted_weight > directional_total * 0.45:
        return "CONFLICTED"
    if transition_total >= continuation_total * 0.45 and transition_total > 0.15:
        return "TRANSITIONING"
    if dominant_side == "BULLISH" and alignment_score >= 0.55:
        return "TRENDING_BULLISH"
    if dominant_side == "BEARISH" and alignment_score >= 0.55:
        return "TRENDING_BEARISH"
    if directional_total <= 0.25:
        return "RANGE_BOUND"
    return "TRANSITIONING"


def derive_decision_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    selected_timeframe = snapshot.get("selected_timeframe", "1m")
    timeframes = snapshot.get("timeframes", {})
    alignment = snapshot.get("alignment", {})
    regime = str(snapshot.get("regime", "INSUFFICIENT")).upper()
    selected = timeframes.get(selected_timeframe, {})
    selected_side = _bias_side(selected.get("bias"))
    selected_readiness = selected.get("readiness", "Weak")
    structure_confidence = float(snapshot.get("structure_confidence") or _weighted_structure_confidence(timeframes))
    decision_strength = _decision_strength(timeframes, alignment)
    alignment_score = float(alignment.get("alignment_score") or 0)
    conflict = str(alignment.get("conflict_level", "MEDIUM")).upper()
    adjacent = _adjacent_timeframes(selected_timeframe)
    aligned_adjacent = sum(
        1
        for timeframe in adjacent
        if _bias_side(timeframes.get(timeframe, {}).get("bias")) == selected_side
        and selected_side != "NEUTRAL"
    )
    higher_side = _dominant_side(
        [timeframes.get(tf, {}).get("bias", "NEUTRAL") for tf in ("15m", "1H", "4H")]
    )
    lower_side = _dominant_side(
        [timeframes.get(tf, {}).get("bias", "NEUTRAL") for tf in ("1m", "3m", "5m")]
    )

    freshness_reason = _stale_reason(timeframes)
    if (
        higher_side != "NEUTRAL"
        and lower_side != "NEUTRAL"
        and higher_side != lower_side
    ) or (conflict == "HIGH" and decision_strength >= 0.45):
        state = "CONFLICTED"
        reason = _decision_reason(
            "Lower and higher timeframes disagree or opposing structure remains strong.",
            alignment,
            selected,
            freshness_reason,
        )
        next_validation = "Wait for higher/lower timeframe agreement before validating."
    elif (
        selected_side != "NEUTRAL"
        and aligned_adjacent >= 2
        and alignment_score >= 0.70
        and structure_confidence >= 0.70
        and decision_strength >= 0.70
        and selected_readiness != "Weak"
        and regime in {"TRENDING_BULLISH", "TRENDING_BEARISH"}
    ):
        state = "VALIDATE"
        reason = _decision_reason(
            "Selected timeframe aligns with nearby context and conflict is low.",
            alignment,
            selected,
            freshness_reason,
        )
        next_validation = "Validate on the next candle close without execution guidance."
    elif (
        selected_side != "NEUTRAL"
        and alignment_score >= 0.50
        and structure_confidence >= 0.55
    ):
        state = "WATCH"
        reason = _decision_reason(
            "A dominant side exists, but conflict, session, or confirmation risk remains.",
            alignment,
            selected,
            freshness_reason,
        )
        next_validation = "Wait for 5m/15m confirmation and monitor structure persistence."
    else:
        state = "WAIT"
        reason = _decision_reason(
            "Confidence or alignment is not strong enough for validation.",
            alignment,
            selected,
            freshness_reason,
        )
        if regime in {"BEARISH_PULLBACK", "BULLISH_PULLBACK"}:
            next_validation = (
                "Wait for fresh session candles and check whether 15m/1H confirm "
                "or reject the pullback transition."
            )
        else:
            next_validation = "Wait for fresher structure labels and stronger multi-timeframe alignment."

    return {
        "state": state,
        "confidence": decision_strength,
        "structure_confidence": structure_confidence,
        "alignment_score": alignment_score,
        "decision_strength": decision_strength,
        "reason": reason,
        "next_validation": next_validation,
        "safety": "Advisory-only. No orders. No buy/sell signals.",
    }


def generate_market_narrative(snapshot: dict[str, Any]) -> dict[str, str]:
    timeframes = snapshot.get("timeframes", {})
    alignment = snapshot.get("alignment", {})
    decision = snapshot.get("decision", {})
    regime = str(snapshot.get("regime", "INSUFFICIENT")).replace("_", " ").title()
    dominant_bias = str(alignment.get("dominant_bias", "NEUTRAL")).replace("_", " ").title()
    chain = snapshot.get("structure_chain", {})
    lower_states = _state_counts(timeframes, ("1m", "3m", "5m"))
    higher_states = _state_counts(timeframes, ("15m", "1H", "4H"))
    aligned = alignment.get("aligned_timeframes", [])
    conflicting = alignment.get("conflicting_timeframes", [])
    primary = _primary_structure_line(timeframes)

    lower_context = _context_sentence("Lower timeframes", lower_states)
    higher_context = _context_sentence("Higher timeframes", higher_states)
    chain_state = chain.get("chain_state")
    if chain_state == "BEARISH_PULLBACK_AGAINST_HTF":
        conflict_summary = (
            "Higher timeframe is bullish while lower and middle timeframes are bearish."
        )
    elif chain_state == "BULLISH_PULLBACK_AGAINST_HTF":
        conflict_summary = (
            "Higher timeframe is bearish while lower and middle timeframes are bullish."
        )
    elif conflicting:
        conflict_summary = (
            f"{', '.join(conflicting)} conflict with the dominant structure, while "
            f"{', '.join(aligned) if aligned else 'no lower timeframe cluster'} aligns."
        )
    elif str(snapshot.get("regime", "")).upper() == "CONFLICTED":
        conflict_summary = _conflicted_regime_summary(timeframes)
    else:
        conflict_summary = "No major opposing timeframe cluster is currently dominant."

    if chain.get("chain_state") == "BEARISH_PULLBACK_AGAINST_HTF":
        summary = (
            "Higher timeframe remains bullish, but lower and middle timeframes "
            "have shifted bearish through transition structure. This suggests a "
            "pullback or transition phase rather than confirmed bearish trend continuation."
        )
    elif chain.get("chain_state") == "BULLISH_PULLBACK_AGAINST_HTF":
        summary = (
            "Higher timeframe remains bearish, but lower and middle timeframes "
            "have shifted bullish through transition structure. This suggests a "
            "pullback or transition phase rather than confirmed bullish trend continuation."
        )
    else:
        summary = (
            f"{snapshot.get('instrument', 'Selected market')} is in a {regime.lower()} regime "
            f"with {dominant_bias.lower()} multi-timeframe bias. {primary}"
        )
    decision_rationale = (
        f"{decision.get('state', 'WAIT')} because {decision.get('reason', 'market structure is not sufficiently clear')}"
    )

    return {
        "summary": summary,
        "higher_timeframe_context": higher_context,
        "lower_timeframe_context": lower_context,
        "conflict_summary": conflict_summary,
        "decision_rationale": decision_rationale,
    }


def generate_executive_summary(snapshot: dict[str, Any]) -> str:
    regime = str(snapshot.get("regime", "INSUFFICIENT")).replace("_", " ").lower()
    state = snapshot.get("decision", {}).get("state", "WAIT")
    chain = snapshot.get("structure_chain", {})
    if chain.get("chain_state") == "BEARISH_PULLBACK_AGAINST_HTF":
        return (
            "Market is currently in a bearish pullback within a higher timeframe "
            f"bullish structure. No confirmation exists yet that the pullback has ended "
            f"or that bearish continuation has begun. Recommended state: {state}."
        )
    if chain.get("chain_state") == "BULLISH_PULLBACK_AGAINST_HTF":
        return (
            "Market is currently in a bullish pullback within a higher timeframe "
            f"bearish structure. No confirmation exists yet that the pullback has ended "
            f"or that bullish continuation has begun. Recommended state: {state}."
        )
    return (
        f"Market is currently in a {regime} regime. Structure requires additional "
        f"confirmation before validation. Recommended state: {state}."
    )


def derive_validation_triggers(snapshot: dict[str, Any]) -> dict[str, list[str]]:
    regime = str(snapshot.get("regime", "")).upper()
    stale = bool(_stale_reason(snapshot.get("timeframes", {})))
    bullish_validation = [
        "15m CHOCH_BULLISH appears",
        "1H structure returns to bullish continuation",
        "lower timeframe bearish transition fails",
    ]
    bearish_validation = [
        "4H shifts to bearish transition",
        "15m and 1H align bearish",
        "fresh BOS_BEARISH appears after session opens",
    ]
    if regime == "BULLISH_PULLBACK":
        bullish_validation = [
            "4H shifts to bullish transition",
            "15m and 1H align bullish",
            "fresh BOS_BULLISH appears after session opens",
        ]
        bearish_validation = [
            "15m CHOCH_BEARISH appears",
            "1H returns to bearish continuation",
            "lower timeframe bullish transition fails",
        ]
    wait_conditions = [
        "market remains closed",
        "lower and higher timeframes remain conflicted",
    ]
    if stale:
        wait_conditions.insert(1, "structure remains stale")
    return {
        "bullish_validation": bullish_validation,
        "bearish_validation": bearish_validation,
        "wait_conditions": wait_conditions,
    }


def compact_multi_timeframe_summary(snapshot: dict[str, Any]) -> str:
    narrative = snapshot.get("narrative", {})
    alignment = snapshot.get("alignment", {})
    decision = snapshot.get("decision", {})
    selected = snapshot.get("timeframes", {}).get(snapshot.get("selected_timeframe", "1m"), {})
    breakdown = selected.get("confidence_breakdown", {})
    lines = [
        "Executive Summary:",
        str(snapshot.get("executive_summary", "Executive summary unavailable.")),
        "",
        "Structure Evolution:",
        _evolution_context_line(snapshot.get("evolution", {})),
        "",
        "Structure Chain:",
        *_structure_chain_lines(snapshot.get("structure_chain", {})),
        f"Regime: {str(snapshot.get('regime', 'INSUFFICIENT')).replace('_', ' ').title()}",
        "",
        "Timeframe Hierarchy:",
        *_timeframe_hierarchy_lines(snapshot.get("timeframe_hierarchy", {})),
        "",
        "Market Narrative:",
        str(narrative.get("summary", "Market narrative unavailable.")),
        str(narrative.get("lower_timeframe_context", "")),
        str(narrative.get("higher_timeframe_context", "")),
        str(narrative.get("conflict_summary", "")),
        "",
        f"Structure Quality: {snapshot.get('structure_quality', 'Unknown')}",
        "Confidence Breakdown:",
        f"Primary Signal: {_percent(breakdown.get('primary_signal'))}",
        f"Alignment: {_percent(alignment.get('alignment_score'))}",
        f"Freshness: {_percent(breakdown.get('recency'))}",
        "Metrics:",
        f"Structure Confidence: {_percent(snapshot.get('structure_confidence'))}",
        f"Directional Alignment: {_alignment_label(snapshot.get('alignment_score'))}",
        f"Decision Strength: {_percent(snapshot.get('decision_strength'))}",
        "",
        "Multi-Timeframe Summary:",
    ]
    for timeframe in SUPPORTED_TIMEFRAMES:
        payload = snapshot.get("timeframes", {}).get(timeframe, {})
        signal = _compact_signal(payload.get("top_signal") or {})
        structure_state = str(
            payload.get("structure_state")
            or payload.get("structure")
            or "INSUFFICIENT"
        ).replace("_", " ").title()
        lines.append(
            f"{timeframe:<4} {structure_state:<20} {signal} {_percent(payload.get('confidence'))}"
        )
    lines.extend(
        [
            "Alignment:",
            f"Market Regime: {str(snapshot.get('regime', 'INSUFFICIENT')).title()}",
            f"Dominant Bias: {str(alignment.get('dominant_bias', 'NEUTRAL')).title()}",
            f"Directional Alignment: {_alignment_label(alignment.get('alignment_score'))}",
            f"Conflict Level: {str(alignment.get('conflict_level', 'UNKNOWN')).title()}",
            "Decision:",
            f"State: {decision.get('state', 'WAIT')}",
            f"Decision Strength: {_percent(snapshot.get('decision_strength'))}",
            f"Next Validation: {decision.get('next_validation', 'Wait for confirmation.')}",
            "",
            "Validation Conditions:",
            *_validation_trigger_lines(snapshot.get("validation_triggers", {})),
        ]
    )
    return "\n".join(lines)


def _build_timeframe_snapshot(market_type: str, instrument: str, timeframe: str) -> dict[str, Any]:
    candles = fetch_market_candles(market_type, instrument, timeframe, limit=1)
    latest_candle = candles[0] if candles else {}
    labels = fetch_smc_labels(market_type, instrument, timeframe, limit=20)
    structure = derive_timeframe_structure(labels, candles, timeframe)
    bias = _bias_from_structure(structure)
    confidence = structure["confidence"]

    return {
        "latest_candle": latest_candle,
        "labels": labels,
        "structure": structure["structure"],
        "structure_state": structure["structure_state"],
        "bias": bias,
        "top_signal": _top_signal_payload(structure),
        "primary_signal": structure["primary_signal"],
        "primary_signal_time": structure["primary_signal_time"],
        "primary_confidence": structure["primary_confidence"],
        "supporting_signals": structure["supporting_signals"],
        "conflicting_signals": structure["conflicting_signals"],
        "confidence": confidence,
        "confidence_breakdown": structure["confidence_breakdown"],
        "freshness": _freshness(latest_candle.get("timestamp", "")),
        "readiness": _readiness(latest_candle, labels, confidence),
        "reason": structure["reason"],
        "_side": _bias_side(bias),
    }


def _public_timeframe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "latest_candle": payload.get("latest_candle", {}),
        "labels": payload.get("labels", []),
        "structure": payload.get("structure", "INSUFFICIENT"),
        "structure_state": payload.get("structure_state", payload.get("structure", "INSUFFICIENT")),
        "bias": payload.get("bias", "NEUTRAL"),
        "top_signal": payload.get("top_signal", {}),
        "primary_signal": payload.get("primary_signal", ""),
        "primary_signal_time": payload.get("primary_signal_time", ""),
        "primary_confidence": payload.get("primary_confidence", 0.0),
        "supporting_signals": payload.get("supporting_signals", []),
        "conflicting_signals": payload.get("conflicting_signals", []),
        "confidence": payload.get("confidence", 0.0),
        "confidence_breakdown": payload.get("confidence_breakdown", {}),
        "freshness": payload.get("freshness", "unavailable"),
        "readiness": payload.get("readiness", "Not Ready"),
        "reason": payload.get("reason", ""),
    }


def _empty_structure(structure: str, reason: str) -> dict[str, Any]:
    return {
        "structure": structure,
        "structure_state": structure,
        "primary_signal": "",
        "primary_signal_time": "",
        "primary_confidence": 0.0,
        "primary_age": "",
        "primary_effective_score": 0.0,
        "supporting_signals": [],
        "conflicting_signals": [],
        "conflict_ratio": 0.0,
        "confidence": 0.0,
        "confidence_breakdown": {
            "primary_signal": 0.0,
            "recency": 0.0,
            "supporting_signals": 0.0,
            "data_readiness": 0.0,
            "final": 0.0,
        },
        "reason": reason,
    }


def _enriched_label(
    label: dict[str, Any],
    timeframe: str,
    latest_candle: dict[str, Any],
) -> dict[str, Any]:
    label_type = str(label.get("label_type") or label.get("label") or "").upper()
    label_time = _parse_timestamp(label.get("timestamp", ""))
    candle_time = _parse_timestamp(latest_candle.get("timestamp", ""))
    reference_time = candle_time or datetime.now(timezone.utc)
    age_minutes = _age_minutes(label_time, reference_time)
    recency_weight = _recency_weight(age_minutes, LOOKBACK_MINUTES[timeframe])
    confidence = float(label.get("confidence") or 0)
    weight = _label_weight(label_type)
    direction = _label_direction(label)
    return {
        "id": label.get("id"),
        "label_type": label_type,
        "family": _label_family(label_type),
        "direction": direction,
        "confidence": confidence,
        "timestamp": label.get("timestamp", ""),
        "age_minutes": age_minutes,
        "age": _age_label(age_minutes),
        "recency_weight": recency_weight,
        "label_weight": weight,
        "effective_score": confidence * weight * recency_weight,
        "price_level": label.get("price_level"),
    }


def _primary_structure_signal(labels: list[dict[str, Any]]) -> dict[str, Any]:
    directional_structure = [
        label for label in labels if label["family"] in {"BOS", "CHOCH"}
    ]
    if directional_structure:
        return max(
            directional_structure,
            key=lambda label: (
                _timestamp_sort_key(label.get("timestamp", "")),
                1 if label["family"] == "CHOCH" else 0,
                label["effective_score"],
            ),
        )
    for family in ("LIQUIDITY_SWEEP", "FVG"):
        family_labels = [label for label in labels if label["family"] == family]
        if family_labels:
            return max(
                family_labels,
                key=lambda label: (
                    _timestamp_sort_key(label.get("timestamp", "")),
                    label["effective_score"],
                ),
            )
    return max(labels, key=lambda label: label["effective_score"])


def _structure_reason(
    primary: dict[str, Any],
    supporting: list[dict[str, Any]],
    conflicting: list[dict[str, Any]],
    structure: str,
) -> str:
    primary_label = _friendly_label(primary["label_type"])
    primary_direction = primary["direction"].lower()
    if structure.endswith("_TRANSITION") and conflicting:
        conflict = conflicting[0]
        return (
            f"Latest {primary_direction} {primary_label} overrides earlier "
            f"{_friendly_label(conflict['label_type'])}."
        )
    if structure == "CONFLICTED" and conflicting:
        conflict = conflicting[0]
        return (
            f"Latest {primary_direction} {primary_label} is opposed by "
            f"recent {_friendly_label(conflict['label_type'])}."
        )
    if supporting:
        support = supporting[0]
        return (
            f"Latest {primary_direction} {primary_label} with supporting "
            f"{_friendly_label(support['label_type'])}."
        )
    if conflicting:
        conflict = conflicting[0]
        return (
            f"Latest {primary_direction} {primary_label} overrides earlier "
            f"{_friendly_label(conflict['label_type'])}."
        )
    if structure == "INSUFFICIENT":
        return f"{primary_label} exists but effective score is weak or stale."
    return f"Latest {primary_direction} {primary_label} defines current structure."


def _structure_confidence_breakdown(
    primary: dict[str, Any],
    support_score: float,
    conflict_score: float,
    latest_candle: dict[str, Any],
    labels: list[dict[str, Any]],
    structure: str,
) -> float:
    if structure == "INSUFFICIENT":
        final = round(min(0.34, primary["effective_score"]), 2)
        return {
            "primary_signal": round(min(1.0, primary["effective_score"]), 2),
            "recency": round(primary.get("recency_weight", 0.0), 2),
            "supporting_signals": 0.0,
            "data_readiness": 1.0 if latest_candle and labels else 0.3,
            "final": final,
        }
    primary_signal_score = min(1.0, primary["effective_score"])
    supporting_signal_score = (
        min(1.0, support_score / max(primary["effective_score"], 0.01))
        if support_score > 0
        else 0.0
    )
    recency_score = primary["recency_weight"]
    data_readiness_score = 1.0 if latest_candle and labels else 0.3
    conflict_penalty = min(0.25, conflict_score * 0.18)
    confidence = (
        primary_signal_score * 0.45
        + recency_score * 0.20
        + supporting_signal_score * 0.20
        + data_readiness_score * 0.15
        - conflict_penalty
    )
    return {
        "primary_signal": round(primary_signal_score, 2),
        "recency": round(recency_score, 2),
        "supporting_signals": round(supporting_signal_score, 2),
        "data_readiness": round(data_readiness_score, 2),
        "final": round(_clamp(confidence), 2),
    }


def _bias_from_structure(structure: dict[str, Any]) -> str:
    primary_side = _label_side_from_signal(structure.get("primary_signal", ""))
    structure_state = str(structure.get("structure_state") or structure.get("structure") or "").upper()
    if structure_state in {"INSUFFICIENT", "RANGING"}:
        return "NEUTRAL"
    if structure_state == "CONFLICTED":
        return "CONFLICTED"

    conflict_score = max(
        float(signal.get("effective_score") or 0)
        for signal in structure.get("conflicting_signals", [])
    ) if structure.get("conflicting_signals") else 0.0
    primary_score = float(structure.get("primary_effective_score") or 0)
    confidence = float(structure.get("confidence") or 0)
    if confidence < 0.35:
        return "NEUTRAL"
    if structure_state.endswith("_TRANSITION") or conflict_score >= primary_score * 0.35:
        return f"MIXED_{primary_side}"
    return primary_side


def _top_signal_payload(structure: dict[str, Any]) -> dict[str, Any]:
    if not structure.get("primary_signal"):
        return {}
    return {
        "label": structure.get("primary_signal", ""),
        "label_type": structure.get("primary_signal", ""),
        "direction": _label_side_from_signal(structure.get("primary_signal", "")),
        "confidence": structure.get("primary_confidence", 0.0),
        "effective_confidence": structure.get("confidence", 0.0),
        "timestamp": structure.get("primary_signal_time", ""),
        "age": structure.get("primary_age", ""),
    }


def _public_signal(label: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label.get("label_type", ""),
        "label_type": label.get("label_type", ""),
        "direction": label.get("direction", "NEUTRAL"),
        "confidence": label.get("confidence", 0.0),
        "effective_score": round(label.get("effective_score", 0.0), 3),
        "timestamp": label.get("timestamp", ""),
        "age": label.get("age", ""),
    }


def _readiness(latest_candle: dict[str, Any], labels: list[dict[str, Any]], confidence: float) -> str:
    if not latest_candle:
        return "Not Ready"
    if not labels:
        return "Weak"
    if confidence >= 0.70:
        return "Strong"
    if confidence >= 0.45:
        return "Moderate"
    return "Weak"


def _label_weight(label_type: str) -> float:
    family = _label_family(label_type)
    return LABEL_WEIGHTS.get(family, 0.5)


def _label_family(label_type: str) -> str:
    normalized = str(label_type or "").upper()
    if normalized.startswith("LIQUIDITY_SWEEP"):
        return "LIQUIDITY_SWEEP"
    for prefix in ("BOS", "CHOCH", "FVG"):
        if normalized.startswith(prefix):
            return prefix
    return "OTHER"


def _label_direction(label: dict[str, Any]) -> str:
    direction = str(label.get("direction") or "").upper()
    if direction in {"BULLISH", "BEARISH"}:
        return direction
    return _label_side_from_signal(label.get("label_type") or label.get("label") or "")


def _label_side_from_signal(label_type: str) -> str:
    normalized = str(label_type or "").upper()
    if "BULLISH" in normalized or normalized.endswith("_LOW"):
        return "BULLISH"
    if "BEARISH" in normalized or normalized.endswith("_HIGH"):
        return "BEARISH"
    return "NEUTRAL"


def _structure_state(primary: dict[str, Any]) -> str:
    side = primary.get("direction", "NEUTRAL")
    family = primary.get("family", "OTHER")
    if side not in {"BULLISH", "BEARISH"}:
        return "RANGING"
    if family == "CHOCH":
        return f"{side}_TRANSITION"
    if family == "BOS":
        return f"{side}_CONTINUATION"
    if family in {"LIQUIDITY_SWEEP", "FVG"}:
        return f"{side}_TRANSITION"
    return "INSUFFICIENT"


def _structure_side(structure_state: str) -> str:
    value = str(structure_state or "").upper()
    if "BULLISH" in value:
        return "BULLISH"
    if "BEARISH" in value:
        return "BEARISH"
    if value == "RANGING":
        return "RANGE"
    return value or "INSUFFICIENT"


def _bias_side(bias: str | None) -> str:
    value = str(bias or "").upper()
    if "BULLISH" in value:
        return "BULLISH"
    if "BEARISH" in value:
        return "BEARISH"
    return "NEUTRAL"


def _dominant_weighted_side(bullish_weight: float, bearish_weight: float) -> str:
    total = bullish_weight + bearish_weight
    if total <= 0:
        return "NEUTRAL"
    if abs(bullish_weight - bearish_weight) / total < 0.12:
        return "NEUTRAL"
    return "BULLISH" if bullish_weight > bearish_weight else "BEARISH"


def _dominant_side(biases: list[str]) -> str:
    bullish = sum(1 for bias in biases if _bias_side(bias) == "BULLISH")
    bearish = sum(1 for bias in biases if _bias_side(bias) == "BEARISH")
    if bullish > bearish:
        return "BULLISH"
    if bearish > bullish:
        return "BEARISH"
    return "NEUTRAL"


def _bias_name(side: str, bullish_weight: float, bearish_weight: float) -> str:
    if side == "NEUTRAL":
        return "NEUTRAL"
    opposing = bearish_weight if side == "BULLISH" else bullish_weight
    dominant = bullish_weight if side == "BULLISH" else bearish_weight
    if opposing >= dominant * 0.35:
        return f"MIXED_{side}"
    return side


def _alignment_reason(
    dominant_side: str,
    aligned_timeframes: list[str],
    conflicting_timeframes: list[str],
    alignment_score: float,
    average_confidence: float,
) -> str:
    if dominant_side == "NEUTRAL":
        return "No dominant multi-timeframe side is established."
    aligned = ", ".join(aligned_timeframes) or "no timeframes"
    if average_confidence < 0.45:
        return (
            f"{aligned} lean {dominant_side.lower()}, but average structure "
            f"confidence is weak at {_percent(average_confidence)}."
        )
    if alignment_score < 0.55:
        return (
            f"{aligned} lean {dominant_side.lower()}, but weighted alignment "
            f"is only {_percent(alignment_score)}."
        )
    if conflicting_timeframes:
        conflicts = ", ".join(conflicting_timeframes)
        return f"{aligned} align {dominant_side.lower()} while {conflicts} conflict."
    return f"{aligned} align {dominant_side.lower()} with low opposing conflict."


def _decision_strength(timeframes: dict[str, Any], alignment: dict[str, Any]) -> float:
    weighted_confidence = 0.0
    total_weight = 0.0
    dominant_side = _bias_side(alignment.get("dominant_bias"))
    for timeframe in SUPPORTED_TIMEFRAMES:
        payload = timeframes.get(timeframe, {})
        side = _bias_side(payload.get("bias"))
        confidence = float(payload.get("confidence") or 0)
        if dominant_side != "NEUTRAL" and side == dominant_side:
            weight = TIMEFRAME_WEIGHTS[timeframe]
            weighted_confidence += confidence * weight
            total_weight += weight
    base = weighted_confidence / total_weight if total_weight else 0.0
    alignment_score = float(alignment.get("alignment_score") or 0)
    conflict_penalty = {"LOW": 0.0, "MEDIUM": 0.08, "HIGH": 0.18}.get(
        str(alignment.get("conflict_level", "MEDIUM")).upper(),
        0.08,
    )
    return round(_clamp((base * 0.65) + (alignment_score * 0.35) - conflict_penalty), 2)


def _weighted_structure_confidence(timeframes: dict[str, Any]) -> float:
    weighted = 0.0
    total = 0.0
    for timeframe in SUPPORTED_TIMEFRAMES:
        payload = timeframes.get(timeframe, {})
        weight = TIMEFRAME_WEIGHTS[timeframe]
        weighted += float(payload.get("confidence") or 0) * weight
        total += weight
    return round(weighted / total, 2) if total else 0.0


def _group_structure(timeframe_results: dict[str, Any], timeframes: tuple[str, ...]) -> str:
    scores = {"BULLISH": 0.0, "BEARISH": 0.0}
    has_any = False
    for timeframe in timeframes:
        payload = timeframe_results.get(timeframe, {})
        side = _bias_side(payload.get("bias"))
        if side in scores:
            scores[side] += TIMEFRAME_WEIGHTS[timeframe] * float(payload.get("confidence") or 0)
            has_any = True
    if not has_any:
        return "INSUFFICIENT"
    total = scores["BULLISH"] + scores["BEARISH"]
    if total <= 0:
        return "INSUFFICIENT"
    if abs(scores["BULLISH"] - scores["BEARISH"]) / total < 0.12:
        return "CONFLICTED"
    return "BULLISH" if scores["BULLISH"] > scores["BEARISH"] else "BEARISH"


def _structure_chain_lines(chain: dict[str, Any]) -> list[str]:
    rows = []
    for item in chain.get("chain", []):
        state = str(item.get("state", "INSUFFICIENT")).replace("_", " ").title()
        rows.append(f"{item.get('timeframe', '')} {state}")
    if chain.get("interpretation"):
        rows.append(f"Interpretation: {chain['interpretation']}")
    return rows or ["No structure chain available."]


def _timeframe_hierarchy_lines(hierarchy_payload: dict[str, Any]) -> list[str]:
    hierarchy = hierarchy_payload.get("hierarchy") or {}
    if not hierarchy:
        return ["No timeframe hierarchy available."]
    rows = []
    for timeframe in ("4H", "1H", "15m", "5m", "1m"):
        node = hierarchy.get(timeframe, {})
        relationship = node.get("relationship_to_parent")
        suffix = f" | {relationship}" if relationship else ""
        rows.append(
            f"{timeframe} {node.get('role', '')}: {node.get('state', 'Unknown')} "
            f"({node.get('influence', 'Unknown')}){suffix}"
        )
    rows.extend(
        [
            f"Dominant Context: {hierarchy_payload.get('dominant_context', 'Unknown')}",
            f"Hierarchy Conflict: {hierarchy_payload.get('hierarchy_conflict', 'Unknown')}",
            f"Scenario Bias: {hierarchy_payload.get('scenario_bias', 'Unknown')}",
        ]
    )
    return rows


def _structure_quality(timeframes: dict[str, Any]) -> str:
    confidences = [float(payload.get("confidence") or 0) for payload in timeframes.values()]
    ready_count = sum(
        1 for payload in timeframes.values()
        if payload.get("readiness") in {"Moderate", "Strong"}
    )
    average = sum(confidences) / len(confidences) if confidences else 0.0
    if ready_count >= 4 and average >= 0.65:
        return "Strong"
    if ready_count >= 3 and average >= 0.50:
        return "Moderate"
    if any(confidence >= 0.35 for confidence in confidences):
        return "Weak"
    return "Poor"


def _state_counts(timeframes: dict[str, Any], selected: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for timeframe in selected:
        state = str(
            timeframes.get(timeframe, {}).get("structure_state", "INSUFFICIENT")
        ).replace("_", " ").title()
        counts[state] = counts.get(state, 0) + 1
    return counts


def _context_sentence(label: str, counts: dict[str, int]) -> str:
    if not counts:
        return f"{label} do not have enough current structure evidence."
    dominant_state = max(counts, key=counts.get)
    if counts[dominant_state] == 1 and len(counts) > 1:
        parts = ", ".join(f"{count} {state.lower()}" for state, count in counts.items())
        return f"{label} are mixed: {parts}."
    return f"{label} mainly show {dominant_state.lower()} structure."


def _primary_structure_line(timeframes: dict[str, Any]) -> str:
    best_timeframe = ""
    best_payload: dict[str, Any] = {}
    best_score = -1.0
    for timeframe, payload in timeframes.items():
        score = float(payload.get("confidence") or 0) * TIMEFRAME_WEIGHTS.get(timeframe, 1)
        if score > best_score:
            best_score = score
            best_timeframe = timeframe
            best_payload = payload
    if not best_payload:
        return "Primary structure is not available."
    signal = str(best_payload.get("primary_signal") or "No signal").replace("_", " ").title()
    state = str(best_payload.get("structure_state") or "Insufficient").replace("_", " ").title()
    confidence = int(round(float(best_payload.get("primary_confidence") or 0) * 100))
    return (
        f"Primary Structure: {state}. Primary Driver: {signal} {confidence}% "
        f"on {best_timeframe}."
    )


def _conflicted_regime_summary(timeframes: dict[str, Any]) -> str:
    side_map = {"BULLISH": [], "BEARISH": []}
    for timeframe, payload in timeframes.items():
        side = _bias_side(payload.get("bias"))
        if side in side_map:
            side_map[side].append(timeframe)
    bullish = ", ".join(side_map["BULLISH"])
    bearish = ", ".join(side_map["BEARISH"])
    if bullish and bearish:
        return f"Bearish structure on {bearish} conflicts with bullish structure on {bullish}."
    if bullish:
        return f"Bullish transition exists on {bullish}, but weighted alignment is not broad enough."
    if bearish:
        return f"Bearish transition exists on {bearish}, but weighted alignment is not broad enough."
    return "Structure is conflicted because directional confidence is split or too weak."


def _stale_reason(timeframes: dict[str, Any]) -> str:
    selected_freshness = [
        str(payload.get("freshness", ""))
        for payload in timeframes.values()
        if payload.get("latest_candle")
    ]
    stale_values = [
        freshness for freshness in selected_freshness
        if "d old" in freshness or "unavailable" in freshness or "provider time ahead" in freshness
    ]
    if stale_values and len(stale_values) >= max(1, len(selected_freshness) // 2):
        return f"Latest structure is stale on {len(stale_values)} timeframe(s)."
    return ""


def _decision_reason(
    base_reason: str,
    alignment: dict[str, Any],
    selected: dict[str, Any],
    freshness_reason: str,
) -> str:
    pieces = [base_reason]
    selected_state = str(selected.get("structure_state") or selected.get("structure") or "INSUFFICIENT")
    selected_reason = selected.get("reason")
    if selected_state:
        pieces.append(f"Selected timeframe state is {selected_state.replace('_', ' ').title()}.")
    if selected_reason:
        pieces.append(str(selected_reason))
    if freshness_reason:
        pieces.append(freshness_reason)
    pieces.append(str(alignment.get("reason", "")))
    return " ".join(piece for piece in pieces if piece).strip()


def _adjacent_timeframes(selected_timeframe: str) -> list[str]:
    if selected_timeframe not in SUPPORTED_TIMEFRAMES:
        return ["3m", "5m"]
    index = SUPPORTED_TIMEFRAMES.index(selected_timeframe)
    start = max(0, index - 2)
    end = min(len(SUPPORTED_TIMEFRAMES), index + 3)
    return [tf for tf in SUPPORTED_TIMEFRAMES[start:end] if tf != selected_timeframe]


def _freshness(timestamp: str) -> str:
    elapsed = _elapsed_seconds(timestamp)
    if elapsed is None:
        return "unavailable"
    if elapsed < -60:
        return "provider time ahead"
    if elapsed < 60:
        return "just now"
    if elapsed < 3600:
        return f"{elapsed // 60}m old"
    if elapsed < 86400:
        return f"{elapsed // 3600}h {(elapsed % 3600) // 60}m old"
    return f"{elapsed // 86400}d old"


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp_sort_key(value: Any) -> float:
    parsed = _parse_timestamp(value)
    return parsed.timestamp() if parsed else 0.0


def _elapsed_seconds(timestamp: Any) -> int | None:
    parsed = _parse_timestamp(timestamp)
    if not parsed:
        return None
    return int((datetime.now(timezone.utc) - parsed).total_seconds())


def _age_minutes(label_time: datetime | None, reference_time: datetime) -> float:
    if not label_time:
        return LOOKBACK_MINUTES["1m"]
    return max(0.0, (reference_time - label_time).total_seconds() / 60)


def _recency_weight(age_minutes: float, lookback_minutes: int) -> float:
    return round(max(0.25, 1 - age_minutes / lookback_minutes), 3)


def _age_label(age_minutes: float) -> str:
    if age_minutes < 1:
        return "just now"
    if age_minutes < 60:
        return f"{int(age_minutes)}m"
    if age_minutes < 1440:
        return f"{int(age_minutes // 60)}h {int(age_minutes % 60)}m"
    return f"{int(age_minutes // 1440)}d"


def _signal_age(structure: dict[str, Any]) -> str:
    signals = structure.get("supporting_signals", []) + structure.get("conflicting_signals", [])
    for signal in signals:
        if signal.get("label") == structure.get("primary_signal"):
            return signal.get("age", "")
    return _freshness(structure.get("primary_signal_time", ""))


def _friendly_label(label_type: str) -> str:
    return str(label_type or "structure").replace("_", " ")


def _compact_signal(signal: dict[str, Any]) -> str:
    if not signal:
        return "No recent structure"
    label_type = str(signal.get("label_type") or signal.get("label") or "UNKNOWN")
    arrow = "↑" if signal.get("direction") == "BULLISH" else "↓" if signal.get("direction") == "BEARISH" else "•"
    return f"{label_type} {arrow} {_percent(signal.get('confidence'))}"


def _percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "0%"


def _alignment_label(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    if score >= 0.70:
        return "Strong"
    if score >= 0.40:
        return "Moderate"
    if score > 0:
        return "Weak"
    return "None"


def _validation_trigger_lines(triggers: dict[str, list[str]]) -> list[str]:
    return [
        "Bullish continuation:",
        *[f"- {item}" for item in triggers.get("bullish_validation", [])],
        "Bearish continuation:",
        *[f"- {item}" for item in triggers.get("bearish_validation", [])],
        "Wait if:",
        *[f"- {item}" for item in triggers.get("wait_conditions", [])],
    ]


def _evolution_context_line(evolution: dict[str, Any]) -> str:
    if not evolution.get("has_previous"):
        return "No previous intelligence snapshot available yet."
    regime = evolution.get("regime_change", {})
    decision = evolution.get("decision_change", {})
    changes = evolution.get("timeframe_changes", [])
    lines = [
        f"Previous Regime: {_title_state(regime.get('previous', ''))}",
        f"Current Regime: {_title_state(regime.get('current', ''))}",
        f"Previous Decision: {decision.get('previous', '')}",
        f"Current Decision: {decision.get('current', '')}",
        f"Changes: {evolution.get('summary', '')}",
    ]
    if changes:
        lines.append(
            "Timeframe Changes: "
            + "; ".join(
                f"{item.get('timeframe')} {item.get('previous_state')} to {item.get('current_state')}"
                for item in changes[:3]
            )
        )
    return "\n".join(lines)


def _store_key(market_type: str, instrument: str, selected_timeframe: str) -> tuple[str, str, str]:
    return (market_type.upper(), instrument.upper(), _normalize_timeframe(selected_timeframe))


def _get_previous_snapshot(
    market_type: str,
    instrument: str,
    selected_timeframe: str,
) -> dict[str, Any] | None:
    with _SNAPSHOT_LOCK:
        previous = _SNAPSHOT_STORE.get(_store_key(market_type, instrument, selected_timeframe))
        return dict(previous) if previous else None


def _persist_latest_snapshot(snapshot: dict[str, Any]) -> None:
    payload = {
        "market_type": snapshot.get("market_type", ""),
        "instrument": snapshot.get("instrument", ""),
        "selected_timeframe": snapshot.get("selected_timeframe", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_regime": snapshot.get("regime", ""),
        "decision_state": snapshot.get("decision", {}).get("state", ""),
        "structure_confidence": snapshot.get("structure_confidence", 0),
        "directional_alignment": snapshot.get("alignment_score", 0),
        "structure_chain": snapshot.get("structure_chain", {}),
        "timeframe_states": _timeframe_state_map(snapshot),
    }
    with _SNAPSHOT_LOCK:
        _SNAPSHOT_STORE[
            _store_key(
                str(payload["market_type"]),
                str(payload["instrument"]),
                str(payload["selected_timeframe"]),
            )
        ] = payload


def _timeframe_state_map(snapshot: dict[str, Any]) -> dict[str, str]:
    return {
        timeframe: str(payload.get("structure_state", "INSUFFICIENT"))
        for timeframe, payload in snapshot.get("timeframes", {}).items()
    }


def _title_state(value: str) -> str:
    return str(value or "").replace("_", " ").title()


def _evolution_summary(
    regime_change: dict[str, Any],
    decision_change: dict[str, Any],
    timeframe_changes: list[dict[str, Any]],
    previous_confidence: float,
    current_confidence: float,
    current: dict[str, Any],
) -> str:
    parts = []
    if timeframe_changes:
        changed = timeframe_changes[0]
        parts.append(
            f"{changed['timeframe']} shifted from {changed['previous_state']} "
            f"to {changed['current_state']}."
        )
    else:
        parts.append("No timeframe structure state changed since the previous snapshot.")

    if regime_change.get("changed"):
        parts.append(
            f"Regime changed from {_title_state(regime_change.get('previous'))} "
            f"to {_title_state(regime_change.get('current'))}."
        )
    if decision_change.get("changed"):
        parts.append(
            f"Decision changed from {decision_change.get('previous')} "
            f"to {decision_change.get('current')}."
        )

    delta = current_confidence - previous_confidence
    if abs(delta) >= 0.01:
        direction = "strengthened" if delta > 0 else "weakened"
        parts.append(f"Structure confidence {direction} by {abs(delta):.0%}.")

    if current.get("decision", {}).get("reason"):
        parts.append(current["decision"]["reason"])
    return " ".join(parts)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalize_timeframe(timeframe: str) -> str:
    value = str(timeframe or "1m")
    return value if value in SUPPORTED_TIMEFRAMES else "1m"
