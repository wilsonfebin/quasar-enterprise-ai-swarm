from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.specialist_response_store import (
    get_latest_final_review,
    get_latest_specialist_responses,
)


AUDIT_STAGES = [
    "Market Data Snapshot",
    "SMC Labels",
    "Multi-Timeframe Intelligence",
    "Structure Evolution",
    "Scenario Engine",
    "Timeframe Hierarchy",
    "Market Memory",
    "Governance Evidence",
    "Band Specialist Reviews",
    "Final Specialist Review",
]

SECRET_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "authorization",
    "x-api-key",
    "x-kite-version",
    "token",
    "secret",
}


def build_decision_trace(
    workflow_details: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    governance_evidence: dict[str, Any] | None = None,
    band_status: dict[str, Any] | None = None,
    market: str | None = None,
    instrument: str | None = None,
    persisted_responses: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workflow_details = workflow_details or {}
    context = context or {}
    governance_evidence = governance_evidence or {}
    band_status = band_status or {}
    created_at = _utc_now()
    selected_market = _selected_market_context(context, market, instrument)
    mtf = context.get("multi_timeframe") or {}
    decision = mtf.get("decision") or {}
    scenario = ((mtf.get("scenarios") or {}).get("primary_scenario") or {})
    market_label = _market_label(context, selected_market, market, instrument)
    persisted_responses = _load_persisted_responses_if_needed(
        workflow_details=workflow_details,
        context=context,
        market=market,
        instrument=instrument,
        persisted_responses=persisted_responses,
    )

    stages = [
        build_audit_stage(
            "Market Data Snapshot",
            created_at,
            "market/latest",
            summarize_market_snapshot(selected_market),
            _status(bool(selected_market.get("candle"))),
        ),
        build_audit_stage(
            "SMC Labels",
            created_at,
            "SMC Label Engine",
            _summarize_smc_labels(selected_market),
            _status(bool(selected_market.get("labels"))),
        ),
        build_audit_stage(
            "Multi-Timeframe Intelligence",
            created_at,
            "Multi-Timeframe Engine",
            summarize_mtf_intelligence(mtf),
            _status(bool(mtf)),
        ),
        build_audit_stage(
            "Structure Evolution",
            created_at,
            "Structure Evolution Engine",
            _summarize_evolution(mtf),
            _status(bool(mtf.get("evolution"))),
        ),
        build_audit_stage(
            "Scenario Engine",
            created_at,
            "Scenario Engine",
            summarize_scenario_engine(mtf),
            _status(bool(mtf.get("scenarios"))),
        ),
        build_audit_stage(
            "Timeframe Hierarchy",
            created_at,
            "Timeframe Hierarchy Engine",
            summarize_hierarchy(mtf),
            _status(bool(mtf.get("timeframe_hierarchy"))),
        ),
        build_audit_stage(
            "Market Memory",
            created_at,
            "Market Memory Engine",
            summarize_memory(mtf),
            _status(bool(mtf.get("memory"))),
        ),
        build_audit_stage(
            "Governance Evidence",
            created_at,
            "Governance Evidence Layer",
            summarize_governance_evidence(governance_evidence),
            _status(bool(governance_evidence.get("specialist_findings"))),
        ),
        build_audit_stage(
            "Band Specialist Reviews",
            created_at,
            "Band Remote Agent Workflow",
            summarize_specialist_reviews(workflow_details, band_status, persisted_responses),
            _status(_has_specialist_responses(workflow_details, persisted_responses)),
        ),
        build_audit_stage(
            "Final Specialist Review",
            created_at,
            "Final Review Specialist",
            _summarize_final_review(workflow_details, persisted_responses),
            _status(_has_final_review(workflow_details, persisted_responses)),
        ),
    ]
    warnings = collect_audit_warnings(
        stages,
        workflow_details,
        governance_evidence,
        band_status,
        persisted_responses,
    )
    trace = {
        "audit_id": _audit_id(workflow_details, market_label, created_at),
        "market": market_label,
        "created_at": created_at,
        "safety_status": "ADVISORY_ONLY",
        "decision_state": str(decision.get("state") or "WAIT"),
        "market_regime": _display(mtf.get("regime") or "Unknown"),
        "scenario": str(scenario.get("name") or "Wait / No Clear Scenario"),
        "evidence_count": int(governance_evidence.get("evidence_count") or 0),
        "stages": stages,
        "warnings": warnings,
    }
    return _json_safe(trace)


def build_audit_stage(
    stage: str,
    timestamp: str | datetime,
    source: str,
    summary: str,
    status: str = "available",
) -> dict[str, str]:
    return {
        "stage": stage,
        "timestamp": _iso(timestamp),
        "source": source,
        "summary": str(summary or "No summary available."),
        "status": status if status in {"available", "missing"} else "missing",
    }


def summarize_market_snapshot(market_snapshot: dict[str, Any] | None) -> str:
    market_snapshot = market_snapshot or {}
    candle = market_snapshot.get("candle") or {}
    if not candle:
        return "Latest market candle is not available."
    timestamp = market_snapshot.get("timestamp") or market_snapshot.get("exchange_candle_time") or ""
    source = market_snapshot.get("source") or "Unknown source"
    freshness = market_snapshot.get("data_age") or market_snapshot.get("freshness") or "freshness unavailable"
    close = candle.get("close", "unknown")
    return f"Latest candle captured from {source}; close {close}; timestamp {timestamp}; {freshness}."


def summarize_mtf_intelligence(mtf: dict[str, Any] | None) -> str:
    mtf = mtf or {}
    if not mtf:
        return "Multi-timeframe intelligence is not available."
    regime = _display(mtf.get("regime") or "Unknown")
    confidence = _percent(mtf.get("structure_confidence"))
    decision = (mtf.get("decision") or {}).get("state") or "WAIT"
    quality = mtf.get("structure_quality") or "Unknown"
    return f"{regime} detected with {confidence} confidence; decision state {decision}; quality {quality}."


def summarize_scenario_engine(mtf: dict[str, Any] | None) -> str:
    scenarios = (mtf or {}).get("scenarios") or {}
    primary = scenarios.get("primary_scenario") or {}
    if not primary:
        return "Scenario engine output is not available."
    return f"Primary scenario {primary.get('name', 'Unknown')} at {primary.get('probability', 0)}%; safety status {scenarios.get('safety_status', 'ADVISORY_ONLY')}."


def summarize_hierarchy(mtf: dict[str, Any] | None) -> str:
    hierarchy = (mtf or {}).get("timeframe_hierarchy") or {}
    if not hierarchy:
        return "Timeframe hierarchy output is not available."
    context = hierarchy.get("dominant_context") or "Hierarchy context unavailable"
    conflict = hierarchy.get("hierarchy_conflict") or "Unknown"
    bias = hierarchy.get("scenario_bias") or "Scenario bias unavailable"
    return f"{context}; hierarchy conflict {conflict}; {bias}."


def summarize_memory(mtf: dict[str, Any] | None) -> str:
    memory = (mtf or {}).get("memory") or {}
    if not memory:
        return "Market memory evidence is not available."
    status = memory.get("status") or "unknown"
    memory_id = memory.get("id")
    suffix = f"; memory id {memory_id}" if memory_id else ""
    return f"Market memory snapshot status {status}{suffix}."


def summarize_governance_evidence(governance_evidence: dict[str, Any] | None) -> str:
    governance_evidence = governance_evidence or {}
    count = int(governance_evidence.get("evidence_count") or 0)
    findings = governance_evidence.get("specialist_findings") or []
    if not findings:
        return "Governance evidence is not available."
    return f"{count} supporting evidence items attached across {len(findings)} specialist findings."


def summarize_specialist_reviews(
    workflow_details: dict[str, Any] | None,
    band_status: dict[str, Any] | None = None,
    persisted_responses: dict[str, Any] | None = None,
) -> str:
    workflow_details = workflow_details or {}
    band_status = band_status or {}
    persisted_responses = persisted_responses or {}
    steps = workflow_details.get("steps") or []
    completed = sum(1 for step in steps if step.get("status") == "completed")
    captured = sum(1 for step in steps if step.get("response_text"))
    persisted_captured = len(persisted_responses.get("specialists") or [])
    if not captured and persisted_captured:
        captured = persisted_captured
        return (
            f"{captured} specialist responses captured from persisted review history; "
            "latest persisted Band specialist responses were used because runtime "
            f"workflow state was empty; Band mode {band_status.get('mode') or band_status.get('status') or 'unknown'}."
        )
    band_mode = band_status.get("mode") or band_status.get("status") or "unknown"
    return f"{captured} specialist responses captured; {completed} specialists completed; Band mode {band_mode}."


def collect_audit_warnings(
    stages: list[dict[str, Any]],
    workflow_details: dict[str, Any] | None = None,
    governance_evidence: dict[str, Any] | None = None,
    band_status: dict[str, Any] | None = None,
    persisted_responses: dict[str, Any] | None = None,
) -> list[str]:
    warnings = [
        f"{stage['stage']} data is missing."
        for stage in stages
        if stage.get("status") == "missing"
    ]
    workflow_details = workflow_details or {}
    governance_evidence = governance_evidence or {}
    band_status = band_status or {}
    persisted_responses = persisted_responses or {}
    warnings.extend(governance_evidence.get("missing_evidence_warnings") or [])
    if not _has_specialist_responses(workflow_details, persisted_responses):
        warnings.append("No captured Band specialist responses are available yet.")
    if band_status and not band_status.get("configured", True):
        warnings.append("Band configuration is missing; specialist review may be unavailable.")
    if band_status and band_status.get("enabled") is False:
        warnings.append("Band integration is disabled; workflow evidence is internal only.")
    return _dedupe(warnings)


def _summarize_smc_labels(market_snapshot: dict[str, Any] | None) -> str:
    labels = (market_snapshot or {}).get("labels") or (market_snapshot or {}).get("smc_labels") or []
    if not labels:
        return "SMC labels are not available."
    top = labels[0]
    label = top.get("label") or top.get("label_type") or "Unknown label"
    confidence = _percent(top.get("confidence"))
    return f"{len(labels)} market structure labels captured; top label {label} at {confidence} confidence."


def _summarize_evolution(mtf: dict[str, Any] | None) -> str:
    evolution = (mtf or {}).get("evolution") or {}
    if not evolution:
        return "Structure evolution is not available."
    if not evolution.get("has_previous"):
        return "No previous intelligence snapshot available yet."
    return str(evolution.get("summary") or "Structure evolution summary unavailable.")


def _summarize_final_review(
    workflow_details: dict[str, Any] | None,
    persisted_responses: dict[str, Any] | None = None,
) -> str:
    workflow_details = workflow_details or {}
    persisted_responses = persisted_responses or {}
    final_summary = str(workflow_details.get("final_summary") or "")
    if final_summary:
        return _compact(final_summary, 220)
    final_step = next(
        (
            step for step in workflow_details.get("steps", [])
            if step.get("agent") == "Final Review Agent"
        ),
        {},
    )
    persisted_final = persisted_responses.get("final_review") or {}
    return _compact(
        final_step.get("response_text")
        or final_step.get("summary")
        or persisted_final.get("summary")
        or persisted_final.get("finding")
        or "Final specialist review is not available.",
        220,
    )


def _selected_market_context(
    context: dict[str, Any],
    market: str | None = None,
    instrument: str | None = None,
) -> dict[str, Any]:
    scope = str(context.get("analysis_scope") or market or "").upper()
    if scope == "FOREX" or str(instrument or "").upper() == "XAUUSD":
        return context.get("forex") or {}
    if scope == "MCX" or str(instrument or "").upper() == "NATURALGAS":
        return context.get("mcx") or {}
    return context.get("mcx") or context.get("forex") or {}


def _market_label(
    context: dict[str, Any],
    selected_market: dict[str, Any],
    market: str | None,
    instrument: str | None,
) -> str:
    if market and instrument:
        return f"{str(market).upper()} {str(instrument).upper()}"
    if context.get("scope_label"):
        return str(context["scope_label"])
    market_type = selected_market.get("market_type") or context.get("analysis_scope") or market or "MCX"
    selected_instrument = selected_market.get("instrument") or instrument or "NATURALGAS"
    return f"{str(market_type).upper()} {str(selected_instrument).upper()}"


def _has_specialist_responses(
    workflow_details: dict[str, Any],
    persisted_responses: dict[str, Any] | None = None,
) -> bool:
    if any(step.get("response_text") for step in workflow_details.get("steps", [])):
        return True
    persisted_responses = persisted_responses or {}
    return bool(persisted_responses.get("specialists"))


def _has_final_review(
    workflow_details: dict[str, Any],
    persisted_responses: dict[str, Any] | None = None,
) -> bool:
    if workflow_details.get("final_summary"):
        return True
    if any(
        step.get("response_text")
        for step in workflow_details.get("steps", [])
        if step.get("agent") == "Final Review Agent"
    ):
        return True
    return bool((persisted_responses or {}).get("final_review"))


def _load_persisted_responses_if_needed(
    *,
    workflow_details: dict[str, Any],
    context: dict[str, Any],
    market: str | None,
    instrument: str | None,
    persisted_responses: dict[str, Any] | None,
) -> dict[str, Any]:
    if persisted_responses is not None:
        return persisted_responses
    if _has_specialist_responses(workflow_details, {}) and _has_final_review(workflow_details, {}):
        return {}

    effective_market, effective_instrument = _market_and_instrument(
        context=context,
        selected_market=_selected_market_context(context, market, instrument),
        market=market,
        instrument=instrument,
    )
    try:
        latest = get_latest_specialist_responses(
            market=effective_market,
            instrument=effective_instrument,
        )
        if _has_final_review(workflow_details, latest):
            return latest
        latest["final_review"] = get_latest_final_review(
            market=effective_market,
            instrument=effective_instrument,
        )
        return latest
    except Exception:
        return {}


def _market_and_instrument(
    *,
    context: dict[str, Any],
    selected_market: dict[str, Any],
    market: str | None,
    instrument: str | None,
) -> tuple[str, str]:
    market_type = str(
        market
        or selected_market.get("market_type")
        or context.get("analysis_scope")
        or "MCX"
    ).upper()
    selected_instrument = str(
        instrument
        or selected_market.get("instrument")
        or ("XAUUSD" if market_type == "FOREX" else "NATURALGAS")
    ).upper()
    return market_type, selected_instrument


def _status(available: bool) -> str:
    return "available" if available else "missing"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_id(workflow_details: dict[str, Any], market_label: str, created_at: str) -> str:
    seed = f"{workflow_details.get('workflow_id', 'workflow')}:{market_label}:{created_at[:19]}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def _iso(value: str | datetime) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.replace(tzinfo=timezone.utc).isoformat()
    return str(value or _utc_now())


def _display(value: Any) -> str:
    return str(value or "Unknown").replace("_", " ").title()


def _percent(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0%"
    if number <= 1:
        number *= 100
    return f"{int(round(number))}%"


def _compact(value: Any, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            if str(key).lower() in SECRET_KEYS:
                safe[key] = "[REDACTED]"
            else:
                safe[key] = _json_safe(item)
        return safe
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.replace(tzinfo=timezone.utc).isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
