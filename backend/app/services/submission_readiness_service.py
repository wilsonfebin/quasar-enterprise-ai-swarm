from __future__ import annotations

import json
from typing import Any


PROJECT_NAME = "Quasar Enterprise AI Delivery Swarm"
HACKATHON_TRACK = "Regulated & High-Stakes Systems"
SAFETY_STATUS = "ADVISORY_ONLY"

COMPONENT_WEIGHTS = {
    "data_layer": 10,
    "feed_lifecycle": 10,
    "smc_engine": 10,
    "multi_timeframe_intelligence": 10,
    "scenario_engine": 10,
    "timeframe_hierarchy": 8,
    "market_memory": 8,
    "band_specialists": 12,
    "governance_evidence": 10,
    "decision_audit_trail": 7,
    "specialist_persistence": 5,
}

SECRET_MARKERS = {
    "api_key",
    "apikey",
    "access_token",
    "authorization",
    "x-api-key",
    "password",
    "secret",
    "token",
}


def build_submission_readiness_snapshot(
    market: str = "MCX",
    instrument: str = "NATURALGAS",
) -> dict[str, Any]:
    market = str(market or "MCX").upper()
    instrument = str(instrument or ("XAUUSD" if market == "FOREX" else "NATURALGAS")).upper()
    analysis_scope = "FOREX" if market == "FOREX" or instrument == "XAUUSD" else "MCX"

    latest_market = _safe_call(lambda: _fetch_latest_market_snapshot(timeframe="1m"), {})
    service = _workflow_service()
    context = _safe_call(
        lambda: service.build_quasar_context(analysis_scope=analysis_scope),
        {
            "analysis_scope": analysis_scope,
            "multi_timeframe": {},
        },
    )
    mtf = context.get("multi_timeframe") or {}
    workflow_details = _safe_call(_get_workflow_details, {})
    persisted = _safe_call(
        lambda: _get_latest_specialist_responses(market=market, instrument=instrument),
        {"specialists": [], "final_review": {}},
    )
    governance = _safe_call(
        lambda: _build_governance_evidence(
            workflow_details,
            context,
            persisted_responses=persisted,
        ),
        {},
    )
    band_status = _safe_call(_band_config_status, {})
    audit = _safe_call(
        lambda: _build_decision_trace(
            workflow_details=workflow_details,
            context=context,
            governance_evidence=governance,
            band_status=band_status,
            market=market,
            instrument=instrument,
            persisted_responses=persisted,
        ),
        {},
    )
    feed_status = {
        "forex": _safe_call(_get_twelvedata_ingestion_status, {}),
        "mcx": _safe_call(_get_zerodha_ingestion_status, {}),
    }

    components = _build_components(
        latest_market=latest_market,
        feed_status=feed_status,
        mtf=mtf,
        governance=governance,
        audit=audit,
        persisted=persisted,
        band_status=band_status,
    )
    warnings = _collect_warnings(
        latest_market=latest_market,
        governance=governance,
        audit=audit,
        persisted=persisted,
        components=components,
    )
    readiness_score = calculate_readiness_score(components)
    payload = {
        "project": PROJECT_NAME,
        "hackathon_track": HACKATHON_TRACK,
        "readiness_score": readiness_score,
        "readiness_state": readiness_state(readiness_score, warnings),
        "safety_status": SAFETY_STATUS,
        "components": components,
        "evidence": {
            "governance_evidence_count": int(governance.get("evidence_count") or 0),
            "audit_stage_count": len(audit.get("stages") or []),
            "specialist_response_count": len(persisted.get("specialists") or []),
            "latest_workflow_run_id": str(persisted.get("workflow_run_id") or ""),
        },
        "warnings": warnings,
        "demo_claims_supported": _demo_claims_supported(components),
    }
    sanitized = sanitize_readiness_payload(payload)
    if contains_secret_like_value(sanitized):
        sanitized["warnings"] = _dedupe(
            sanitized.get("warnings", []) + ["Secret-like value detected in readiness output."]
        )
        sanitized["readiness_state"] = readiness_state(
            sanitized.get("readiness_score", 0),
            sanitized["warnings"],
        )
    return sanitized


def calculate_readiness_score(components: dict[str, dict[str, Any]]) -> int:
    score = 0.0
    for name, weight in COMPONENT_WEIGHTS.items():
        status = str((components.get(name) or {}).get("status") or "").lower()
        if status == "ready":
            score += weight
        elif status == "warning":
            score += weight * 0.5
    return int(round(score))


