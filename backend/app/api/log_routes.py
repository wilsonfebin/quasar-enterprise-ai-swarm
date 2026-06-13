from pathlib import Path
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
        return {"lines": ["No logs yet."]}

    lines = path.read_text().splitlines()[-100:]
    return {"lines": lines}
