from fastapi import FastAPI

from app.api.agent_routes import router as agent_router
from app.api.log_routes import router as log_router
from app.api.market_routes import router as market_router
from app.api.smc_routes import router as smc_router
from app.db import DatabaseUnavailable, seed_mock_market_data

app = FastAPI(title="Quasar Enterprise AI Delivery Swarm")

app.include_router(market_router, prefix="/market", tags=["Market"])
app.include_router(smc_router, prefix="/smc", tags=["SMC"])
app.include_router(agent_router, prefix="/agents", tags=["Agents"])
app.include_router(log_router, prefix="/logs", tags=["Logs"])


@app.on_event("startup")
def seed_day_1_mock_data():
    try:
        seed_mock_market_data()
    except DatabaseUnavailable as exc:
        print(f"Skipping Day-1 DB seed: {exc}")


@app.get("/health")
def health():
    return {"status": "healthy", "service": "quasar-backend"}
