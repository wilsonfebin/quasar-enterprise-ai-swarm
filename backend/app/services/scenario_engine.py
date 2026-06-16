from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SCENARIO_NAMES = {
    "bullish_continuation": "Bullish Continuation",
    "bearish_continuation": "Bearish Continuation",
    "range_continuation": "Range Continuation",
    "bullish_transition": "Bullish Transition",
    "bearish_transition": "Bearish Transition",
    "wait": "Wait / No Clear Scenario",
}

TIMEFRAME_WEIGHTS = {
    "1m": 10,
    "3m": 12,
    "5m": 15,
    "15m": 20,
    "1H": 25,
    "4H": 30,
}


def generate_market_scenarios(market_intelligence: dict[str, Any]) -> dict[str, Any]:
    scores = {
        "bullish_continuation": 1.0,
        "bearish_continuation": 1.0,
        "range_continuation": 1.0,
        "bullish_transition": 1.0,
        "bearish_transition": 1.0,
        "wait": 1.0,
    }
    rationale = {key: [] for key in scores}

    _merge_scores(scores, rationale, _score_timeframe_alignment(market_intelligence))
    _merge_scores(scores, rationale, _score_regime_bias(market_intelligence))
    _merge_scores(scores, rationale, _score_conflict_adjustment(market_intelligence))
    _merge_scores(scores, rationale, _score_freshness_adjustment(market_intelligence))

    probabilities = _normalize_probabilities(scores)
    ranked = sorted(
        probabilities.items(),
        key=lambda item: (-item[1], SCENARIO_NAMES[item[0]]),
    )

    neutral_key = "range_continuation"
    primary_key = ranked[0][0]
    if primary_key == neutral_key:
        primary_key = "wait" if probabilities.get("wait", 0) >= ranked[1][1] else ranked[1][0]
    secondary_key = next(
        key for key, _ in ranked if key not in {primary_key, neutral_key}
    )
    visible_probabilities = _normalize_visible_probabilities(
        probabilities,
        [primary_key, secondary_key, neutral_key],
    )

    scenario_confidence = _scenario_confidence(
        probabilities,
        market_intelligence,
    )

    return {
        "primary_scenario": _scenario_payload(primary_key, visible_probabilities, rationale),
        "secondary_scenario": _scenario_payload(secondary_key, visible_probabilities, rationale),
        "neutral_scenario": _scenario_payload(neutral_key, visible_probabilities, rationale),
        "scenario_confidence": scenario_confidence,
        "validation_conditions": _build_validation_conditions(
            market_intelligence,
            primary_key,
        ),
        "invalidation_conditions": _build_invalidation_conditions(
            market_intelligence,
            primary_key,
        ),
        "safety_status": "ADVISORY_ONLY",
    }


def _score_timeframe_alignment(
    market_intelligence: dict[str, Any],
) -> tuple[dict[str, float], dict[str, list[str]]]:
    states = _timeframe_states(market_intelligence)
    scores = _empty_scores()
    rationale = _empty_rationale()

    bullish_weight = 0.0
    bearish_weight = 0.0
    transition_bullish_weight = 0.0
    transition_bearish_weight = 0.0
    neutral_weight = 0.0
    used_weight = 0.0

    for timeframe, weight in TIMEFRAME_WEIGHTS.items():
        state = _normalize_state(states.get(timeframe, ""))
        if not state:
            continue
        used_weight += weight
        if "BULLISH" in state:
            bullish_weight += weight
            if "TRANSITION" in state:
                transition_bullish_weight += weight
            else:
                scores["bullish_continuation"] += weight * 1.2
        elif "BEARISH" in state:
            bearish_weight += weight
            if "TRANSITION" in state:
                transition_bearish_weight += weight
            else:
                scores["bearish_continuation"] += weight * 1.2
        elif state in {"RANGING", "RANGE", "NEUTRAL", "CONFLICTED"}:
            neutral_weight += weight
            scores["range_continuation"] += weight
            scores["wait"] += weight * 0.8
        else:
            scores["wait"] += weight * 0.6

    scores["bullish_transition"] += transition_bullish_weight * 1.1
    scores["bearish_transition"] += transition_bearish_weight * 1.1

    if bullish_weight > bearish_weight:
        scores["bullish_continuation"] += bullish_weight * 0.35
        rationale["bullish_continuation"].append(
            "Weighted timeframe structure leans bullish."
        )
    elif bearish_weight > bullish_weight:
        scores["bearish_continuation"] += bearish_weight * 0.35
        rationale["bearish_continuation"].append(
            "Weighted timeframe structure leans bearish."
        )

    if transition_bullish_weight > bullish_weight * 0.45:
        rationale["bullish_transition"].append(
            "Bullish transition appears across weighted timeframes."
        )
    if transition_bearish_weight > bearish_weight * 0.45:
        rationale["bearish_transition"].append(
            "Bearish transition appears across weighted timeframes."
        )
    if used_weight and neutral_weight > used_weight * 0.30:
        rationale["range_continuation"].append(
            "Neutral or conflicted timeframe states are material."
        )

    return scores, rationale


