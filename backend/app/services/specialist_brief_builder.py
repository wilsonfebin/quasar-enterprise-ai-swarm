from __future__ import annotations

import re
from typing import Any


FORBIDDEN_EXECUTION_TERMS = (
    "buy",
    "sell",
    "entry",
    "exit",
    "target",
    "stop-loss",
    "stop loss",
    "order placement",
    "place order",
)


def build_requirement_brief(context: dict[str, Any]) -> dict[str, Any]:
    intelligence = build_specialist_intelligence_context(context)
    return _with_common_fields(
        {
            "state": "Scope Confirmed",
            "brief": (
                "The review is evaluating whether the selected market is in "
                "continuation, pullback, transition, or unresolved structure."
            ),
            "market_question": (
                "Is the current structure a higher-timeframe continuation, a "
                "lower-timeframe pullback, or a transition requiring validation?"
            ),
            "focus": [
                "selected market only",
                "multi-timeframe structure",
                "advisory-only validation",
            ],
            "next_step": (
                "Proceed to specialist review of regime, evidence quality, and "
                "validation conditions."
            ),
        },
        intelligence,
    )


def build_market_intelligence_brief(context: dict[str, Any]) -> dict[str, Any]:
    intelligence = build_specialist_intelligence_context(context)
    regime = _display_state(intelligence["market_regime"])
    hierarchy = intelligence["timeframe_hierarchy"]
    evolution = intelligence["structure_evolution"]
    primary = intelligence["scenario_engine"].get("primary_scenario") or {}
    secondary = intelligence["scenario_engine"].get("secondary_scenario") or {}
    return _with_common_fields(
        {
            "state": regime,
            "dominant_thesis": _scenario_sentence(primary, regime),
            "alternative_thesis": _alternative_sentence(secondary, hierarchy),
            "supporting_evidence": [
                hierarchy.get("dominant_context") or "Higher timeframe context is unavailable.",
                evolution.get("summary") or "Structure evolution has no prior comparison yet.",
            ],
            "contradicting_evidence": [
                f"Hierarchy conflict is {hierarchy.get('hierarchy_conflict', 'Unknown')}.",
                f"Directional alignment is {intelligence['directional_alignment']}.",
            ],
            "next_validation": intelligence["next_validation"],
        },
        intelligence,
    )


def build_system_readiness_brief(context: dict[str, Any]) -> dict[str, Any]:
    intelligence = build_specialist_intelligence_context(context)
    freshness = intelligence["freshness"].get("data_age") or "unknown"
    session = intelligence["session"] or "Unknown"
    source = intelligence["source"] or "unknown"
    evidence_quality = _evidence_quality(intelligence)
    state = "Ready"
    if "closed" in session.lower() or "off" in session.lower():
        state = "Closed Session"
    elif evidence_quality != "Usable":
        state = "Degraded"
    return _with_common_fields(
        {
            "state": state,
            "freshness": freshness,
            "session": session,
            "data_source": source,
            "evidence_quality": evidence_quality,
            "readiness_summary": (
                "Data is suitable for advisory review when freshness, session, "
                "scenario output, hierarchy output, and governance evidence remain available."
            ),
            "next_step": "Continue monitoring freshness and source availability.",
        },
        intelligence,
    )


def build_risk_governance_brief(context: dict[str, Any]) -> dict[str, Any]:
    intelligence = build_specialist_intelligence_context(context)
    risk_level = _risk_level(intelligence)
    return _with_common_fields(
        {
            "state": "Guardrails Active",
            "risk_level": risk_level,
            "risk_reason": _risk_reason(intelligence),
            "confidence_risk": (
                f"Structure confidence is {intelligence['structure_confidence']}%, so "
                "the thesis should remain unconfirmed until validation evidence improves."
            ),
            "invalidation_risk": (
                "If higher-timeframe support weakens or hierarchy conflict increases, "
                "the current dominant thesis becomes less reliable."
            ),
            "next_step": (
                "Require timeframe agreement and fresh evidence before upgrading the "
                "decision state."
            ),
        },
        intelligence,
    )


