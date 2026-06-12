from fastapi import APIRouter

router = APIRouter()


@router.get("/workflow-status")
def workflow_status():
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
    }
