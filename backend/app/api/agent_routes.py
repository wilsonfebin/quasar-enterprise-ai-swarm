from fastapi import APIRouter, Query

from app.agents.band_client import (
    BandClient,
    band_config_status,
    extract_agent_identity,
    get_last_band_debug_response,
    utc_now_iso,
)
from app.agents.workflow_service import WorkflowService
from app.agents.workflow_service import (
    get_band_processing_state,
    get_workflow_details,
    get_workflow_state,
    reset_workflow_state,
    update_band_processing_state,
)
from app.agents.specialist_service import SpecialistProcessorService
from app.data.ingestion_service import append_log
from app.services.decision_audit_service import build_decision_trace
from app.services.governance_evidence_service import build_governance_evidence
from app.services.specialist_response_store import (
    get_latest_specialist_responses,
    get_responses_by_workflow_run_id,
)

router = APIRouter()


@router.get("/workflow-status")
def workflow_status():
    band_status = band_config_status()
    band_status.update(get_band_processing_state())
    state = get_workflow_state()
    steps = state.get("steps") or []
    completed_count = sum(1 for step in steps if step.get("status") == "completed")
    final_review_completed = any(
        step.get("agent") == "Final Review Agent" and step.get("status") == "completed"
        for step in steps
    )
    running = state.get("status") == "running"
    return {
        "workflow_id": state["workflow_id"],
        "workflow_run_id": state["workflow_id"],
        "current_agent": state["current_agent"],
        "current_state": state.get("status", "waiting"),
        "running": running,
        "specialist_workflow_running": running,
        "completed_count": completed_count,
        "completed_specialists": completed_count,
        "total_count": len(steps) or 6,
        "total_specialists": len(steps) or 6,
        "final_review_completed": final_review_completed,
        "progress": state["progress"],
        "steps": steps,
        "handoffs": [
            "Requirement Agent → Market Intelligence Agent",
            "Market Intelligence Agent → Architecture Agent",
            "Architecture Agent → Risk Governance Agent",
            "Risk Governance Agent → Delivery Planning Agent",
            "Delivery Planning Agent → Final Review Agent",
        ],
        "band": band_status,
    }


@router.get("/workflow/details")
def workflow_details():
    return get_workflow_details()


@router.get("/governance/evidence")
def governance_evidence():
    details = get_workflow_details()
    context = WorkflowService().build_quasar_context(
        analysis_scope=details.get("analysis_scope", "MCX")
    )
    persisted = get_latest_specialist_responses(
        market=context.get("analysis_scope"),
        instrument=_instrument_from_context(context),
    )
    return build_governance_evidence(
        details,
        context,
        persisted_responses=persisted,
    )


@router.get("/audit/decision-trace")
def decision_trace(
    market: str | None = Query(None),
    instrument: str | None = Query(None),
):
    return _latest_decision_trace(market=market, instrument=instrument)


@router.get("/audit/decision-trace/latest")
def latest_decision_trace(
    market: str | None = Query(None),
    instrument: str | None = Query(None),
):
    return _latest_decision_trace(market=market, instrument=instrument)


def _latest_decision_trace(
    market: str | None = None,
    instrument: str | None = None,
):
    details = get_workflow_details()
    scope = _analysis_scope_from_query(
        market=market,
        instrument=instrument,
        fallback=details.get("analysis_scope", "MCX"),
    )
    service = WorkflowService()
    context = service.build_quasar_context(analysis_scope=scope)
    effective_market = str(market or context.get("analysis_scope") or scope).upper()
    effective_instrument = instrument or _instrument_from_context(context)
    persisted = get_latest_specialist_responses(
        market=effective_market,
        instrument=effective_instrument,
    )
    evidence = build_governance_evidence(
        details,
        context,
        persisted_responses=persisted,
    )
    band = band_config_status()
    band.update(get_band_processing_state())
    return build_decision_trace(
        workflow_details=details,
        context=context,
        governance_evidence=evidence,
        band_status=band,
        market=effective_market,
        instrument=effective_instrument,
        persisted_responses=persisted,
    )


def _analysis_scope_from_query(
    market: str | None,
    instrument: str | None,
    fallback: str,
) -> str:
    market_value = str(market or "").upper()
    instrument_value = str(instrument or "").upper()
    if market_value == "FOREX" or instrument_value == "XAUUSD":
        return "FOREX"
    if market_value == "MCX" or instrument_value == "NATURALGAS":
        return "MCX"
    return str(fallback or "MCX").upper()


