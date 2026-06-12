from datetime import datetime, timezone
from fastapi import APIRouter, Query

from app.db import (
    DatabaseUnavailable,
    fetch_latest_market_snapshot,
    fetch_market_candles,
)

router = APIRouter()


def fallback_latest_market_data():
    now = datetime.now(timezone.utc).isoformat()

    return {
        "mcx": {
            "instrument": "NATURALGAS",
            "market_type": "MCX",
            "source": "MOCK_MCX",
            "timeframe": "1m",
            "timestamp": now,
            "candle": {
                "open": 297.2,
                "high": 298.1,
                "low": 296.8,
                "close": 297.6,
                "volume": 12500,
            },
            "smc_labels": [
                {"label": "BOS_BULLISH", "direction": "BULLISH", "confidence": 0.81},
                {"label": "FVG_BULLISH", "direction": "BULLISH", "confidence": 0.73},
            ],
            "status": "MOCK_FALLBACK_DB_UNAVAILABLE",
        },
        "forex": {
            "instrument": "XAUUSD",
            "market_type": "FOREX",
            "source": "MOCK_FOREX",
            "timeframe": "1m",
            "timestamp": now,
            "candle": {
                "open": 2338.2,
                "high": 2341.5,
                "low": 2336.9,
                "close": 2340.4,
                "volume": 0,
            },
            "smc_labels": [
                {"label": "LIQUIDITY_SWEEP_HIGH", "direction": "BEARISH", "confidence": 0.78},
                {"label": "CHOCH_BEARISH", "direction": "BEARISH", "confidence": 0.69},
            ],
            "status": "MOCK_FALLBACK_DB_UNAVAILABLE",
        },
    }


@router.get("/latest")
def latest_market_data():
    try:
        snapshot = fetch_latest_market_snapshot()
        if {"mcx", "forex"}.issubset(snapshot):
            return snapshot
    except DatabaseUnavailable:
        pass

    return fallback_latest_market_data()


@router.get("/candles")
def market_candles(
    market_type: str = Query("MCX"),
    instrument: str = Query("NATURALGAS"),
    timeframe: str = Query("1m"),
    limit: int = Query(50, ge=1, le=500),
):
    try:
        candles = fetch_market_candles(
            market_type=market_type.upper(),
            instrument=instrument.upper(),
            timeframe=timeframe,
            limit=limit,
        )
        return {"status": "DB", "candles": candles}
    except DatabaseUnavailable:
        latest = fallback_latest_market_data()
        key = "mcx" if market_type.upper() == "MCX" else "forex"
        fallback = latest.get(key)
        if not fallback:
            return {"status": "MOCK_FALLBACK_DB_UNAVAILABLE", "candles": []}

        return {
            "status": "MOCK_FALLBACK_DB_UNAVAILABLE",
            "candles": [
                {
                    "instrument": fallback["instrument"],
                    "market_type": fallback["market_type"],
                    "source": fallback["source"],
                    "timeframe": fallback["timeframe"],
                    "timestamp": fallback["timestamp"],
                    **fallback["candle"],
                }
            ],
        }