def _score_regime_bias(
    market_intelligence: dict[str, Any],
) -> tuple[dict[str, float], dict[str, list[str]]]:
    regime = _regime(market_intelligence)
    higher_side = _higher_timeframe_side(market_intelligence)
    scores = _empty_scores()
    rationale = _empty_rationale()

    if "TRENDING_BULLISH" in regime or "BULLISH_CONTINUATION" in regime:
        scores["bullish_continuation"] += 35
        rationale["bullish_continuation"].append("Market regime is bullish.")
    elif "TRENDING_BEARISH" in regime or "BEARISH_CONTINUATION" in regime:
        scores["bearish_continuation"] += 35
        rationale["bearish_continuation"].append("Market regime is bearish.")
    elif "BULLISH_PULLBACK" in regime:
        if higher_side == "BULLISH":
            scores["bullish_continuation"] += 24
            rationale["bullish_continuation"].append(
                "Pullback is against bullish higher-timeframe structure."
            )
        else:
            scores["bullish_transition"] += 18
            scores["range_continuation"] += 10
            rationale["bullish_transition"].append(
                "Pullback regime needs higher-timeframe stability."
            )
    elif "BEARISH_PULLBACK" in regime:
        if higher_side == "BEARISH":
            scores["bearish_continuation"] += 24
            rationale["bearish_continuation"].append(
                "Pullback is against bearish higher-timeframe structure."
            )
        else:
            scores["bearish_transition"] += 18
            scores["range_continuation"] += 10
            rationale["bearish_transition"].append(
                "Pullback regime needs higher-timeframe stability."
            )
    elif "TRANSITION" in regime:
        scores["bullish_transition"] += 12
        scores["bearish_transition"] += 12
        scores["range_continuation"] += 8
        rationale["range_continuation"].append("Market regime is transitioning.")
    elif "CONFLICT" in regime or "RANGE" in regime:
        scores["range_continuation"] += 28
        scores["wait"] += 18
        rationale["range_continuation"].append(
            "Regime does not show a clean directional state."
        )
    elif "INSUFFICIENT" in regime:
        scores["wait"] += 30
        rationale["wait"].append("Insufficient structure for scenario confidence.")

    return scores, rationale


def _score_conflict_adjustment(
    market_intelligence: dict[str, Any],
) -> tuple[dict[str, float], dict[str, list[str]]]:
    conflict = _conflict_level(market_intelligence)
    scores = _empty_scores()
    rationale = _empty_rationale()

    if conflict == "LOW":
        dominant = _dominant_side(market_intelligence)
        if dominant == "BULLISH":
            scores["bullish_continuation"] += 16
            rationale["bullish_continuation"].append("Conflict level is low.")
        elif dominant == "BEARISH":
            scores["bearish_continuation"] += 16
            rationale["bearish_continuation"].append("Conflict level is low.")
        else:
            scores["range_continuation"] += 8
    elif conflict == "MEDIUM":
        scores["range_continuation"] += 10
        scores["wait"] += 6
        rationale["range_continuation"].append("Conflict level is medium.")
    elif conflict == "HIGH":
        scores["range_continuation"] += 24
        scores["wait"] += 28
        scores["bullish_continuation"] *= 0.65
        scores["bearish_continuation"] *= 0.65
        rationale["wait"].append("High conflict reduces scenario clarity.")
        rationale["range_continuation"].append("High conflict supports range or wait state.")

    return scores, rationale


def _score_freshness_adjustment(
    market_intelligence: dict[str, Any],
) -> tuple[dict[str, float], dict[str, list[str]]]:
    freshness = _freshness_minutes(market_intelligence)
    scores = _empty_scores()
    rationale = _empty_rationale()

    if freshness is None:
        scores["wait"] += 8
        rationale["wait"].append("Freshness is unavailable.")
    elif freshness <= 30:
        dominant = _dominant_side(market_intelligence)
        if dominant == "BULLISH":
            scores["bullish_continuation"] += 8
        elif dominant == "BEARISH":
            scores["bearish_continuation"] += 8
        else:
            scores["range_continuation"] += 6
        rationale[_dominant_rationale_key(dominant)].append(
            "Market intelligence is fresh."
        )
    elif freshness <= 240:
        scores["range_continuation"] += 8
        scores["wait"] += 8
        rationale["range_continuation"].append(
            "Freshness is acceptable but not immediate."
        )
    else:
        scores["range_continuation"] += 30
        scores["wait"] += 36
        scores["bullish_continuation"] *= 0.60
        scores["bearish_continuation"] *= 0.60
        rationale["wait"].append("Stale intelligence reduces scenario clarity.")

    return scores, rationale


