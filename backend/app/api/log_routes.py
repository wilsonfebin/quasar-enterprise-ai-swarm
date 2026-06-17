from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter()

LOG_DIR = Path("logs")


@router.get("/{log_name}")
def read_log(log_name: str):
    allowed = {
        "mcx": "mcx.log",
        "forex": "forex.log",
        "backend": "backend.log",
        "agent": "agent_workflow.log",
    }

    filename = allowed.get(log_name)
    if not filename:
        return {"error": "invalid log name"}

    path = LOG_DIR / filename

    if not path.exists():
        if log_name == "agent":
            return {"lines": _persisted_agent_workflow_lines()}
        return {"lines": ["No logs yet."]}

    lines = path.read_text().splitlines()[-100:]
    if log_name == "agent" and _agent_log_is_static(lines):
        return {"lines": _persisted_agent_workflow_lines()}
    return {"lines": lines}


def _agent_log_is_static(lines: list[str]) -> bool:
    text = "\n".join(lines)
    return bool(lines) and "Requirement Agent completed scope extraction" in text


def _persisted_agent_workflow_lines() -> list[str]:
    try:
        from app.services.specialist_response_store import get_latest_specialist_responses

        latest = get_latest_specialist_responses()
    except Exception as exc:
        return [f"Agent workflow logs unavailable: {exc}"]

    workflow_id = str(latest.get("workflow_run_id") or "latest")
    records: list[dict[str, Any]] = list(latest.get("specialists") or [])
    final_review = latest.get("final_review") or {}
    if final_review:
        records.append(final_review)
    if not records:
        return [
            "No persisted specialist workflow responses yet. Run Agent Swarm Review once to populate this audit trail."
        ]

    lines = [f"Workflow {workflow_id} persisted specialist audit trail"]
    records.sort(key=lambda item: str(item.get("created_at") or ""))
    for item in records:
        created_at = item.get("created_at") or ""
        specialist = item.get("specialist_name") or "Specialist"
        state = item.get("state") or item.get("finding") or "completed"
        source = item.get("response_source") or "persisted"
        confidence = item.get("confidence", "")
        confidence_text = f" confidence={confidence}" if confidence != "" else ""
        lines.append(
            f"[{created_at}] {specialist} completed state={state} source={source}{confidence_text}"
        )
    return lines[-100:]
