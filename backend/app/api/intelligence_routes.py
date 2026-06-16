from fastapi import APIRouter, Query

from app.db import DatabaseUnavailable
from app.services.market_memory_engine import (
    get_memory_summary,
    get_transition_matrix,
)

router = APIRouter()


@router.get("/memory")
def intelligence_memory(market: str | None = Query(default=None)):
    try:
        return get_memory_summary(market=market)
    except DatabaseUnavailable as exc:
        return {
            "status": "DB_UNAVAILABLE",
            "message": str(exc),
            "regime_statistics": {},
            "transition_statistics": {},
            "persistence_scores": {},
            "recovery_scores": {},
            "failure_scores": {},
            "sample_count": 0,
        }


@router.get("/memory/transitions")
def intelligence_memory_transitions(market: str | None = Query(default=None)):
    try:
        return get_transition_matrix(market=market)
    except DatabaseUnavailable as exc:
        return {
            "status": "DB_UNAVAILABLE",
            "message": str(exc),
        }