def _normalize_probabilities(scores: dict[str, float]) -> dict[str, int]:
    clipped = {key: max(0.0, float(value)) for key, value in scores.items()}
    total = sum(clipped.values())
    if total <= 0:
        return {key: 0 for key in clipped}

    raw = {key: (value / total) * 100 for key, value in clipped.items()}
    rounded = {key: int(value) for key, value in raw.items()}
    remainder = 100 - sum(rounded.values())
    ranking_keys = sorted(
        raw,
        key=lambda key: (raw[key] - rounded[key], raw[key]),
        reverse=True,
    )
    for key in ranking_keys[:remainder]:
        rounded[key] += 1
    return rounded


def _normalize_visible_probabilities(
    probabilities: dict[str, int],
    keys: list[str],
) -> dict[str, int]:
    total = sum(max(0, probabilities.get(key, 0)) for key in keys)
    if total <= 0:
        return {key: 0 for key in keys}
    raw = {key: (max(0, probabilities.get(key, 0)) / total) * 100 for key in keys}
    rounded = {key: int(value) for key, value in raw.items()}
    remainder = 100 - sum(rounded.values())
    ranking_keys = sorted(
        raw,
        key=lambda key: (raw[key] - rounded[key], raw[key]),
        reverse=True,
    )
    for key in ranking_keys[:remainder]:
        rounded[key] += 1
    return rounded


def _build_validation_conditions(
    market_intelligence: dict[str, Any],
    primary_key: str,
) -> list[str]:
    conditions = [
        "15m structure must align with 1H direction",
        "4H regime must remain stable",
        "Conflict level must stay below High",
        "Freshness must remain within acceptable threshold",
    ]
    if "transition" in primary_key:
        conditions.insert(0, "Transition structure must persist across nearby timeframes")
    if primary_key == "wait":
        return [
            "Conflict level must reduce before scenario clarity improves",
            "Freshness must remain within acceptable threshold",
            "Higher and lower timeframes must show clearer agreement",
        ]
    if _conflict_level(market_intelligence) == "HIGH":
        conditions.append("Higher and lower timeframe conflict must reduce")
    return conditions


def _build_invalidation_conditions(
    market_intelligence: dict[str, Any],
    primary_key: str,
) -> list[str]:
    conditions = [
        "Conflict level becomes High",
        "Freshness moves beyond acceptable threshold",
        "4H regime changes against the primary scenario",
    ]
    if "bullish" in primary_key:
        conditions.append("1H and 15m structure shift bearish")
    elif "bearish" in primary_key:
        conditions.append("1H and 15m structure shift bullish")
    elif primary_key == "range_continuation":
        conditions.append("1H and 4H align in the same directional state")
    else:
        conditions.append("Structure remains insufficient across higher timeframes")
    return conditions


def _scenario_payload(
    key: str,
    probabilities: dict[str, int],
    rationale: dict[str, list[str]],
) -> dict[str, Any]:
    return {
        "name": SCENARIO_NAMES[key],
        "probability": probabilities.get(key, 0),
        "rationale": _unique_nonempty(rationale.get(key, []))[:4],
    }


def _scenario_confidence(
    probabilities: dict[str, int],
    market_intelligence: dict[str, Any],
) -> float:
    ranked = sorted(probabilities.values(), reverse=True)
    separation = ((ranked[0] - ranked[1]) / 100) if len(ranked) > 1 else 0
    structure_confidence = _structure_confidence(market_intelligence)
    alignment = _alignment_score(market_intelligence)
    freshness = _freshness_minutes(market_intelligence)
    freshness_factor = 1.0
    if freshness is None:
        freshness_factor = 0.65
    elif freshness > 240:
        freshness_factor = 0.45
    elif freshness > 30:
        freshness_factor = 0.75
    confidence = (
        (structure_confidence * 0.35)
        + (alignment * 0.30)
        + (separation * 0.20)
        + (freshness_factor * 0.15)
    )
    return round(max(0.0, min(1.0, confidence)), 2)


def _merge_scores(
    scores: dict[str, float],
    rationale: dict[str, list[str]],
    scored: tuple[dict[str, float], dict[str, list[str]]],
) -> None:
    score_delta, rationale_delta = scored
    for key, value in score_delta.items():
        if key in scores:
            scores[key] += value
    for key, values in rationale_delta.items():
        if key in rationale:
            rationale[key].extend(values)


