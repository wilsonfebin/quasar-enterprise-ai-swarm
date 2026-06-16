from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.specialist_response_store import (
    get_latest_final_review,
    get_latest_specialist_responses,
)


SPECIALIST_EVIDENCE_MAP = {
    "Requirement Agent": [
        "Multi-Timeframe Intelligence Engine",
        "Timeframe Hierarchy Engine",
        "Scenario Engine",
    ],
    "Market Intelligence Agent": [
        "Timeframe Hierarchy Engine",
        "Scenario Engine",
        "Structure Evolution Engine",
    ],
    "Architecture Agent": [
        "Multi-Timeframe Intelligence Engine",
        "Market Memory Engine",
    ],
    "Risk Governance Agent": [
        "Scenario Engine",
        "Timeframe Hierarchy Engine",
        "Market Memory Engine",
    ],
    "Delivery Planning Agent": [
        "Scenario Engine",
        "Structure Evolution Engine",
        "Timeframe Hierarchy Engine",
    ],
    "Final Review Agent": [
        "Multi-Timeframe Intelligence Engine",
        "Scenario Engine",
        "Timeframe Hierarchy Engine",
        "Market Memory Engine",
    ],
}

DISPLAY_NAMES = {
    "Requirement Agent": "Requirement Specialist",
    "Market Intelligence Agent": "Market Intelligence Specialist",
    "Architecture Agent": "System Readiness Specialist",
    "Risk Governance Agent": "Risk Governance Specialist",
    "Delivery Planning Agent": "Delivery Planning Specialist",
    "Final Review Agent": "Final Review Specialist",
}


