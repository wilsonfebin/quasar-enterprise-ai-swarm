import os
from datetime import datetime, timezone
from pathlib import Path

from app.data.twelvedata_client import (
    TwelveDataClient,
    TwelveDataCredentialsMissing,
)
from app.data.zerodha_client import ZerodhaClient, ZerodhaCredentialsMissing
from app.db import insert_market_candle

LOG_DIR = Path("logs")


def append_log(log_name, message):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with (LOG_DIR / log_name).open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")


def normalize_candle(candle):
    return {
        "instrument": candle["instrument"].upper(),
        "market_type": candle["market_type"].upper(),
        "source": candle["source"].upper(),
        "timeframe": candle["timeframe"],
        "ts": candle["ts"],
        "open": float(candle["open"]),
        "high": float(candle["high"]),
        "low": float(candle["low"]),
        "close": float(candle["close"]),
        "volume": float(candle.get("volume") or 0),
    }


def save_ingested_candle(candle):
    normalized = normalize_candle(candle)
    inserted = insert_market_candle(normalized)
    append_log(
        "backend.log",
        (
            "Inserted candle "
            f"{inserted['market_type']} {inserted['instrument']} "
            f"{inserted['timeframe']} source={inserted['source']} id={inserted['id']}"
        ),
    )
    return inserted


def build_mock_candles():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    minute_offset = now.minute % 10

    return [
        {
            "instrument": "NATURALGAS",
            "market_type": "MCX",
            "source": "MOCK_INGEST",
            "timeframe": "1m",
            "ts": now,
            "open": 297.0 + minute_offset * 0.1,
            "high": 298.0 + minute_offset * 0.1,
            "low": 296.6 + minute_offset * 0.1,
            "close": 297.5 + minute_offset * 0.1,
            "volume": 12600 + minute_offset * 100,
        },
        {
            "instrument": "XAUUSD",
            "market_type": "FOREX",
            "source": "MOCK_INGEST",
            "timeframe": "1m",
            "ts": now,
            "open": 2340.0 + minute_offset * 0.2,
            "high": 2342.0 + minute_offset * 0.2,
            "low": 2338.7 + minute_offset * 0.2,
            "close": 2341.1 + minute_offset * 0.2,
            "volume": 0,
        },
    ]


def ingest_mock_candles():
    inserted = [save_ingested_candle(candle) for candle in build_mock_candles()]
    append_log("mcx_live.log", "Mock MCX NATURALGAS candle ingested")
    append_log("forex_live.log", "Mock Forex XAUUSD candle ingested")
    return {
        "status": "ok",
        "mode": "mock",
        "inserted": inserted,
    }


def ingest_twelvedata_forex():
    if not os.getenv("TWELVEDATA_API_KEY", ""):
        message = "TWELVEDATA_API_KEY is not configured; TwelveData ingestion skipped"
        append_log("forex_live.log", message)
        append_log("backend.log", message)
        return {"status": "skipped", "message": message}

    try:
        candle = TwelveDataClient().fetch_latest_forex_candle()
        inserted = save_ingested_candle(candle)
    except TwelveDataCredentialsMissing as exc:
        message = str(exc)
        append_log("forex_live.log", message)
        append_log("backend.log", message)
        return {"status": "skipped", "message": message}
    except Exception as exc:
        message = f"TwelveData ingestion failed: {exc}"
        append_log("forex_live.log", message)
        append_log("backend.log", message)
        return {"status": "error", "message": message}

    append_log("forex_live.log", f"TwelveData Forex candle ingested id={inserted['id']}")
    return {"status": "ok", "source": "TWELVEDATA", "inserted": inserted}


def ingest_zerodha_mcx():
    try:
        ZerodhaClient().ensure_credentials()
    except ZerodhaCredentialsMissing as exc:
        message = f"{exc}; Zerodha MCX ingestion skipped"
        append_log("mcx_live.log", message)
        append_log("backend.log", message)
        return {"status": "skipped", "message": message}

    message = "Zerodha credentials found, but live MCX ingestion is not enabled in Phase 2"
    append_log("mcx_live.log", message)
    append_log("backend.log", message)
    return {"status": "placeholder", "message": message}