def _empty_scores() -> dict[str, float]:
    return {key: 0.0 for key in SCENARIO_NAMES}


def _empty_rationale() -> dict[str, list[str]]:
    return {key: [] for key in SCENARIO_NAMES}


def _timeframe_states(market_intelligence: dict[str, Any]) -> dict[str, str]:
    direct = market_intelligence.get("timeframe_states")
    if isinstance(direct, dict):
        return {str(key): str(value) for key, value in direct.items()}

    states = {}
    for timeframe, payload in (market_intelligence.get("timeframes") or {}).items():
        if isinstance(payload, dict):
            states[str(timeframe)] = str(
                payload.get("structure_state")
                or payload.get("state")
                or payload.get("structure")
                or ""
            )
    return states


def _regime(market_intelligence: dict[str, Any]) -> str:
    return str(
        market_intelligence.get("market_regime")
        or market_intelligence.get("regime")
        or ""
    ).upper()


def _decision_state(market_intelligence: dict[str, Any]) -> str:
    decision = market_intelligence.get("decision")
    if isinstance(decision, dict):
        return str(decision.get("state", "")).upper()
    return str(market_intelligence.get("decision_state", "")).upper()


def _conflict_level(market_intelligence: dict[str, Any]) -> str:
    alignment = market_intelligence.get("alignment") or {}
    return str(
        market_intelligence.get("conflict_level")
        or alignment.get("conflict_level")
        or "MEDIUM"
    ).upper()


def _alignment_score(market_intelligence: dict[str, Any]) -> float:
    alignment = market_intelligence.get("alignment") or {}
    return _coerce_unit(
        market_intelligence.get("directional_alignment")
        or market_intelligence.get("alignment_score")
        or alignment.get("alignment_score")
        or alignment.get("score")
        or 0
    )


def _structure_confidence(market_intelligence: dict[str, Any]) -> float:
    return _coerce_unit(market_intelligence.get("structure_confidence") or 0)


def _freshness_minutes(market_intelligence: dict[str, Any]) -> float | None:
    for key in ("freshness_minutes", "freshness_min"):
        if market_intelligence.get(key) is not None:
            return float(market_intelligence[key])
    if market_intelligence.get("freshness_seconds") is not None:
        return float(market_intelligence["freshness_seconds"]) / 60

    candidates = []
    for payload in (market_intelligence.get("timeframes") or {}).values():
        if not isinstance(payload, dict):
            continue
        candle = payload.get("latest_candle") or {}
        timestamp = candle.get("exchange_candle_time") or candle.get("timestamp")
        parsed = _parse_timestamp(timestamp)
        if parsed:
            candidates.append(parsed)
    if not candidates:
        return None
    latest = max(candidates)
    return max(0.0, (datetime.now(timezone.utc) - latest).total_seconds() / 60)


def _higher_timeframe_side(market_intelligence: dict[str, Any]) -> str:
    states = _timeframe_states(market_intelligence)
    bullish = 0
    bearish = 0
    for timeframe in ("15m", "1H", "4H"):
        state = _normalize_state(states.get(timeframe, ""))
        weight = TIMEFRAME_WEIGHTS.get(timeframe, 0)
        if "BULLISH" in state:
            bullish += weight
        elif "BEARISH" in state:
            bearish += weight
    if bullish > bearish:
        return "BULLISH"
    if bearish > bullish:
        return "BEARISH"
    return "NEUTRAL"


def _dominant_side(market_intelligence: dict[str, Any]) -> str:
    alignment = market_intelligence.get("alignment") or {}
    dominant = str(alignment.get("dominant_bias") or "").upper()
    if "BULLISH" in dominant:
        return "BULLISH"
    if "BEARISH" in dominant:
        return "BEARISH"

    states = _timeframe_states(market_intelligence)
    bullish = 0
    bearish = 0
    for timeframe, weight in TIMEFRAME_WEIGHTS.items():
        state = _normalize_state(states.get(timeframe, ""))
        if "BULLISH" in state:
            bullish += weight
        elif "BEARISH" in state:
            bearish += weight
    if bullish > bearish:
        return "BULLISH"
    if bearish > bullish:
        return "BEARISH"
    return "NEUTRAL"


def _dominant_rationale_key(side: str) -> str:
    if side == "BULLISH":
        return "bullish_continuation"
    if side == "BEARISH":
        return "bearish_continuation"
    return "range_continuation"


def _normalize_state(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_")


def _coerce_unit(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number > 1:
        number = number / 100
    return max(0.0, min(1.0, number))


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _unique_nonempty(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
