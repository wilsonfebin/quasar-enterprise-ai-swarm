from fastapi import APIRouter, Query

from app.services.submission_readiness_service import (
    build_submission_readiness_snapshot,
)

router = APIRouter()


@router.get("/readiness")
def submission_readiness(
    market: str = Query("MCX"),
    instrument: str = Query("NATURALGAS"),
):
    return build_submission_readiness_snapshot(market=market, instrument=instrument)
