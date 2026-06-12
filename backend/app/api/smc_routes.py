from fastapi import APIRouter, Query

from app.api.market_routes import fallback_latest_market_data
from app.db import DatabaseUnavailable, fetch_smc_labels

router = APIRouter()
HIGHER_TIMEFRAMES = {"1H", "4H"}


@router.get("/labels")
def smc_labels(
    market_type: str = Query("MCX"),
    instrument: str = Query("NATURALGAS"),
    timeframe: str = Query("1m"),
    limit: int = Query(50, ge=1, le=500),
):
    market_type = market_type.upper()
    instrument = instrument.upper()

    try:
        labels = fetch_smc_labels(
            market_type=market_type,
            instrument=instrument,
            timeframe=timeframe,
            limit=limit,
        )
        if not labels and timeframe in HIGHER_TIMEFRAMES:
            return {
                "status": "EMPTY",
                "message": "Insufficient candles for selected timeframe",
                "labels": [],
            }
        return {"status": "DB", "labels": labels}
    except DatabaseUnavailable:
        latest = fallback_latest_market_data()
        key = "mcx" if market_type == "MCX" else "forex"
        fallback = latest.get(key)
        if not fallback:
            return {"status": "MOCK_FALLBACK_DB_UNAVAILABLE", "labels": []}

        return {
            "status": "MOCK_FALLBACK_DB_UNAVAILABLE",
            "labels": [
                {
                    "instrument": fallback["instrument"],
                    "market_type": fallback["market_type"],
                    "timeframe": fallback["timeframe"],
                    "timestamp": fallback["timestamp"],
                    "label_type": label["label"],
                    "direction": label["direction"],
                    "price_level": fallback["candle"]["close"],
                    "confidence": label["confidence"],
                    "metadata": {"source": "fallback_mock"},
                }
                for label in fallback["smc_labels"]
            ],
        }