def build_delivery_planning_brief(context: dict[str, Any]) -> dict[str, Any]:
    intelligence = build_specialist_intelligence_context(context)
    triggers = intelligence["validation_conditions"]
    return _with_common_fields(
        {
            "state": "Validation Plan",
            "primary_watch_condition": _primary_watch_condition(intelligence),
            "bullish_continuation_conditions": _conditions(
                triggers.get("bullish_validation"),
                [
                    "15m structure realigns with 1H",
                    "higher timeframe regime remains stable",
                    "lower timeframe corrective pressure fades",
                ],
            ),
            "bearish_continuation_conditions": _conditions(
                triggers.get("bearish_validation"),
                [
                    "1H shifts bearish",
                    "4H support weakens",
                    "fresh bearish structure appears after session continuation",
                ],
            ),
            "wait_conditions": _conditions(
                triggers.get("wait_conditions"),
                [
                    "timeframes remain conflicted",
                    "freshness degrades",
                    "market session becomes inactive",
                ],
            ),
            "next_step": intelligence["next_validation"],
        },
        intelligence,
    )


def build_final_review_brief(context: dict[str, Any]) -> dict[str, Any]:
    intelligence = build_specialist_intelligence_context(context)
    primary = intelligence["scenario_engine"].get("primary_scenario") or {}
    secondary = intelligence["scenario_engine"].get("secondary_scenario") or {}
    state = intelligence["decision_state"] or "WAIT"
    return _with_common_fields(
        {
            "state": state,
            "executive_summary": _executive_summary(intelligence),
            "dominant_hypothesis": _scenario_title(primary),
            "alternative_hypothesis": _scenario_title(secondary),
            "why_not_confirmed": _why_not_confirmed(intelligence),
            "decision_support": (
                "Monitor validation conditions rather than treating the current "
                "state as confirmed."
            ),
            "next_validation": intelligence["next_validation"],
        },
        intelligence,
    )


def build_specialist_brief(agent_name: str, context: dict[str, Any]) -> dict[str, Any]:
    builders = {
        "Requirement Agent": build_requirement_brief,
        "Market Intelligence Agent": build_market_intelligence_brief,
        "Architecture Agent": build_system_readiness_brief,
        "Risk Governance Agent": build_risk_governance_brief,
        "Delivery Planning Agent": build_delivery_planning_brief,
        "Final Review Agent": build_final_review_brief,
    }
    return builders.get(agent_name, build_requirement_brief)(context)


def build_specialist_intelligence_context(context: dict[str, Any]) -> dict[str, Any]:
    mtf = context.get("multi_timeframe") or {}
    selected_market = _selected_market_context(context)
    alignment = mtf.get("alignment") or {}
    decision = mtf.get("decision") or {}
    metrics = mtf.get("metrics") or {}
    scenario_engine = mtf.get("scenarios") or {}
    validation_conditions = mtf.get("validation_triggers") or {}
    structure_confidence = _percent_int(
        metrics.get("structure_confidence", mtf.get("structure_confidence"))
    )
    return {
        "market_regime": mtf.get("regime") or "INSUFFICIENT",
        "decision_state": decision.get("state") or "WAIT",
        "structure_confidence": structure_confidence,
        "directional_alignment": _alignment_label(
            metrics.get("alignment_score", alignment.get("alignment_score"))
        ),
        "conflict_level": alignment.get("conflict_level") or "Unknown",
        "scenario_engine": scenario_engine,
        "timeframe_hierarchy": mtf.get("timeframe_hierarchy") or {},
        "structure_evolution": mtf.get("evolution") or {},
        "market_memory": mtf.get("memory") or {},
        "validation_conditions": validation_conditions,
        "next_validation": decision.get("next_validation") or _fallback_next_validation(validation_conditions),
        "freshness": {"data_age": selected_market.get("data_age") or "unknown"},
        "session": selected_market.get("session") or "Unknown",
        "source": selected_market.get("source") or "unknown",
        "supporting_signals": _supporting_signals(selected_market.get("labels") or []),
        "safety_mode": "ADVISORY_ONLY",
    }


