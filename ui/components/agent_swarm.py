import html
import re
import time
from datetime import datetime

import streamlit as st

from api_client import (
    market_candles,
    multi_timeframe_intelligence,
    reset_workflow,
    smc_labels,
    start_workflow_thread,
    workflow_details as fetch_workflow_details,
    workflow_status as fetch_workflow_status,
)
from utils.formatting import (
    confidence_label,
    display_scope_label,
    extract_line_value,
    extract_section_lines,
    format_freshness,
    market_session_text,
)

def clean_agent_output(text: str) -> str:
    prefixes = [
        "Requirement Agent response:",
        "Market Intelligence Agent response:",
        "Architecture Agent response:",
        "System Readiness Agent response:",
        "Risk Governance Agent response:",
        "Delivery Planning Agent response:",
        "Final Review Agent response:",
    ]
    cleaned = str(text or "").strip()
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :].strip()
    return cleaned


def short_time(timestamp: str) -> str:
    if not timestamp:
        return "—"
    try:
        return datetime.fromisoformat(timestamp).strftime("%H:%M:%S")
    except ValueError:
        return timestamp[:8] or "—"


def parse_prompt_context(prompt: str) -> dict[str, object]:
    context = {
        "scope": extract_line_value(prompt, "Scope") or extract_line_value(prompt, "Selected scope"),
        "timeframe": extract_line_value(prompt, "Timeframe") or "1m",
        "candle": extract_line_value(prompt, "Candle"),
        "bias": extract_line_value(prompt, "Dominant Bias") or "Neutral",
        "session": extract_line_value(prompt, "Session"),
        "data_age": extract_line_value(prompt, "Data Age"),
        "source": extract_line_value(prompt, "Source"),
        "labels": [],
    }
    labels = extract_section_lines(
        prompt,
        "Supporting Signals",
        ["Dominant Bias", "Session", "Data Age", "Source", "Safety"],
    )
    if not labels:
        labels = extract_section_lines(
            prompt,
            "Top Labels",
            ["Dominant Bias", "Session", "Data Age", "Source", "Safety"],
        )
    context["labels"] = labels[:3]
    return context


def final_decision_data(workflow_details: dict, selected_scope: str) -> dict[str, object]:
    summary = workflow_details.get("final_summary", "")
    steps = workflow_details.get("steps", [])
    final_step = next(
        (step for step in steps if step.get("agent") == "Final Review Agent"),
        {},
    )
    prompt_context = parse_prompt_context(final_step.get("prompt_sent", ""))
    final_brief = (
        final_step.get("specialist_brief")
        if isinstance(final_step.get("specialist_brief"), dict)
        else {}
    )
    final_response_text = clean_agent_output(final_step.get("response_text", ""))
    scope = (
        prompt_context.get("scope")
        or workflow_details.get("analysis_scope")
        or selected_scope
    )
    decision_state = brief_value(final_brief, "state", "decision_state") or extract_line_value(summary, "Decision State") or (
        "Waiting" if workflow_details.get("status") == "waiting" else "WATCH"
    )
    executive_summary = (
        brief_value(final_brief, "executive_summary", "brief")
        or extract_line_value(final_response_text, "Executive Summary")
        or extract_line_value(summary, "Executive Assessment")
        or extract_line_value(summary, "Executive Summary")
    )
    dominant_hypothesis = brief_value(final_brief, "dominant_hypothesis") or extract_line_value(final_response_text, "Dominant Hypothesis") or extract_line_value(summary, "Dominant Hypothesis")
    alternative_hypothesis = brief_value(final_brief, "alternative_hypothesis") or extract_line_value(final_response_text, "Alternative Hypothesis") or extract_line_value(summary, "Alternative Hypothesis")
    why_not_confirmed = brief_value(final_brief, "why_not_confirmed") or extract_line_value(final_response_text, "Why Not Confirmed") or extract_line_value(summary, "Why Not Confirmed")
    evidence = extract_section_lines(
        summary,
        "Intelligence Evidence",
        ["Confidence", "Next Validation", "Specialist Notes", "Safety"],
    )
    if not evidence:
        evidence = extract_section_lines(
            summary,
            "Evidence",
            ["Confidence", "Next Validation", "Specialist Notes", "Safety"],
        )
    if not evidence:
        evidence = list(prompt_context.get("labels", []))
    next_validation = extract_line_value(summary, "Next Validation")
    if not next_validation:
        next_lines = extract_section_lines(summary, "Next Validation", ["Specialist Notes", "Safety"])
        next_validation = (
            next_lines[0]
            if next_lines
            else "Review fresh multi-timeframe confirmation before changing the advisory state."
        )
    return {
        "scope": display_scope_label(str(scope), selected_scope),
        "decision_state": decision_state,
        "market_regime": extract_line_value(summary, "Market Regime"),
        "structure_confidence": "",
        "confidence": confidence_label(summary),
        "evidence": evidence[:3],
        "next_validation": next_validation,
        "safety": "Advisory-only market intelligence.",
        "executive_summary": executive_summary,
        "dominant_hypothesis": dominant_hypothesis,
        "alternative_hypothesis": alternative_hypothesis,
        "why_not_confirmed": why_not_confirmed,
        "final_review_brief": final_brief,
    }


def brief_value(brief: dict, *keys: str) -> str:
    for key in keys:
        value = brief.get(key)
        if value:
            return str(value)
    return ""


def brief_list(brief: dict, *keys: str) -> list[str]:
    for key in keys:
        value = brief.get(key)
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if value:
            return [str(value)]
    return []


def final_review_completed(steps: list[dict]) -> bool:
    return any(
        step.get("agent") == "Final Review Agent" and step.get("status") == "completed"
        for step in steps
    )


def sanitize_advisory_text(value: object) -> str:
    text = str(value or "").strip()
    if not text or text in {"None", "null"}:
        return ""
    replacements = [
        (
            "duplicate_skipped",
            "No material structure change detected since the previous review.",
        ),
        (
            "Latest bullish CHOCH BULLISH overrides earlier FVG BEARISH",
            "Recent bullish structure partially offsets earlier bearish pressure.",
        ),
        (
            "3m, 5m, 15m, 1H, 4H lean bearish, but weighted alignment is only 52%",
            "Several timeframes lean bearish, but weighted alignment remains too weak to treat the thesis as confirmed.",
        ),
        (
            "Selected timeframe state is Bullish Transition",
            "The selected timeframe shows a bullish transition, while broader alignment remains mixed.",
        ),
        ("Waiting for Band analysis.", "Specialist review completed."),
        ("Waiting for Band analysis", "Specialist review completed."),
        (
            "No previous intelligence snapshot available yet.",
            "No prior reviewed intelligence state is available yet.",
        ),
        ("snapshot", "review"),
        ("payload", "evidence"),
        ("backend", "system"),
        (" raw ", " evidence "),
        (" raw", " evidence"),
        ("raw ", "evidence "),
        ("null", "unavailable"),
        ("None", "Unavailable"),
        ("CHOCH BULLISH", "recent bullish structure"),
        ("CHOCH_BULLISH", "recent bullish structure"),
        ("FVG BEARISH", "earlier bearish pressure"),
        ("FVG_BEARISH", "earlier bearish pressure"),
        ("BOS BULLISH confidence", "bullish structure confidence"),
        ("BOS BEARISH confidence", "bearish structure confidence"),
        ("BOS_BULLISH confidence", "bullish structure confidence"),
        ("BOS_BEARISH confidence", "bearish structure confidence"),
        ("duplicate skipped", "No material structure change detected since the previous review."),
    ]
    for source, target in replacements:
        text = text.replace(source, target)
    text = text.replace("overrides", "partially offsets")
    text = text.replace("override", "partially offset")
    return " ".join(text.split())