def build_governance_evidence(
    workflow_details: dict[str, Any],
    context: dict[str, Any] | None = None,
    persisted_responses: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = context or {}
    persisted_responses = _load_persisted_responses_if_needed(
        workflow_details,
        context,
        persisted_responses,
    )
    mtf = context.get("multi_timeframe") or {}
    steps = _steps_with_persisted_responses(
        workflow_details.get("steps") or [],
        persisted_responses,
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    findings = [
        _specialist_finding(step, mtf, timestamp)
        for step in steps
        if step.get("agent") in SPECIALIST_EVIDENCE_MAP
    ]
    missing = [
        warning
        for finding in findings
        for warning in finding.get("missing_evidence_warnings", [])
    ]
    return {
        "workflow_id": workflow_details.get("workflow_id", ""),
        "analysis_scope": workflow_details.get("analysis_scope", context.get("analysis_scope", "")),
        "generated_at": timestamp,
        "specialist_findings": findings,
        "evidence_count": sum(len(item.get("evidence", [])) for item in findings),
        "missing_evidence_warnings": missing,
    }


def _load_persisted_responses_if_needed(
    workflow_details: dict[str, Any],
    context: dict[str, Any],
    persisted_responses: dict[str, Any] | None,
) -> dict[str, Any]:
    if persisted_responses is not None:
        return persisted_responses
    if _has_all_runtime_responses(workflow_details):
        return {}

    market, instrument = _market_and_instrument(context, workflow_details)
    try:
        latest = get_latest_specialist_responses(market=market, instrument=instrument)
        if _runtime_final_review_missing(workflow_details) and not latest.get("final_review"):
            latest["final_review"] = get_latest_final_review(
                market=market,
                instrument=instrument,
            )
        return latest
    except Exception:
        return {}


def _has_all_runtime_responses(workflow_details: dict[str, Any]) -> bool:
    steps = [
        step
        for step in workflow_details.get("steps", [])
        if step.get("agent") in SPECIALIST_EVIDENCE_MAP
    ]
    return bool(steps) and all(step.get("response_text") for step in steps)


def _runtime_final_review_missing(workflow_details: dict[str, Any]) -> bool:
    if workflow_details.get("final_summary"):
        return False
    final_step = next(
        (
            step
            for step in workflow_details.get("steps", [])
            if step.get("agent") == "Final Review Agent"
        ),
        {},
    )
    return not bool(final_step.get("response_text"))


def _market_and_instrument(
    context: dict[str, Any],
    workflow_details: dict[str, Any],
) -> tuple[str, str]:
    scope = str(
        context.get("analysis_scope")
        or workflow_details.get("analysis_scope")
        or "MCX"
    ).upper()
    if scope == "FOREX":
        return "FOREX", str((context.get("forex") or {}).get("instrument") or "XAUUSD")
    return "MCX", str((context.get("mcx") or {}).get("instrument") or "NATURALGAS")


def _steps_with_persisted_responses(
    steps: list[dict[str, Any]],
    persisted_responses: dict[str, Any],
) -> list[dict[str, Any]]:
    persisted_by_agent = {
        str(item.get("specialist_name") or ""): item
        for item in persisted_responses.get("specialists", [])
        if item.get("specialist_name")
    }
    final_review = persisted_responses.get("final_review") or {}
    if final_review.get("specialist_name"):
        persisted_by_agent[str(final_review["specialist_name"])] = final_review

    hydrated = []
    for step in steps:
        agent = str(step.get("agent") or "")
        persisted = persisted_by_agent.get(agent)
        if step.get("response_text") or not persisted:
            hydrated.append(step)
            continue
        hydrated.append(
            {
                **step,
                "summary": step.get("summary") or persisted.get("finding") or persisted.get("summary", ""),
                "response_text": persisted.get("summary") or persisted.get("finding", ""),
                "response_preview": persisted.get("finding") or persisted.get("summary", ""),
                "response_received": True,
                "specialist_brief": persisted.get("specialist_brief", {}),
                "response_source": persisted.get("response_source", "persisted"),
                "persisted_response_used": True,
                "persisted_created_at": persisted.get("created_at", ""),
            }
        )
    return hydrated


def governance_evidence_references_text(evidence_payload: dict[str, Any]) -> str:
    findings = evidence_payload.get("specialist_findings") or []
    lines = ["Evidence References:"]
    for finding in findings:
        evidence = finding.get("evidence") or []
        if not evidence:
            continue
        facts = "; ".join(str(item.get("fact", "")) for item in evidence[:2] if item.get("fact"))
        if facts:
            lines.append(f"- {finding.get('specialist')}: {facts}")
    return "\n".join(lines) if len(lines) > 1 else "Evidence References:\n- No evidence references available."


def _specialist_finding(step: dict[str, Any], mtf: dict[str, Any], timestamp: str) -> dict[str, Any]:
    agent = str(step.get("agent", ""))
    evidence = _evidence_for_agent(agent, mtf, timestamp)
    brief_evidence = _brief_evidence(step.get("specialist_brief") or {}, timestamp)
    warnings = []
    if not evidence:
        warnings.append(f"{DISPLAY_NAMES.get(agent, agent)} has no attached Quasar evidence.")
    if not step.get("response_text"):
        warnings.append(f"{DISPLAY_NAMES.get(agent, agent)} has no captured response text.")
    return {
        "specialist": DISPLAY_NAMES.get(agent, agent),
        "agent": agent,
        "finding": _finding_for_agent(agent, step, mtf),
        "confidence": _confidence(mtf),
        "timestamp": timestamp,
        "supporting_timeframes": _supporting_timeframes(mtf),
        "response_source": step.get("response_source") or ("persisted" if step.get("persisted_response_used") else "runtime"),
        "evidence": evidence + brief_evidence,
        "missing_evidence_warnings": warnings,
    }


def _brief_evidence(brief: dict[str, Any], timestamp: str) -> list[dict[str, Any]]:
    if not isinstance(brief, dict) or not brief:
        return []
    mapping = [
        ("thesis evidence", brief.get("dominant_thesis") or brief.get("dominant_hypothesis")),
        ("contradiction evidence", brief.get("alternative_thesis") or brief.get("alternative_hypothesis")),
        ("validation evidence", brief.get("next_validation") or brief.get("next_step")),
        ("readiness evidence", brief.get("readiness_summary")),
        ("risk evidence", brief.get("risk_reason") or brief.get("confidence_risk")),
    ]
    return [
        {
            "source": "Specialist Brief Builder",
            "fact": f"{label}: {value}",
            "timestamp": timestamp,
            "confidence": int(brief.get("structure_confidence") or 0),
            "supporting_timeframes": [],
        }
        for label, value in mapping
        if value
    ]


def _evidence_for_agent(agent: str, mtf: dict[str, Any], timestamp: str) -> list[dict[str, Any]]:
    sources = SPECIALIST_EVIDENCE_MAP.get(agent, [])
    builders = {
        "Multi-Timeframe Intelligence Engine": _multi_timeframe_evidence,
        "Timeframe Hierarchy Engine": _hierarchy_evidence,
        "Scenario Engine": _scenario_evidence,
        "Structure Evolution Engine": _evolution_evidence,
        "Market Memory Engine": _memory_evidence,
    }
    evidence = []
    for source in sources:
        fact = builders[source](mtf)
        if fact:
            evidence.append(
                {
                    "source": source,
                    "fact": fact,
                    "timestamp": timestamp,
                    "confidence": _confidence(mtf),
                    "supporting_timeframes": _supporting_timeframes(mtf),
                }
            )
    return evidence


def _finding_for_agent(agent: str, step: dict[str, Any], mtf: dict[str, Any]) -> str:
    if agent == "Market Intelligence Agent":
        return _display_regime(mtf.get("regime", ""))
    if agent == "Risk Governance Agent":
        return str((mtf.get("decision") or {}).get("state") or "WAIT")
    if agent == "Delivery Planning Agent":
        scenario = ((mtf.get("scenarios") or {}).get("primary_scenario") or {}).get("name")
        return str(scenario or "Wait / No Clear Scenario")
    if agent == "Final Review Agent":
        return str((mtf.get("decision") or {}).get("state") or "WAIT")
    return str(step.get("summary") or step.get("response_preview") or "Specialist review captured")


def _multi_timeframe_evidence(mtf: dict[str, Any]) -> str:
    regime = _display_regime(mtf.get("regime", ""))
    decision = str((mtf.get("decision") or {}).get("state") or "WAIT")
    quality = str(mtf.get("structure_quality") or "Unknown")
    return f"Regime {regime}; decision {decision}; structure quality {quality}"


def _hierarchy_evidence(mtf: dict[str, Any]) -> str:
    hierarchy = mtf.get("timeframe_hierarchy") or {}
    context = hierarchy.get("dominant_context")
    conflict = hierarchy.get("hierarchy_conflict")
    if context or conflict:
        return f"{context or 'Hierarchy context unavailable'}; hierarchy conflict {conflict or 'Unknown'}"
    return ""


def _scenario_evidence(mtf: dict[str, Any]) -> str:
    primary = ((mtf.get("scenarios") or {}).get("primary_scenario") or {})
    if not primary:
        return ""
    return f"{primary.get('name', 'Scenario unavailable')} {primary.get('probability', 0)}%"


def _evolution_evidence(mtf: dict[str, Any]) -> str:
    evolution = mtf.get("evolution") or {}
    if not evolution:
        return ""
    if not evolution.get("has_previous"):
        return "No previous intelligence snapshot available yet"
    return str(evolution.get("summary") or "Evolution summary unavailable")


def _memory_evidence(mtf: dict[str, Any]) -> str:
    memory = mtf.get("memory") or {}
    status = memory.get("status")
    if not status:
        return ""
    return f"Market memory snapshot status {status}"


def _confidence(mtf: dict[str, Any]) -> int:
    try:
        return int(round(float(mtf.get("structure_confidence") or 0) * 100))
    except (TypeError, ValueError):
        return 0


def _supporting_timeframes(mtf: dict[str, Any]) -> list[str]:
    timeframes = mtf.get("timeframes") or {}
    return [
        timeframe
        for timeframe in ("4H", "1H", "15m", "5m", "3m", "1m")
        if timeframe in timeframes
    ]


def _display_regime(value: Any) -> str:
    return str(value or "Unknown").replace("_", " ").title()
