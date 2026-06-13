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

router = APIRouter()


@router.get("/workflow-status")
def workflow_status():
    band_status = band_config_status()
    band_status.update(get_band_processing_state())
    state = get_workflow_state()
    return {
        "workflow_id": state["workflow_id"],
        "current_agent": state["current_agent"],
        "current_state": state.get("status", "waiting"),
        "progress": state["progress"],
        "steps": state["steps"],
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
