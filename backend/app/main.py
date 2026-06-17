import os

from fastapi import FastAPI

from app.api.agent_routes import router as agent_router
from app.api.intelligence_routes import router as intelligence_router
from app.api.log_routes import router as log_router
from app.api.market_routes import router as market_router
from app.api.smc_routes import router as smc_router
from app.api.submission_routes import router as submission_router
from app.data.ingestion_service import append_log, refresh_market_structure
from app.data.scheduler import (
    start_missing_candle_fill_scheduler,
    start_twelvedata_scheduler,
    start_zerodha_scheduler,
    stop_missing_candle_fill_scheduler,
    stop_twelvedata_scheduler,
    stop_zerodha_scheduler,
)
from app.db import (
    DatabaseUnavailable,
    ensure_market_candle_metadata_columns,
)
from app.services.market_memory_engine import ensure_market_memory_table
from app.services.specialist_response_store import ensure_specialist_response_table

app = FastAPI(title="Quasar Enterprise AI Delivery Swarm")

app.include_router(market_router, prefix="/market", tags=["Market"])
app.include_router(smc_router, prefix="/smc", tags=["SMC"])
app.include_router(agent_router, prefix="/agents", tags=["Agents"])
app.include_router(log_router, prefix="/logs", tags=["Logs"])
app.include_router(intelligence_router, prefix="/intelligence", tags=["Intelligence"])
app.include_router(submission_router, prefix="/submission", tags=["Submission"])


@app.on_event("startup")
async def startup_services():
    twelvedata_configured = bool(os.getenv("TWELVEDATA_API_KEY", ""))
    zerodha_configured = bool(
        os.getenv("ZERODHA_API_KEY", "") and os.getenv("ZERODHA_ACCESS_TOKEN", "")
    )
    band_enabled = os.getenv("BAND_ENABLED", "false")
    band_configured = bool(
        band_enabled.lower() == "true"
        and os.getenv("BAND_AGENT_ID", "")
        and os.getenv("BAND_API_KEY", "")
        and os.getenv("BAND_BASE_URL", "")
    )
    append_log(
        "backend.log",
        (
            f"USE_MOCK_DATA={os.getenv('USE_MOCK_DATA', 'true')} "
            f"TWELVEDATA configured: {str(twelvedata_configured).lower()} "
            f"ZERODHA configured: {str(zerodha_configured).lower()} "
            f"BAND_ENABLED={band_enabled} "
            f"BAND configured: {str(band_configured).lower()}"
        ),
    )

    try:
        ensure_market_candle_metadata_columns()
        ensure_market_memory_table()
        ensure_specialist_response_table()
        refresh_market_structure()
    except DatabaseUnavailable as exc:
        print(f"Skipping startup DB refresh: {exc}")

    start_twelvedata_scheduler()
    start_zerodha_scheduler()
    start_missing_candle_fill_scheduler()


@app.on_event("shutdown")
async def shutdown_background_tasks():
    await stop_missing_candle_fill_scheduler()
    await stop_twelvedata_scheduler()
    await stop_zerodha_scheduler()


@app.get("/health")
def health():
    return {"status": "healthy", "service": "quasar-backend"}
