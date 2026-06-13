import os

from fastapi import FastAPI

from app.api.agent_routes import router as agent_router
from app.api.log_routes import router as log_router
from app.api.market_routes import router as market_router
from app.api.smc_routes import router as smc_router
from app.data.ingestion_service import append_log, refresh_market_structure
from app.db import DatabaseUnavailable, seed_mock_market_data

app = FastAPI(title="Quasar Enterprise AI Delivery Swarm")

app.include_router(market_router, prefix="/market", tags=["Market"])
app.include_router(smc_router, prefix="/smc", tags=["SMC"])
app.include_router(agent_router, prefix="/agents", tags=["Agents"])
app.include_router(log_router, prefix="/logs", tags=["Logs"])


@app.on_event("startup")
def seed_day_1_mock_data():
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
        seed_mock_market_data()
        refresh_market_structure()
    except DatabaseUnavailable as exc:
        print(f"Skipping Day-1 DB seed: {exc}")


@app.get("/health")
def health():
    return {"status": "healthy", "service": "quasar-backend"}