def format_specialist_brief_text(brief: dict[str, Any]) -> str:
    lines = []
    for key, label in (
        ("state", "State"),
        ("brief", "Brief"),
        ("market_question", "Market Question"),
        ("dominant_thesis", "Dominant Thesis"),
        ("alternative_thesis", "Alternative Thesis"),
        ("risk_reason", "Risk Reason"),
        ("confidence_risk", "Confidence Risk"),
        ("invalidation_risk", "Invalidation Risk"),
        ("executive_summary", "Executive Summary"),
        ("dominant_hypothesis", "Dominant Hypothesis"),
        ("alternative_hypothesis", "Alternative Hypothesis"),
        ("why_not_confirmed", "Why Not Confirmed"),
        ("decision_support", "Decision Support"),
        ("readiness_summary", "Readiness Summary"),
        ("primary_watch_condition", "Primary Watch Condition"),
        ("next_validation", "Next Validation"),
        ("next_step", "Next Step"),
    ):
        if brief.get(key):
            lines.append(f"{label}: {brief[key]}")
    for key, label in (
        ("focus", "Focus"),
        ("supporting_evidence", "Supporting Evidence"),
        ("contradicting_evidence", "Contradicting Evidence"),
        ("bullish_continuation_conditions", "Bullish Continuation Conditions"),
        ("bearish_continuation_conditions", "Bearish Continuation Conditions"),
        ("wait_conditions", "Wait Conditions"),
        ("supporting_signals", "Supporting Signals"),
    ):
        values = brief.get(key) or []
        if values:
            lines.append(f"{label}:")
            lines.extend(f"- {item}" for item in values[:3])
    lines.append("Safety Mode: ADVISORY_ONLY")
    return "\n".join(_scrub_forbidden_terms(line) for line in lines)


def is_raw_label_repetition(response_text: str) -> bool:
    text = str(response_text or "")
    if not text.strip():
        return True
    raw_count = len(re.findall(r"\b(?:BOS|CHOCH|FVG)_[A-Z_]+\b", text.upper()))
    intelligence_terms = (
        "thesis",
        "hypothesis",
        "regime",
        "hierarchy",
        "persistence",
        "validation",
        "readiness",
        "risk",
        "scenario",
    )
    has_intelligence = any(term in text.lower() for term in intelligence_terms)
    return (raw_count >= 2 and not has_intelligence) or (raw_count >= 3 and len(text) < 500)


def _with_common_fields(brief: dict[str, Any], intelligence: dict[str, Any]) -> dict[str, Any]:
    return {
        **brief,
        "market_regime": _display_state(intelligence["market_regime"]),
        "decision_state": intelligence["decision_state"],
        "structure_confidence": intelligence["structure_confidence"],
        "directional_alignment": intelligence["directional_alignment"],
        "conflict_level": intelligence["conflict_level"],
        "validation_conditions": intelligence["validation_conditions"],
        "next_validation": brief.get("next_validation") or brief.get("next_step") or intelligence["next_validation"],
        "supporting_signals": intelligence["supporting_signals"][:3],
        "safety_mode": "ADVISORY_ONLY",
    }


def _selected_market_context(context: dict[str, Any]) -> dict[str, Any]:
    scope = str(context.get("analysis_scope") or "MCX").upper()
    return context.get("forex", {}) if scope in {"FOREX", "FX", "XAUUSD"} else context.get("mcx", {})