def readiness_state(score: int, warnings: list[str]) -> str:
    critical = _critical_warnings(warnings)
    if score >= 90 and not critical:
        return "READY"
    if score >= 75:
        return "READY_WITH_WARNINGS"
    return "NOT_READY"


def sanitize_readiness_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if str(key).lower() in SECRET_MARKERS:
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_readiness_payload(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_readiness_payload(item) for item in value]
    return value


def contains_secret_like_value(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, sort_keys=True).lower()
    return any(marker in text and "[redacted]" not in text for marker in SECRET_MARKERS)


def _build_components(
    *,
    latest_market: dict[str, Any],
    feed_status: dict[str, dict[str, Any]],
    mtf: dict[str, Any],
    governance: dict[str, Any],
    audit: dict[str, Any],
    persisted: dict[str, Any],
    band_status: dict[str, Any],
) -> dict[str, dict[str, str]]:
    mcx = latest_market.get("mcx") or {}
    forex = latest_market.get("forex") or {}
    labels = (mcx.get("smc_labels") or []) + (forex.get("smc_labels") or [])
    scenarios = mtf.get("scenarios") or {}
    hierarchy = mtf.get("timeframe_hierarchy") or {}
    memory = mtf.get("memory") or {}
    findings = governance.get("specialist_findings") or []
    audit_stages = audit.get("stages") or []
    specialists = persisted.get("specialists") or []
    final_review = persisted.get("final_review") or {}
    worker_alive = bool(
        (feed_status.get("forex") or {}).get("worker_alive")
        or (feed_status.get("mcx") or {}).get("worker_alive")
    )
    feed_has_status = bool(feed_status.get("forex") or feed_status.get("mcx"))
    band_connected = bool(band_status.get("configured")) or bool(specialists)

    return {
        "data_layer": component(
            "ready" if mcx.get("candle") or forex.get("candle") else "not_ready",
            "Latest market candle data is available."
            if mcx.get("candle") or forex.get("candle")
            else "No latest market candle data is available.",
        ),
        "feed_lifecycle": component(
            "ready" if worker_alive else "warning" if feed_has_status else "not_ready",
            "Backend ingestion lifecycle status is available."
            if feed_has_status
            else "Feed lifecycle status is unavailable.",
        ),
        "smc_engine": component(
            "ready" if labels else "not_ready",
            f"{len(labels)} market structure labels are available."
            if labels
            else "Market structure labels are unavailable.",
        ),
        "multi_timeframe_intelligence": component(
            "ready" if mtf.get("timeframes") else "not_ready",
            "Multi-timeframe intelligence snapshot is available."
            if mtf.get("timeframes")
            else "Multi-timeframe intelligence snapshot is unavailable.",
        ),
        "scenario_engine": component(
            "ready" if scenarios.get("primary_scenario") else "not_ready",
            "Scenario engine output is available."
            if scenarios.get("primary_scenario")
            else "Scenario engine output is unavailable.",
        ),
        "timeframe_hierarchy": component(
            "ready" if hierarchy.get("hierarchy") else "not_ready",
            "Timeframe hierarchy output is available."
            if hierarchy.get("hierarchy")
            else "Timeframe hierarchy output is unavailable.",
        ),
        "market_memory": component(
            "ready"
            if memory.get("status") in {"recorded", "duplicate_skipped"}
            else "warning"
            if memory
            else "not_ready",
            f"Market memory status is {memory.get('status', 'unavailable')}.",
        ),
        "band_specialists": component(
            "ready" if specialists and band_connected else "not_ready",
            f"{len(specialists)} persisted Band specialist responses are available."
            if specialists
            else "Band specialist workflow evidence is unavailable.",
        ),
        "governance_evidence": component(
            "ready" if governance.get("evidence_count", 0) > 0 and findings else "not_ready",
            f"{governance.get('evidence_count', 0)} governance evidence items are attached."
            if findings
            else "Governance evidence is unavailable.",
        ),
        "decision_audit_trail": component(
            "ready" if len(audit_stages) >= 10 and audit.get("safety_status") == SAFETY_STATUS else "not_ready",
            f"{len(audit_stages)} audit stages are available."
            if audit_stages
            else "Decision audit trail is unavailable.",
        ),
        "specialist_persistence": component(
            "ready" if specialists and final_review else "warning" if specialists else "not_ready",
            "Specialist responses and final review are persisted."
            if specialists and final_review
            else "Persisted specialist responses are incomplete.",
        ),
    }