def _instrument_from_context(context: dict) -> str:
    if str(context.get("analysis_scope") or "").upper() == "FOREX":
        return str((context.get("forex") or {}).get("instrument") or "XAUUSD")
    return str((context.get("mcx") or {}).get("instrument") or "NATURALGAS")


@router.post("/workflow/reset")
def workflow_reset():
    state = reset_workflow_state()
    update_band_processing_state(
        last_message_status="waiting",
        last_chat_id="",
        last_message_id="",
        last_error="",
        last_response="",
        last_processed_at="",
        orchestration_mode="internal",
    )
    return get_workflow_details()


@router.get("/specialists/latest")
def latest_specialist_responses(
    market: str | None = Query(None),
    instrument: str | None = Query(None),
):
    return get_latest_specialist_responses(market=market, instrument=instrument)


@router.get("/specialists/history")
def specialist_response_history(
    workflow_run_id: str | None = Query(None),
    market: str | None = Query(None),
    instrument: str | None = Query(None),
):
    return get_responses_by_workflow_run_id(
        workflow_run_id=workflow_run_id,
        market=market,
        instrument=instrument,
    )


@router.get("/band/status")
def band_status():
    client = BandClient()
    if not client.is_enabled():
        return {
            "enabled": False,
            "configured": False,
            "status": "disabled",
        }

    if not client.is_configured():
        return {
            "enabled": True,
            "configured": False,
            "status": "missing_credentials",
        }

    health = client.health_check()
    if not health["connected"]:
        return {
            "enabled": True,
            "configured": True,
            "status": "disconnected",
        }

    identity = extract_agent_identity(health["agent"], client.agent_id)
    return {
        "enabled": True,
        "configured": True,
        "status": "connected",
        **identity,
    }


@router.get("/band/diagnostics")
def band_diagnostics():
    append_log("band.log", "Band diagnostics request")
    client = BandClient()
    health = client.health_check()
    agent = health.get("agent") if isinstance(health.get("agent"), dict) else {}
    identity = extract_agent_identity(agent, client.agent_id)

    return {
        "enabled": client.is_enabled(),
        "configured": client.is_configured(),
        "connected": bool(health.get("connected")),
        "agent_id": identity["agent_id"] if client.is_configured() else "",
        "api_reachable": bool(health.get("connected")),
        "last_check": utc_now_iso(),
    }


@router.get("/band/chats")
def band_chats():
    client = BandClient()
    if not client.is_enabled():
        return {"enabled": False, "configured": False, "count": 0, "chats": []}
    if not client.is_configured():
        return {"enabled": True, "configured": False, "count": 0, "chats": []}

    chats_response = client.list_chats()
    if chats_response.get("status") == "error":
        return {
            "enabled": True,
            "configured": True,
            "count": 0,
            "chats": [],
            "status": "error",
            "message": chats_response.get("message", "Unable to list Band chats"),
        }

    chats = chats_response.get("data", [])
    if isinstance(chats, dict):
        chats = chats.get("data", [])
    return {
        "enabled": True,
        "configured": True,
        "count": len(chats) if isinstance(chats, list) else 0,
        "chats": chats if isinstance(chats, list) else [],
    }


@router.get("/band/participants")
def band_participants(chat_id: str | None = Query(None)):
    return WorkflowService().discover_participants(chat_id=chat_id)


@router.post("/band/test-workflow")
def band_test_workflow():
    result = WorkflowService().run_band_health_check()
    return result


@router.get("/band/debug-last-response")
def band_debug_last_response():
    return get_last_band_debug_response()


@router.post("/band/process-next")
def band_process_next():
    return WorkflowService().process_next_band_message()


@router.post("/band/run-quasar-workflow")
def band_run_quasar_workflow(
    debug: bool = Query(False), analysis_scope: str = Query("MCX")
):
    return WorkflowService().run_quasar_workflow_from_band(
        debug=debug, analysis_scope=analysis_scope
    )


@router.post("/band/process-specialists")
def band_process_specialists(chat_id: str | None = Query(None)):
    return SpecialistProcessorService().process_all(chat_id=chat_id)