def _supporting_signals(labels: list[dict[str, Any]]) -> list[str]:
    signals = []
    for label in labels[:3]:
        name = label.get("label") or label.get("label_type") or "Structure signal"
        confidence = _percent_int(label.get("confidence"))
        signals.append(f"{str(name).replace('_', ' ').title()} {confidence}%")
    return signals


def _conditions(values: Any, fallback: list[str]) -> list[str]:
    if isinstance(values, list) and values:
        return [str(item) for item in values[:3]]
    return fallback


def _fallback_next_validation(triggers: dict[str, Any]) -> str:
    wait_conditions = triggers.get("wait_conditions") or []
    if wait_conditions:
        return str(wait_conditions[0])
    return "Recheck after fresh multi-timeframe evidence updates."


def _display_state(value: Any) -> str:
    return str(value or "Unknown").replace("_", " ").title()


def _percent_int(value: Any) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if number <= 1:
        number *= 100
    return max(0, min(100, int(round(number))))


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
    return "Unknown"


def _scenario_title(scenario: dict[str, Any]) -> str:
    name = str(scenario.get("name") or "Wait / No Clear Scenario")
    probability = scenario.get("probability")
    return f"{name} ({probability}%)" if probability is not None else name


def _scenario_sentence(scenario: dict[str, Any], regime: str) -> str:
    title = _scenario_title(scenario)
    return f"{title} is the leading scenario while the market regime is {regime}."


def _alternative_sentence(scenario: dict[str, Any], hierarchy: dict[str, Any]) -> str:
    title = _scenario_title(scenario)
    conflict = hierarchy.get("hierarchy_conflict") or "Unknown"
    return f"{title} becomes more relevant if hierarchy conflict remains {conflict} or deteriorates."


def _evidence_quality(intelligence: dict[str, Any]) -> str:
    if not intelligence["scenario_engine"] or not intelligence["timeframe_hierarchy"]:
        return "Degraded"
    if intelligence["freshness"].get("data_age") in {"unknown", ""}:
        return "Degraded"
    return "Usable"


def _risk_level(intelligence: dict[str, Any]) -> str:
    confidence = int(intelligence["structure_confidence"])
    conflict = str(intelligence["conflict_level"]).lower()
    if confidence < 45 or "high" in conflict:
        return "High"
    if confidence < 70 or "medium" in conflict:
        return "Medium"
    return "Low"


def _risk_reason(intelligence: dict[str, Any]) -> str:
    return (
        f"Hierarchy conflict is {intelligence['conflict_level']} and directional "
        f"alignment is {intelligence['directional_alignment']}."
    )


def _primary_watch_condition(intelligence: dict[str, Any]) -> str:
    hierarchy = intelligence["timeframe_hierarchy"]
    return hierarchy.get("scenario_bias") or "15m and 1H alignment"


def _executive_summary(intelligence: dict[str, Any]) -> str:
    regime = _display_state(intelligence["market_regime"]).lower()
    return (
        f"Market is currently in a {regime} state. The current decision state "
        "should remain tied to hierarchy, persistence, and validation evidence."
    )


def _why_not_confirmed(intelligence: dict[str, Any]) -> str:
    return (
        f"Directional alignment is {intelligence['directional_alignment']} and "
        f"conflict level is {intelligence['conflict_level']}; confirmation requires "
        "fresh multi-timeframe agreement."
    )


def _scrub_forbidden_terms(text: str) -> str:
    scrubbed = text
    replacements = {
        "buy": "bullish",
        "sell": "bearish",
        "entry": "trigger",
        "exit": "invalidating change",
        "target": "objective",
        "stop-loss": "risk boundary",
        "stop loss": "risk boundary",
        "order placement": "workflow action",
        "place order": "take workflow action",
    }
    for term, replacement in replacements.items():
        scrubbed = re.sub(rf"\b{re.escape(term)}\b", replacement, scrubbed, flags=re.IGNORECASE)
    return scrubbed