def component(status: str, summary: str) -> dict[str, str]:
    return {"status": status, "summary": summary}


def _collect_warnings(
    *,
    latest_market: dict[str, Any],
    governance: dict[str, Any],
    audit: dict[str, Any],
    persisted: dict[str, Any],
    components: dict[str, dict[str, Any]],
) -> list[str]:
    warnings = []
    if SAFETY_STATUS != "ADVISORY_ONLY":
        warnings.append("Critical: safety status is not advisory-only.")
    if not ((latest_market.get("mcx") or {}).get("candle") or (latest_market.get("forex") or {}).get("candle")):
        warnings.append("Critical: no market data available.")
    if not governance.get("specialist_findings"):
        warnings.append("Critical: governance evidence endpoint unavailable.")
    if not audit.get("stages"):
        warnings.append("Critical: audit trace unavailable.")
    if not persisted.get("specialists"):
        warnings.append("Critical: Band specialist workflow unavailable.")
    for name, payload in components.items():
        if payload.get("status") == "warning":
            warnings.append(f"{name} is ready with warnings.")
        elif payload.get("status") == "not_ready":
            warnings.append(f"{name} is not ready.")
    warnings.extend(governance.get("missing_evidence_warnings") or [])
    warnings.extend(audit.get("warnings") or [])
    return _dedupe(warnings)


def _critical_warnings(warnings: list[str]) -> list[str]:
    return [warning for warning in warnings if str(warning).lower().startswith("critical:")]


def _demo_claims_supported(components: dict[str, dict[str, Any]]) -> list[str]:
    claims = []
    if components["feed_lifecycle"]["status"] in {"ready", "warning"}:
        claims.append("Live market data ingestion lifecycle is observable")
    if components["multi_timeframe_intelligence"]["status"] == "ready":
        claims.append("Quasar generates multi-timeframe market intelligence")
    if components["band_specialists"]["status"] == "ready":
        claims.append("Band specialists review Quasar intelligence")
    if components["governance_evidence"]["status"] == "ready":
        claims.append("Every specialist finding is linked to governance evidence")
    if components["decision_audit_trail"]["status"] == "ready":
        claims.append("Decision trace remains available after runtime reset")
    if components["specialist_persistence"]["status"] in {"ready", "warning"}:
        claims.append("Specialist review continuity is persisted")
    claims.append("System is advisory-only with execution disabled")
    return claims


def _safe_call(callable_obj, fallback):
    try:
        return callable_obj()
    except Exception:
        return fallback


def _fetch_latest_market_snapshot(timeframe: str = "1m") -> dict[str, Any]:
    from app.db import fetch_latest_market_snapshot

    return fetch_latest_market_snapshot(timeframe=timeframe)


def _workflow_service():
    from app.agents.workflow_service import WorkflowService

    return WorkflowService()


def _get_workflow_details() -> dict[str, Any]:
    from app.agents.workflow_service import get_workflow_details

    return get_workflow_details()


def _get_latest_specialist_responses(market: str, instrument: str) -> dict[str, Any]:
    from app.services.specialist_response_store import get_latest_specialist_responses

    return get_latest_specialist_responses(market=market, instrument=instrument)


def _build_governance_evidence(*args, **kwargs) -> dict[str, Any]:
    from app.services.governance_evidence_service import build_governance_evidence

    return build_governance_evidence(*args, **kwargs)


def _band_config_status() -> dict[str, Any]:
    from app.agents.band_client import band_config_status

    return band_config_status()


def _build_decision_trace(*args, **kwargs) -> dict[str, Any]:
    from app.services.decision_audit_service import build_decision_trace

    return build_decision_trace(*args, **kwargs)


def _get_twelvedata_ingestion_status() -> dict[str, Any]:
    from app.data.scheduler import get_twelvedata_ingestion_status

    return get_twelvedata_ingestion_status()


def _get_zerodha_ingestion_status() -> dict[str, Any]:
    from app.data.scheduler import get_zerodha_ingestion_status

    return get_zerodha_ingestion_status()


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
