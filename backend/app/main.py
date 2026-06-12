import os

from fastapi import FastAPI

from app.api.agent_routes import router as agent_router
from app.api.log_routes import router as log_router
from app.api.market_routes import router as market_router
from app.api.smc_routes import router as smc_router
from app.data.ingestion_service import append_log
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
    append_log(
        "backend.log",
        (
            f"USE_MOCK_DATA={os.getenv('USE_MOCK_DATA', 'true')} "
            f"TWELVEDATA configured: {str(twelvedata_configured).lower()} "
            f"ZERODHA configured: {str(zerodha_configured).lower()}"
        ),
    )

    try:
        seed_mock_market_data()
    except DatabaseUnavailable as exc:
        print(f"Skipping Day-1 DB seed: {exc}")


@app.get("/health")
def health():
    return {"status": "healthy", "service": "quasar-backend"}
