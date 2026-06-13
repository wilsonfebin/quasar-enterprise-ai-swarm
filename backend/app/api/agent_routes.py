from fastapi import APIRouter

from app.agents.band_client import (
    BandClient,
    band_config_status,
    extract_agent_identity,
    get_last_band_debug_response,
    utc_now_iso,
)
from app.agents.workflow_service import WorkflowService
from app.agents.workflow_service import get_band_processing_state
from app.data.ingestion_service import append_log

router = APIRouter()


@router.get("/workflow-status")
def workflow_status():
    band_status = band_config_status()
    band_status.update(get_band_processing_state())
    return {
        "workflow_id": "quasar-delivery-swarm-001",
        "current_agent": "Market Intelligence Agent",
        "progress": 35,
        "steps": [
            {
                "agent": "Requirement Agent",
                "status": "completed",
                "summary": "Converted business requirement into structured delivery scope.",
            },
            {
                "agent": "Market Intelligence Agent",
                "status": "running",
                "summary": "Reviewing MCX and Forex SMC market structure labels.",
            },
            {
                "agent": "Architecture Agent",
                "status": "waiting",
                "summary": "Waiting for market intelligence context.",
            },
            {
                "agent": "Risk Governance Agent",
                "status": "waiting",
                "summary": "Pending architecture and market intelligence output.",
            },
            {
                "agent": "Delivery Planning Agent",
                "status": "waiting",
                "summary": "Pending governance review.",
            },
            {
                "agent": "Final Review Agent",
                "status": "waiting",
                "summary": "Pending all agent outputs.",
            },
        ],
        "handoffs": [
            "Requirement Agent → Market Intelligence Agent",
            "Market Intelligence Agent analyzing live market context",
        ],
        "band": band_status,
    }


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