def sanitize_advisory_list(values: object) -> list[str]:
    if not isinstance(values, list):
        values = [values] if values else []
    cleaned = []
    for value in values:
        item = sanitize_advisory_text(value)
        if item:
            cleaned.append(item)
    return cleaned


def clipped_advisory_text(value: object, max_chars: int) -> str:
    text = sanitize_advisory_text(value)
    if len(text) <= max_chars:
        return text
    clipped = text[: max_chars - 1].rsplit(" ", 1)[0].strip()
    return f"{clipped}."


def sync_specialist_workflow_gate(workflow: dict, detail_steps: list[dict], current_state: str) -> dict[str, object]:
    completed = int(
        workflow.get("completed_specialists")
        or workflow.get("completed_count")
        or sum(1 for step in detail_steps if step.get("status") == "completed")
    )
    total = int(workflow.get("total_specialists") or workflow.get("total_count") or len(detail_steps) or 6)
    final_done = bool(workflow.get("final_review_completed")) or final_review_completed(detail_steps)
    backend_running = bool(workflow.get("specialist_workflow_running") or workflow.get("running"))
    running = backend_running or str(current_state).lower() == "running"

    if st.session_state.get("specialist_workflow_running") or running:
        st.session_state["completed_specialists"] = completed
        st.session_state["total_specialists"] = total
        st.session_state["final_review_completed"] = final_done
        if workflow.get("workflow_run_id") or workflow.get("workflow_id"):
            st.session_state["workflow_run_id"] = workflow.get("workflow_run_id") or workflow.get("workflow_id")

    if final_done:
        st.session_state["final_review_completed"] = True
        st.session_state["quasar_workflow_running"] = False
        st.session_state["specialist_workflow_running"] = False
        st.session_state["specialist_summary_locked"] = False
    elif running or st.session_state.get("specialist_workflow_running"):
        st.session_state["specialist_workflow_running"] = True
        st.session_state["specialist_summary_locked"] = True
    elif str(current_state).lower() == "failed":
        st.session_state["quasar_workflow_running"] = False
        st.session_state["specialist_workflow_running"] = False
        st.session_state["specialist_summary_locked"] = False

    return {
        "running": bool(st.session_state.get("specialist_workflow_running")),
        "completed": int(st.session_state.get("completed_specialists", completed)),
        "total": int(st.session_state.get("total_specialists", total)),
        "final_review_completed": bool(st.session_state.get("final_review_completed", final_done)),
        "summary_locked": bool(st.session_state.get("specialist_summary_locked")),
    }


def gated_specialist_steps(
    steps: list[dict],
    gate: dict[str, object],
) -> list[dict]:
    if not gate.get("summary_locked") or gate.get("final_review_completed"):
        return steps
    completed = int(gate.get("completed") or 0)
    gated_steps = []
    for index, step in enumerate(steps):
        gated_step = dict(step)
        if index < completed:
            gated_step["status"] = "completed"
        elif index == completed:
            gated_step["status"] = "running"
        else:
            gated_step["status"] = "waiting"
        gated_steps.append(gated_step)
    return gated_steps


def apply_specialist_summary_gate(decision: dict[str, object], gate: dict[str, object]) -> dict[str, object]:
    if gate.get("summary_locked") and not gate.get("final_review_completed"):
        return {
            **decision,
            "decision_state": "ANALYZING",
            "market_regime": "PENDING REVIEW",
            "structure_confidence": "PENDING",
        }
    return decision


def rerun_agent_monitor() -> None:
    try:
        st.rerun(scope="fragment")
    except st.errors.StreamlitAPIException:
        st.rerun()


def reset_specialist_analysis_request() -> None:
    st.session_state["specialist_analysis_requested"] = False
    st.session_state["specialist_analysis_requested_v2"] = False
    st.session_state["specialist_analysis_requested_v3"] = False
    st.session_state["final_review_completed"] = False
    st.session_state["specialist_workflow_running"] = False
    st.session_state["specialist_summary_locked"] = False
    st.session_state["completed_specialists"] = 0


def start_specialist_analysis(analysis_scope: str, workflow_run_id: str) -> None:
    if (
        st.session_state.get("quasar_workflow_running")
        and not st.session_state.get("final_review_completed")
    ):
        return
    reset_workflow()
    st.session_state["quasar_band_workflow"] = {}
    st.session_state["specialist_analysis_requested"] = True
    st.session_state["specialist_analysis_requested_v2"] = True
    st.session_state["specialist_analysis_requested_v3"] = True
    st.session_state["specialist_analysis_scope"] = analysis_scope
    st.session_state["quasar_workflow_running"] = True
    st.session_state["specialist_workflow_running"] = True
    st.session_state["final_review_completed"] = False
    st.session_state["completed_specialists"] = 0
    st.session_state["total_specialists"] = 6
    st.session_state["specialist_summary_locked"] = True
    st.session_state["workflow_run_id"] = workflow_run_id
    st.session_state["quasar_workflow_thread"] = start_workflow_thread(analysis_scope)


def normalize_label_text(label: str) -> str:
    return str(label or "UNKNOWN").replace("_", " ").title()


def label_direction(label: dict) -> str:
    direction = str(label.get("direction") or "").upper()
    if direction:
        return direction
    label_name = str(label.get("label") or "").upper()
    if "BULLISH" in label_name:
        return "BULLISH"
    if "BEARISH" in label_name:
        return "BEARISH"
    return "NEUTRAL"


def dominant_bias_from_labels(labels: list[dict]) -> str:
    bullish = sum(float(label.get("confidence") or 0) for label in labels if label_direction(label) == "BULLISH")
    bearish = sum(float(label.get("confidence") or 0) for label in labels if label_direction(label) == "BEARISH")
    if bullish > bearish:
        return "Mixed Bullish" if bearish else "Bullish"
    if bearish > bullish:
        return "Mixed Bearish" if bullish else "Bearish"
    if bullish or bearish:
        return "Conflicted"
    return "Neutral"


def selected_market_params(analysis_scope: str) -> tuple[str, str, str]:
    if analysis_scope == "FOREX":
        return "FOREX", "XAUUSD", "Forex XAUUSD"
    return "MCX", "NATURALGAS", "MCX NATURALGAS"


def format_percent(value) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "Waiting"


def compact_directional_confidence(direction: str, value) -> str:
    label = str(direction or "Neutral").replace("_", " ").title()
    if "Bullish" in label:
        label = "Bullish"
    elif "Bearish" in label:
        label = "Bearish"
    elif "Neutral" not in label and "Waiting" not in label:
        label = label.split()[0]
    percent = format_percent(value)
    return f"{label}: {percent}" if percent != "Waiting" else percent


def percent_value(value, default=None):
    text = str(value or "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if match:
        return int(round(float(match.group(1))))
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if numeric <= 1:
        numeric *= 100
    return int(round(numeric))


def unit_value(value, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if numeric > 1:
        numeric /= 100
    return max(0.0, min(numeric, 1.0))


def confidence_attribution(decision: dict[str, object]) -> dict[str, object]:
    intelligence = decision.get("multi_timeframe")
    if not isinstance(intelligence, dict) or not intelligence:
        return {"rows": [], "final": percent_value(decision.get("structure_confidence"))}

    metrics = intelligence.get("metrics") if isinstance(intelligence.get("metrics"), dict) else {}
    alignment = intelligence.get("alignment") if isinstance(intelligence.get("alignment"), dict) else {}
    hierarchy = (
        intelligence.get("timeframe_hierarchy")
        if isinstance(intelligence.get("timeframe_hierarchy"), dict)
        else {}
    )
    scenarios = intelligence.get("scenarios") if isinstance(intelligence.get("scenarios"), dict) else {}
    memory = intelligence.get("memory") if isinstance(intelligence.get("memory"), dict) else {}
    evolution = intelligence.get("evolution") if isinstance(intelligence.get("evolution"), dict) else {}

    final_confidence = (
        percent_value(decision.get("structure_confidence"))
        or percent_value(metrics.get("structure_confidence"))
        or percent_value(intelligence.get("structure_confidence"))
        or percent_value(alignment.get("alignment_score"))
        or 0
    )

    aligned = alignment.get("aligned_timeframes") or []
    conflicting = alignment.get("conflicting_timeframes") or []
    total_timeframes = max(1, len(aligned) + len(conflicting))
    hierarchy_conflict = str(hierarchy.get("hierarchy_conflict") or "").upper()
    if hierarchy_conflict == "LOW":
        hierarchy_factor = 1.0
    elif hierarchy_conflict == "MEDIUM":
        hierarchy_factor = 0.65
    elif hierarchy_conflict == "HIGH":
        hierarchy_factor = 0.25
    else:
        hierarchy_factor = len(aligned) / total_timeframes

    primary = scenarios.get("primary_scenario") if isinstance(scenarios.get("primary_scenario"), dict) else {}
    secondary = scenarios.get("secondary_scenario") if isinstance(scenarios.get("secondary_scenario"), dict) else {}
    primary_probability = percent_value(primary.get("probability"), 0) or 0
    secondary_probability = percent_value(secondary.get("probability"), 0) or 0
    scenario_factor = max(0.0, min((primary_probability - secondary_probability) / 50, 1.0))

    memory_status = str(memory.get("status") or "").lower()
    if evolution.get("has_previous"):
        timeframe_changes = evolution.get("timeframe_changes") or []
        regime_changed = bool((evolution.get("regime_change") or {}).get("changed"))
        decision_changed = bool((evolution.get("decision_change") or {}).get("changed"))
        persistence_factor = 0.45 if timeframe_changes or regime_changed or decision_changed else 1.0
    elif memory_status in {"recorded", "duplicate_skipped"}:
        persistence_factor = 0.65
    else:
        persistence_factor = 0.35

    agreement_factor = unit_value(alignment.get("alignment_score") or intelligence.get("alignment_score"))
    conflict_level = str(alignment.get("conflict_level") or decision.get("conflict_level") or "").upper()
    conflict_factor = {"LOW": 0.0, "MEDIUM": 0.5, "HIGH": 1.0}.get(conflict_level, 0.25)

    raw_rows = [
        ("Hierarchy Alignment", 30 * hierarchy_factor),
        ("Scenario Dominance", 25 * scenario_factor),
        ("Structure Persistence", 20 * persistence_factor),
        ("Multi-Timeframe Agreement", 25 * agreement_factor),
    ]
    penalty = int(round(15 * conflict_factor))
    available_positive = max(0, final_confidence + penalty)
    raw_total = sum(score for _, score in raw_rows)
    if raw_total <= 0:
        contributions = [0 for _ in raw_rows]
    else:
        contributions = [int(round((score / raw_total) * available_positive)) for _, score in raw_rows]

    adjustment = available_positive - sum(contributions)
    if contributions and adjustment:
        strongest_index = max(range(len(raw_rows)), key=lambda index: raw_rows[index][1])
        contributions[strongest_index] += adjustment

    return {
        "rows": [
            {"label": label, "value": value}
            for (label, _), value in zip(raw_rows, contributions)
        ]
        + [{"label": "Conflict Penalty", "value": -penalty}],
        "final": final_confidence,
    }


def render_confidence_attribution(decision: dict[str, object]) -> str:
    attribution = confidence_attribution(decision)
    rows = attribution.get("rows", [])
    if not rows:
        final = attribution.get("final")
        return (
            '<div class="decision-label">Confidence Attribution</div>'
            '<div class="confidence-attribution">'
            '<div class="confidence-row"><span>Confidence source</span><strong>Final review output</strong></div>'
            f'<div class="confidence-final">Final Confidence: {html.escape(str(final) + "%" if final is not None else "Unavailable")}</div>'
            "</div>"
        )
    row_markup = "".join(
        (
            '<div class="confidence-row">'
            f'<span>{html.escape(item["label"])}</span>'
            f'<strong>{html.escape(("+" if item["value"] >= 0 else "-") + str(abs(int(item["value"]))) + "%")}</strong>'
            "</div>"
        )
        for item in rows
    )
    return (
        '<div class="decision-label">Confidence Attribution</div>'
        '<div class="confidence-attribution">'
        f"{row_markup}"
        f'<div class="confidence-final">Final Confidence: {html.escape(str(attribution.get("final", 0)))}%</div>'
        "</div>"
    )


def alignment_label(value) -> str:
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


def direction_class(value: str) -> str:
    text = str(value or "").upper()
    if "CONFLICT" in text:
        return "conflicted"
    if "BULLISH" in text:
        return "bullish"
    if "BEARISH" in text:
        return "bearish"
    if "RANGE" in text or "NEUTRAL" in text:
        return "neutral"
    return "insufficient"


def mtf_rows(snapshot: dict) -> list[dict[str, str]]:
    rows = []
    for timeframe in ["1m", "3m", "5m", "15m", "1H", "4H"]:
        payload = snapshot.get("timeframes", {}).get(timeframe, {})
        top_signal = payload.get("top_signal") or {}
        if top_signal:
            direction = str(top_signal.get("direction") or "").upper()
            arrow = "▲" if direction == "BULLISH" else "▼" if direction == "BEARISH" else "•"
            signal = (
                f"{normalize_label_text(top_signal.get('label_type'))} {arrow} "
                f"{format_percent(top_signal.get('confidence'))}"
            )
        else:
            signal = "No signal"
        rows.append(
            {
                "timeframe": timeframe,
                "structure": str(
                    payload.get("structure_state")
                    or payload.get("structure")
                    or payload.get("bias")
                    or "INSUFFICIENT"
                ).replace("_", " ").title(),
                "top_signal": signal,
                "confidence": format_percent(payload.get("confidence")),
                "confidence_breakdown": payload.get("confidence_breakdown", {}),
                "direction_class": direction_class(payload.get("structure_state") or payload.get("bias")),
                "reason": payload.get("reason", "Waiting for structure."),
            }
        )
    return rows


def top_aligned_timeframes(snapshot: dict) -> str:
    aligned = snapshot.get("alignment", {}).get("aligned_timeframes", [])
    return ", ".join(aligned) if aligned else "None"


def label_side(value: str) -> str:
    text = str(value or "").upper()
    if "BULLISH" in text:
        return "BULLISH"
    if "BEARISH" in text:
        return "BEARISH"
    return "NEUTRAL"


def get_selected_market_preview(analysis_scope: str, timezone_name: str = "UTC") -> dict[str, str]:
    market_type, instrument, scope_label = selected_market_params(analysis_scope)
    candles = market_candles(market_type, instrument, "1m", limit=1)
    labels_response = smc_labels(market_type, instrument, "1m", limit=20)
    intelligence = multi_timeframe_intelligence(market_type, instrument, "1m")
    labels = labels_response.get("labels", []) if "error" not in labels_response else []
    top_label = labels[0] if labels else {}
    top_signal = "Waiting for labels"
    if top_label:
        confidence = int(round(float(top_label.get("confidence") or 0) * 100))
        top_signal = f"{normalize_label_text(top_label.get('label_type'))} {confidence}%"

    candle_rows = candles.get("candles", []) if "error" not in candles else []
    latest = candle_rows[0] if candle_rows else {}
    timestamp = latest.get("timestamp", "")
    session = market_session_text(market_type, timestamp) if timestamp else "Waiting"
    data_age = format_freshness(timestamp, timezone_name) if timestamp else "Waiting"
    alignment = intelligence.get("alignment", {}) if "error" not in intelligence else {}
    decision = intelligence.get("decision", {}) if "error" not in intelligence else {}
    narrative = intelligence.get("narrative", {}) if "error" not in intelligence else {}
    metrics = intelligence.get("metrics", {}) if "error" not in intelligence else {}
    validation_triggers = intelligence.get("validation_triggers", {}) if "error" not in intelligence else {}
    structure_chain = intelligence.get("structure_chain", {}) if "error" not in intelligence else {}
    timeframe_rows = mtf_rows(intelligence) if "error" not in intelligence else []
    if timeframe_rows:
        top_signal = timeframe_rows[0].get("top_signal", top_signal)
    return {
        "scope": scope_label,
        "market_regime": str(intelligence.get("regime", "Waiting")).replace("_", " ").title(),
        "dominant_bias": alignment.get("dominant_bias") or dominant_bias_from_labels(labels),
        "multi_timeframe_bias": alignment.get("dominant_bias", "Waiting"),
        "decision_state": decision.get("state", "Waiting"),
        "structure_confidence": format_percent(metrics.get("structure_confidence", intelligence.get("structure_confidence"))),
        "summary_confidence": compact_directional_confidence(
            alignment.get("dominant_bias") or dominant_bias_from_labels(labels),
            alignment.get("alignment_score", intelligence.get("alignment_score")),
        ),
        "raw_alignment_score": alignment.get("alignment_score", intelligence.get("alignment_score")),
        "directional_alignment": alignment_label(alignment.get("alignment_score")),
        "decision_strength": format_percent(metrics.get("decision_strength", intelligence.get("decision_strength"))),
        "structure_quality": intelligence.get("structure_quality", "Waiting"),
        "conflict_level": str(alignment.get("conflict_level", "Waiting")).title(),
        "top_aligned_timeframes": top_aligned_timeframes(intelligence),
        "top_signal": top_signal,
        "reason": decision.get("reason", "Waiting for Band analysis."),
        "narrative": narrative.get("summary", "Waiting for market narrative."),
        "decision_rationale": narrative.get("decision_rationale", decision.get("reason", "Waiting for Band analysis.")),
        "next_validation": decision.get("next_validation", "Waiting for Band analysis."),
        "executive_summary": intelligence.get("executive_summary", ""),
        "validation_triggers": validation_triggers,
        "structure_chain": structure_chain,
        "evolution": intelligence.get("evolution", {}),
        "session": session,
        "data_age": data_age,
        "safety": "Advisory-only",
        "multi_timeframe": intelligence if "error" not in intelligence else {},
        "timeframe_rows": timeframe_rows,
    }


def render_selected_market_preview(preview: dict[str, str]):
    st.markdown(
        (
            '<div class="scope-preview">'
            '<div class="scope-preview-title">Selected Market Preview</div>'
            '<div class="scope-preview-grid">'
            f'<div><span class="decision-label">Selected Scope:</span> {html.escape(preview.get("scope", ""))}</div>'
            f'<div><span class="decision-label">Market Regime:</span> {html.escape(preview.get("market_regime", ""))}</div>'
            f'<div><span class="decision-label">Multi-Timeframe Bias:</span> {html.escape(preview.get("multi_timeframe_bias", ""))}</div>'
            f'<div><span class="decision-label">Decision State:</span> {html.escape(preview.get("decision_state", ""))}</div>'
            f'<div><span class="decision-label">Structure Confidence:</span> {html.escape(preview.get("structure_confidence", ""))}</div>'
            f'<div><span class="decision-label">Directional Alignment:</span> {html.escape(preview.get("directional_alignment", ""))}</div>'
            f'<div><span class="decision-label">Structure Quality:</span> {html.escape(preview.get("structure_quality", ""))}</div>'
            f'<div><span class="decision-label">Conflict Level:</span> {html.escape(preview.get("conflict_level", ""))}</div>'
            f'<div><span class="decision-label">Aligned TFs:</span> {html.escape(preview.get("top_aligned_timeframes", ""))}</div>'
            f'<div><span class="decision-label">Top Signal:</span> {html.escape(preview.get("top_signal", ""))}</div>'
            f'<div><span class="decision-label">Narrative:</span> {html.escape(preview.get("narrative", ""))}</div>'
            f'<div><span class="decision-label">Session:</span> {html.escape(preview.get("session", ""))}</div>'
            f'<div><span class="decision-label">Data Age:</span> {html.escape(preview.get("data_age", ""))}</div>'
            f'<div><span class="decision-label">Safety Mode:</span> {html.escape(preview.get("safety", ""))}</div>'
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_multi_timeframe_table(
    rows: list[dict[str, str]],
    title: str = "Multi-Timeframe Details",
    expanded: bool = False,
):
    if not rows:
        return
    with st.expander(title, expanded=expanded):
        st.markdown(
            '<div class="mtf-row mtf-header"><div>TF</div><div>State</div><div>Signal</div><div>Conf</div></div>',
            unsafe_allow_html=True,
        )
        for row in rows:
            state_class = direction_class(row.get("structure", ""))
            signal_class = direction_class(row.get("top_signal", ""))
            st.markdown(
                (
                    f'<div class="mtf-row {state_class}">'
                    f'<div>{html.escape(str(row.get("timeframe", "")))}</div>'
                    f'<div class="mtf-state">{html.escape(str(row.get("structure", "")))}</div>'
                    f'<div class="mtf-signal {signal_class}">{html.escape(str(row.get("top_signal", "")))}</div>'
                    f'<div>{html.escape(str(row.get("confidence", "")))}</div>'
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
        with st.expander("Confidence Breakdown", expanded=False):
            for row in rows:
                breakdown = row.get("confidence_breakdown", {}) or {}
                st.caption(
                    (
                        f"{row.get('timeframe', '')}: "
                        f"Primary {format_percent(breakdown.get('primary_signal'))} | "
                        f"Recency {format_percent(breakdown.get('recency'))} | "
                        f"Support {format_percent(breakdown.get('supporting_signals'))} | "
                        f"Readiness {format_percent(breakdown.get('data_readiness'))} | "
                        f"Final {format_percent(breakdown.get('final'))}"
                    )
                )


def render_structure_chain(chain: dict):
    rows = chain.get("chain", []) if isinstance(chain, dict) else []
    if not rows:
        return
    st.markdown('<div class="workflow-section-title">Structure Chain</div>', unsafe_allow_html=True)
    parts = []
    for index, item in enumerate(rows):
        state = str(item.get("state", "INSUFFICIENT")).replace("_", " ").title()
        state_class = direction_class(state)
        parts.append(
            '<div class="chain-node">'
            f'<span class="chain-tf">{html.escape(str(item.get("timeframe", "")))}</span>'
            f'<span class="chain-state {state_class}">{html.escape(state)}</span>'
            '</div>'
        )
        if index < len(rows) - 1:
            parts.append('<div class="chain-arrow">↓</div>')
    st.markdown(f'<div class="structure-chain">{"".join(parts)}</div>', unsafe_allow_html=True)
    if chain.get("interpretation"):
        st.caption(chain["interpretation"])


def render_validation_conditions(triggers: dict):
    if not isinstance(triggers, dict) or not triggers:
        return
    groups = [
        ("Bullish continuation", triggers.get("bullish_validation", []), "bullish"),
        ("Bearish continuation", triggers.get("bearish_validation", []), "bearish"),
        ("Wait if", triggers.get("wait_conditions", []), "neutral"),
    ]
    with st.expander("Validation Conditions", expanded=False):
        for title, items, css_class in groups:
            if not items:
                continue
            body = "".join(
                f"<li>{html.escape(sanitize_advisory_text(str(item).replace('_', ' ')))}</li>"
                for item in items
            )
            st.markdown(
                f'<div class="validation-block {css_class}"><strong>{html.escape(title)}</strong><ul>{body}</ul></div>',
                unsafe_allow_html=True,
            )


def render_structure_evolution(evolution: dict):
    with st.expander("Structure Evolution", expanded=False):
        if not isinstance(evolution, dict) or not evolution.get("has_previous"):
            st.caption("No prior reviewed intelligence state is available yet.")
            return
        regime = evolution.get("regime_change", {})
        decision = evolution.get("decision_change", {})
        confidence = evolution.get("confidence_change", {})
        timeframe_changes = evolution.get("timeframe_changes", [])
        changed_lines = []
        if regime.get("changed"):
            changed_lines.append(
                "Regime moved from "
                f"{sanitize_advisory_text(str(regime.get('previous', '')).replace('_', ' ').title())} "
                "to "
                f"{sanitize_advisory_text(str(regime.get('current', '')).replace('_', ' ').title())}."
            )
        if decision.get("changed"):
            changed_lines.append(
                "Decision state moved from "
                f"{sanitize_advisory_text(decision.get('previous'))} to "
                f"{sanitize_advisory_text(decision.get('current'))}."
            )
        if timeframe_changes:
            changed_lines.extend(
                [
                    (
                        f"{str(item.get('timeframe', ''))} reviewed state moved from "
                        f"{sanitize_advisory_text(str(item.get('previous_state', '')).replace('_', ' ').title())} to "
                        f"{sanitize_advisory_text(str(item.get('current_state', '')).replace('_', ' ').title())}."
                    )
                    for item in timeframe_changes[:5]
                ]
            )
        delta = confidence.get("delta")
        try:
            delta_value = float(delta)
        except (TypeError, ValueError):
            delta_value = 0.0
        if abs(delta_value) >= 0.01:
            direction = "strengthened" if delta_value > 0 else "weakened"
            changed_lines.append(
                f"Structure confidence {direction} by {abs(delta_value) * 100:.0f}%."
            )
        if changed_lines:
            changed_items = "".join(
                f"<li>{html.escape(line)}</li>" for line in changed_lines
            )
        else:
            changed_items = (
                "<li>No material structure, regime, decision, or confidence change detected.</li>"
            )
        raw_reason = str(evolution.get("summary", ""))
        reason = sanitize_advisory_text(raw_reason)
        if "No timeframe structure state changed" in raw_reason:
            current_state = sanitize_advisory_text(decision.get("current"))
            current_regime = sanitize_advisory_text(
                str(regime.get("current", "")).replace("_", " ").title()
            )
            if changed_lines:
                reason = (
                    "The latest review changed outside the timeframe chain, so the evolution "
                    "is being driven by regime, decision, or confidence movement."
                )
            else:
                reason = (
                    "The latest reviewed state remains "
                    f"{current_state or 'unchanged'} / {current_regime or 'unchanged'}; "
                    "no material movement was detected across the tracked evolution fields."
                )
        st.markdown(
            (
                '<div class="decision-card">'
                f'<div><span class="decision-label">Previous:</span> {html.escape(sanitize_advisory_text(decision.get("previous")))} / {html.escape(sanitize_advisory_text(str(regime.get("previous", "")).replace("_", " ").title()))}</div>'
                f'<div><span class="decision-label">Current:</span> {html.escape(sanitize_advisory_text(decision.get("current")))} / {html.escape(sanitize_advisory_text(str(regime.get("current", "")).replace("_", " ").title()))}</div>'
                '<div class="decision-label">What Changed</div>'
                f'<ul class="decision-list">{changed_items}</ul>'
                '<div class="decision-label">Reason</div>'
                f'<div>{html.escape(reason)}</div>'
                '</div>'
            ),
            unsafe_allow_html=True,
        )


def render_final_decision_card(decision: dict[str, object]):
    scope = sanitize_advisory_text(decision.get("scope"))
    decision_state = sanitize_advisory_text(decision.get("decision_state"))
    market_regime = sanitize_advisory_text(decision.get("market_regime"))
    structure_confidence = sanitize_advisory_text(decision.get("structure_confidence"))
    directional_alignment = sanitize_advisory_text(decision.get("directional_alignment"))
    conflict_level = sanitize_advisory_text(decision.get("conflict_level"))
    executive_summary = sanitize_advisory_text(
        decision.get("executive_summary")
        or decision.get("narrative")
        or decision.get("reason")
        or (
            "Specialist review completed. Current state remains "
            f"{decision.get('decision_state', 'WAIT')} because confidence and alignment "
            "require fresh multi-timeframe confirmation."
        )
    )
    dominant_hypothesis = sanitize_advisory_text(decision.get("dominant_hypothesis"))
    alternative_hypothesis = sanitize_advisory_text(decision.get("alternative_hypothesis"))
    why_not_confirmed = sanitize_advisory_text(decision.get("why_not_confirmed"))
    next_validation = sanitize_advisory_text(decision.get("next_validation"))
    evidence = sanitize_advisory_list(decision.get("evidence", []))
    evidence_items = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in evidence
    )
    if not evidence_items and dominant_hypothesis:
        evidence_items = f"<li>{html.escape(dominant_hypothesis)}</li>"
    if not evidence_items:
        evidence_items = "<li>Final review completed with advisory-only evidence.</li>"
    st.markdown(
        (
            '<div class="decision-card">'
            '<div class="decision-title">Final Advisory Assessment</div>'
            '<div class="executive-strip">'
            f'<div><span>Decision State</span><strong>{html.escape(decision_state or "WAIT")}</strong></div>'
            f'<div><span>Market Regime</span><strong>{html.escape(market_regime or "Unavailable")}</strong></div>'
            f'<div><span>Confidence</span><strong>{html.escape(structure_confidence or "Unavailable")}</strong></div>'
            f'<div><span>Conflict</span><strong>{html.escape(conflict_level or "Unavailable")}</strong></div>'
            f'<div><span>Dominant Thesis</span><strong>{html.escape(dominant_hypothesis or "Unavailable")}</strong></div>'
            "</div>"
            '<div class="decision-label">Executive Summary</div>'
            f'<div>{html.escape(executive_summary)}</div>'
            f"{render_confidence_attribution(decision)}"
            '<div class="decision-label">Dominant Hypothesis</div>'
            f'<div>{html.escape(dominant_hypothesis or "Unavailable")}</div>'
            '<div class="decision-label">Alternative Hypothesis</div>'
            f'<div>{html.escape(alternative_hypothesis or "Unavailable")}</div>'
            '<div class="decision-label">Why Not Confirmed</div>'
            f'<div>{html.escape(why_not_confirmed or conflict_level or "Review validation conditions.")}</div>'
            '<div class="decision-label">Key Evidence</div>'
            f'<ul class="decision-list">{evidence_items}</ul>'
            '<div class="decision-label">Next Validation</div>'
            f'<div>{html.escape(next_validation or "Review fresh multi-timeframe confirmation before changing the advisory state.")}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    render_validation_conditions(decision.get("validation_triggers", {}))


def agent_response_summary(step: dict, selected_scope: str) -> dict[str, object]:
    response_text = clean_agent_output(
        step.get("response_text") or step.get("summary") or "Waiting for Band analysis."
    )
    prompt_context = parse_prompt_context(step.get("prompt_sent", ""))
    brief = step.get("specialist_brief") if isinstance(step.get("specialist_brief"), dict) else {}
    labels = list(prompt_context.get("labels", []))
    decision_state = (
        brief_value(brief, "state", "decision_state")
        or extract_line_value(response_text, "Decision State")
        or extract_line_value(response_text, "State")
        or str(prompt_context.get("bias") or step.get("status", "waiting")).title()
    )
    brief_text = brief_value(
        brief,
        "brief",
        "executive_summary",
        "dominant_thesis",
        "readiness_summary",
        "risk_reason",
        "primary_watch_condition",
    )
    evidence = brief_list(
        brief,
        "supporting_evidence",
        "contradicting_evidence",
        "bullish_continuation_conditions",
        "confidence_risk",
        "why_not_confirmed",
    )
    if not evidence:
        evidence = extract_section_lines(
            response_text,
            "Intelligence Evidence",
            ["Confidence", "Next Validation", "Next Step", "Safety", "Specialist Notes"],
        )
    if not evidence:
        evidence = extract_section_lines(
            response_text,
            "Evidence",
            ["Next Validation", "Next Step", "Safety", "Specialist Notes"],
        )
    if not evidence:
        evidence = [response_text[:180]]
    next_step = (
        brief_value(brief, "next_validation", "next_step")
        or extract_line_value(response_text, "Next Validation")
        or extract_line_value(response_text, "Next Step")
        or "Recheck after fresh multi-timeframe evidence updates."
    )
    supporting_signals = brief_list(brief, "supporting_signals") or labels[:3]
    agent = step.get("agent", "")
    if agent == "Requirement Agent":
        decision_state = brief_value(brief, "state") or "Scope Confirmed"
        brief_text = brief_text or brief_value(brief, "market_question")
        next_step = brief_value(brief, "next_step", "next_validation") or "Continue specialist review for the selected market only."
    elif agent == "Architecture Agent":
        decision_state = brief_value(brief, "state") or "Readiness Review"
        next_step = brief_value(brief, "next_step", "next_validation") or "Check freshness, session state, feed source, and evidence availability."
        evidence = [
            f"Freshness: {brief_value(brief, 'freshness') or prompt_context.get('data_age') or 'Unknown'}",
            f"Session: {brief_value(brief, 'session') or prompt_context.get('session') or 'Unknown'}",
            f"Source: {brief_value(brief, 'data_source') or prompt_context.get('source') or 'Unknown'}",
        ]
    elif agent == "Risk Governance Agent":
        decision_state = brief_value(brief, "state") or "Guardrails Active"
        next_step = brief_value(brief, "next_step", "next_validation") or "Require confirmation and avoid stale or conflicted structure."
    elif agent == "Delivery Planning Agent":
        decision_state = brief_value(brief, "state") or "Validation Plan"
    elif agent == "Final Review Agent":
        decision_state = brief_value(brief, "state", "decision_state") or extract_line_value(response_text, "Decision State") or "WATCH"
        evidence = [
            item
            for item in [
                brief_value(brief, "dominant_hypothesis"),
                brief_value(brief, "alternative_hypothesis"),
                brief_value(brief, "why_not_confirmed"),
            ]
            if item
        ] or evidence

    duration = step.get("duration_seconds")
    completed_at = short_time(step.get("completed_at", ""))
    timing = f"{completed_at} • {duration}s" if step.get("completed_at") and duration is not None else ""
    evidence_items = "".join(f"<li>{html.escape(str(item))}</li>" for item in evidence[:3])
    supporting_items = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in supporting_signals[:3]
    )
    brief_block = (
        '<div class="response-block-title">Brief</div>'
        f'<div>{html.escape(brief_text)}</div>'
        if brief_text
        else ""
    )
    supporting_block = (
        '<div class="response-block-title">Supporting Signals</div>'
        f'<ul class="decision-list">{supporting_items}</ul>'
        if supporting_items
        else ""
    )
    timing_block = (
        '<div class="response-block-title">Timing</div>'
        f'<div>{html.escape(timing)}</div>'
        if timing
        else ""
    )
    return {
        "state": sanitize_advisory_text(decision_state),
        "brief": sanitize_advisory_text(brief_text or response_text),
        "next_step": sanitize_advisory_text(next_step),
        "evidence": evidence[:3],
        "supporting_signals": supporting_signals[:3],
        "timing": timing,
        "expanded_html": (
            '<div class="response-scroll">'
            '<div class="response-block-title">State</div>'
            f'<div>{html.escape(str(decision_state))}</div>'
            f"{brief_block}"
            '<div class="response-block-title">Evidence</div>'
            f'<ul class="decision-list">{evidence_items}</ul>'
            '<div class="response-block-title">Next Step</div>'
            f'<div>{html.escape(str(next_step))}</div>'
            f"{supporting_block}"
            f"{timing_block}"
            "</div>"
        ),
    }


def render_agent_card_detail(step: dict, selected_scope: str) -> str:
    if step.get("status") != "completed":
        return ""
    summary = agent_response_summary(step, selected_scope)
    brief = str(summary.get("brief") or "")
    validation_focus = str(summary.get("next_step") or "")
    validation_focus_block = (
        '<div class="agent-card-label">Validation Focus</div>'
        f'<div class="agent-card-text">{html.escape(validation_focus)}</div>'
        if step.get("agent") == "Delivery Planning Agent" and validation_focus
        else ""
    )
    return (
        '<div class="agent-card-detail">'
        '<div class="agent-card-label">State</div>'
        f'<div class="agent-card-value">{html.escape(str(summary.get("state", "")))}</div>'
        '<div class="agent-card-label">Brief</div>'
        f'<div class="agent-card-text">{html.escape(brief)}</div>'
        f"{validation_focus_block}"
        "</div>"
    )


@st.fragment
def render_agent_monitor():
    workflow = fetch_workflow_status()
    workflow_details = fetch_workflow_details()

    with st.container(border=True):
        st.markdown(
            '<div class="market-card-title">Agent Swarm Monitor</div>',
            unsafe_allow_html=True,
        )

        if "error" in workflow:
            st.error(workflow["error"])
            return
        if "error" in workflow_details:
            workflow_details = workflow

        detail_steps = workflow_details.get("steps") or workflow["steps"]
        completed_agents = sum(1 for step in detail_steps if step["status"] == "completed")
        current_state = workflow_details.get("status") or workflow.get("current_state", "waiting")
        workflow_thread = st.session_state.get("quasar_workflow_thread")
        thread_alive = bool(workflow_thread and workflow_thread.is_alive())
        if current_state in {"completed", "failed"} or (
            current_state == "waiting" and not thread_alive
        ):
            st.session_state["quasar_workflow_running"] = False
        gate_state = sync_specialist_workflow_gate(workflow, detail_steps, current_state)
        detail_steps = gated_specialist_steps(detail_steps, gate_state)
        completed_agents = sum(1 for step in detail_steps if step["status"] == "completed")
        analysis_scope_label = st.radio(
            "Analysis Scope",
            ["MCX NATURALGAS", "Forex XAUUSD"],
            horizontal=True,
            key="analysis_scope",
        )
        analysis_scope = "FOREX" if analysis_scope_label == "Forex XAUUSD" else "MCX"
        selected_scope = display_scope_label(analysis_scope)
        selected_timezone = st.session_state.get("global_timezone", "UTC")
        if "specialist_analysis_requested_v3" not in st.session_state:
            st.session_state["specialist_analysis_requested_v3"] = False
            st.session_state["specialist_analysis_requested_v2"] = False
            st.session_state["specialist_analysis_requested"] = False
        previous_scope = st.session_state.get("specialist_analysis_scope")
        if previous_scope and previous_scope != analysis_scope:
            reset_specialist_analysis_request()
        st.session_state["specialist_analysis_scope"] = analysis_scope
        analysis_requested = bool(st.session_state.get("specialist_analysis_requested_v3"))
        selected_preview = {"scope": selected_scope}
        if not analysis_requested:
            st.info(
                "Select a market and run specialist analysis to generate a reviewed advisory briefing."
            )

        analysis_in_progress = bool(
            st.session_state.get("quasar_workflow_running")
            and not st.session_state.get("final_review_completed")
        )
        st.markdown(
            (
                '<div class="agent-purpose-banner">'
                '<div class="agent-purpose-title">Agent Swarm Review</div>'
                '<div class="agent-purpose-copy">'
                "Transforms raw market structure into an advisory assessment using:"
                "</div>"
                '<div class="agent-purpose-grid">'
                "<span>✓ Multi-Timeframe Intelligence</span>"
                "<span>✓ Scenario Analysis</span>"
                "<span>✓ Hierarchy Analysis</span>"
                "<span>✓ Market Memory</span>"
                "<span>✓ Governance Validation</span>"
                "<span>✓ Specialist Review</span>"
                "</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        st.button(
            "Get Specialist Analysis",
            key="run_quasar_band_workflow_button_v2",
            use_container_width=True,
            type="primary",
            on_click=start_specialist_analysis,
            args=(
                analysis_scope,
                workflow.get("workflow_run_id") or workflow.get("workflow_id", ""),
            ),
        )
        if analysis_in_progress:
            st.caption("Specialist review in progress")

        if not analysis_requested:
            return

        if gate_state.get("final_review_completed"):
            selected_preview = get_selected_market_preview(analysis_scope, selected_timezone)

        workflow_scope = str(workflow_details.get("analysis_scope") or "MCX").upper()
        decision = final_decision_data(workflow_details, selected_scope)
        workflow_matches_selection = workflow_scope == analysis_scope
        mtf_decision = selected_preview.get("multi_timeframe", {}).get("decision", {})
        mtf_alignment = selected_preview.get("multi_timeframe", {}).get("alignment", {})
        final_gate_complete = bool(gate_state.get("final_review_completed"))
        if mtf_decision and not final_gate_complete:
            decision["decision_state"] = mtf_decision.get("state", decision.get("decision_state", "Waiting"))
            decision["structure_confidence"] = selected_preview.get("summary_confidence", selected_preview.get("structure_confidence", "Waiting"))
            decision["market_regime"] = selected_preview.get("market_regime", "Waiting")
            decision["structure_quality"] = selected_preview.get("structure_quality", "Waiting")
            decision["directional_alignment"] = selected_preview.get("directional_alignment", "Waiting")
            decision["executive_summary"] = selected_preview.get("executive_summary", "")
            decision["validation_triggers"] = selected_preview.get("validation_triggers", {})
            decision["evolution"] = selected_preview.get("evolution", {})
            decision["narrative"] = selected_preview.get("decision_rationale") or selected_preview.get("narrative")
            decision["reason"] = mtf_decision.get("reason", decision.get("reason", "Waiting for Band analysis."))
            decision["next_validation"] = mtf_decision.get(
                "next_validation",
                decision.get("next_validation", "Waiting for Band analysis."),
            )
            decision["alignment_score"] = selected_preview.get("alignment_score", "Waiting")
            decision["conflict_level"] = str(
                mtf_alignment.get("conflict_level", "Waiting")
            ).title()
        elif final_gate_complete:
            decision["multi_timeframe"] = selected_preview.get("multi_timeframe", {})
            decision["structure_confidence"] = (
                selected_preview.get("summary_confidence")
                or decision.get("structure_confidence")
                or selected_preview.get("structure_confidence", "Waiting")
            )
            decision["market_regime"] = (
                decision.get("market_regime")
                or selected_preview.get("market_regime", "Waiting")
            )
            decision["structure_quality"] = selected_preview.get("structure_quality", "Waiting")
            decision["directional_alignment"] = selected_preview.get("directional_alignment", "Waiting")
            decision["validation_triggers"] = selected_preview.get("validation_triggers", {})
            decision["evolution"] = selected_preview.get("evolution", {})
            decision["alignment_score"] = selected_preview.get("alignment_score", "Waiting")
            decision["conflict_level"] = selected_preview.get("conflict_level", "Waiting")
        if str(current_state).lower() == "waiting":
            decision["decision_state"] = selected_preview.get("decision_state", "Waiting")
            decision["structure_confidence"] = selected_preview.get("summary_confidence", selected_preview.get("structure_confidence", "Waiting"))
            decision["market_regime"] = selected_preview.get("market_regime", "Waiting")
            decision["structure_quality"] = selected_preview.get("structure_quality", "Waiting")
            decision["directional_alignment"] = selected_preview.get("directional_alignment", "Waiting")
            decision["executive_summary"] = selected_preview.get("executive_summary", "")
            decision["validation_triggers"] = selected_preview.get("validation_triggers", {})
            decision["evolution"] = selected_preview.get("evolution", {})
            decision["narrative"] = selected_preview.get("narrative", "Waiting for market narrative.")
            decision["alignment_score"] = selected_preview.get("alignment_score", "Waiting")
            decision["conflict_level"] = selected_preview.get("conflict_level", "Waiting")
        decision = apply_specialist_summary_gate(decision, gate_state)

        summary_cards = [
            ("Selected Market", selected_preview.get("scope", selected_scope)),
            (
                "Decision State",
                str(decision.get("decision_state", "Waiting"))
                if workflow_matches_selection
                else "Waiting",
            ),
            (
                "Market Regime",
                str(decision.get("market_regime", "Waiting"))
                if workflow_matches_selection
                else "Waiting",
            ),
            (
                "Structure Confidence",
                str(decision.get("structure_confidence", "Waiting"))
                if workflow_matches_selection
                else "Waiting",
            ),
        ]
        summary_cols = st.columns(4)
        for col, (label, value) in zip(summary_cols, summary_cards):
            with col:
                st.markdown(
                    (
                        '<div class="agent-summary-card">'
                        f'<div class="metric-label">{html.escape(label)}</div>'
                        f'<div class="metric-value">{html.escape(value)}</div>'
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
        if gate_state.get("summary_locked") and not gate_state.get("final_review_completed"):
            st.caption("Specialist review in progress")

        st.progress((workflow_details.get("progress", workflow["progress"]) or 0) / 100)
        st.caption(
            f"Run State: {str(current_state).title()} | "
            f"Progress: {workflow_details.get('progress', workflow['progress'])}% | "
            f"Completed Agents: {gate_state.get('completed', completed_agents)}/{gate_state.get('total', len(detail_steps))}"
        )

        display_names = {
            "Requirement Agent": "Requirement",
            "Market Intelligence Agent": "Market Intelligence",
            "Architecture Agent": "System Readiness",
            "Risk Governance Agent": "Risk Governance",
            "Delivery Planning Agent": "Delivery Planning",
            "Final Review Agent": "Final Review",
        }
        status_labels = {
            "completed": "✅ Completed",
            "running": "🔄 Running",
            "waiting": "⏳ Waiting",
            "failed": "⚠ Failed",
        }
        agent_cols = st.columns(6)
        for col, step in zip(agent_cols, detail_steps):
            with col:
                status_class = step["status"] if step["status"] in status_labels else "waiting"
                badge_markup = (
                    '<div class="agent-band-badge">Band ✓</div>'
                    if step.get("status") == "completed"
                    else ""
                )
                status_markup = (
                    ""
                    if step.get("status") == "completed"
                    else f'<div class="agent-status">{html.escape(status_labels.get(step["status"], step["status"].title()))}</div>'
                )
                detail_markup = render_agent_card_detail(step, selected_scope)
                st.markdown(
                    (
                        f'<div class="agent-card {status_class}">'
                        f'<div class="agent-name">{html.escape(display_names.get(step["agent"], step["agent"]))}</div>'
                        f"{status_markup}"
                        f"{badge_markup}"
                        f"{detail_markup}"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )

        if final_gate_complete and workflow_matches_selection:
            render_final_decision_card(decision)
            render_structure_evolution(decision.get("evolution", {}))

        last_quasar_workflow = st.session_state.get("quasar_band_workflow", {})
        if last_quasar_workflow:
            if last_quasar_workflow.get("success"):
                st.success("Quasar Band workflow completed.")
            elif last_quasar_workflow.get("status") == "no_messages":
                st.info("No pending Band workflow message.")
            else:
                st.warning(
                    last_quasar_workflow.get("error")
                    or last_quasar_workflow.get("message")
                    or "Quasar Band workflow did not complete."
                )

        failed_steps = [step for step in detail_steps if step.get("status") == "failed"]
        has_failure = bool(failed_steps) or str(current_state).lower() == "failed"
        if has_failure:
            diagnostics = workflow_details.get("delivery_pack", {}).get("diagnostics", {})
            failed_agent = failed_steps[0] if failed_steps else {}
            with st.expander("Advanced Diagnostics", expanded=False):
                st.write(f"Workflow ID: {workflow_details.get('workflow_id', '—')}")
                st.write(f"Chat ID: {workflow_details.get('chat_id') or diagnostics.get('band_chat_id') or '—'}")
                st.write(f"Message ID: {workflow_details.get('message_id') or diagnostics.get('source_message_id') or '—'}")
                st.write(f"Failed Agent: {failed_agent.get('agent', '—')}")
                st.write(
                    "Error Reason: "
                    f"{failed_agent.get('summary') or last_quasar_workflow.get('error') or 'Unknown'}"
                )
                st.write(f"Scanned Message Count: {failed_agent.get('scanned_message_count', '—')}")

        if analysis_requested and (
            st.session_state.get("quasar_workflow_running")
            or st.session_state.get("specialist_workflow_running")
            or current_state == "running"
            or thread_alive
        ):
            time.sleep(3)
            rerun_agent_monitor()
