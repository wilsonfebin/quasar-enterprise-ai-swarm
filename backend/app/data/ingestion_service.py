import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.data.twelvedata_client import (
    TwelveDataClient,
    TwelveDataCredentialsMissing,
)
from app.data.zerodha_client import ZerodhaClient, ZerodhaCredentialsMissing
from app.data.candle_aggregator import aggregate_1m_candles
from app.db import (
    fetch_matching_market_candle,
    insert_market_candle,
    insert_market_candles_bulk,
)
from app.strategy.smc_label_engine import generate_smc_labels

LOG_DIR = Path("logs")


def append_log(log_name, message):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with (LOG_DIR / log_name).open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")


def twelvedata_symbol_forex():
    return os.getenv("TWELVEDATA_SYMBOL_FOREX", "XAUUSD")


def zerodha_mcx_instrument():
    return os.getenv("ZERODHA_MCX_INSTRUMENT", "NATURALGAS")


def normalize_candle(candle):
    return {
        "instrument": candle["instrument"].upper(),
        "market_type": candle["market_type"].upper(),
        "source": candle["source"].upper(),
        "timeframe": candle["timeframe"],
        "ts": candle["ts"],
        "fetched_at": candle.get("fetched_at") or datetime.now(timezone.utc),
        "open": float(candle["open"]),
        "high": float(candle["high"]),
        "low": float(candle["low"]),
        "close": float(candle["close"]),
        "volume": float(candle.get("volume") or 0),
    }


def save_ingested_candle(candle, skip_duplicates=False):
    normalized = normalize_candle(candle)
    if skip_duplicates:
        existing = fetch_matching_market_candle(normalized)
        if existing:
            append_log(
                "backend.log",
                (
                    "Duplicate candle skipped "
                    f"{existing['market_type']} {existing['instrument']} "
                    f"{existing['timeframe']} source={existing['source']} "
                    f"timestamp={existing['timestamp']} id={existing['id']}"
                ),
            )
            return {"duplicate": True, "candle": existing}

    inserted = insert_market_candle(normalized)
    append_log(
        "backend.log",
        (
            "Inserted candle "
            f"{inserted['market_type']} {inserted['instrument']} "
            f"{inserted['timeframe']} source={inserted['source']} id={inserted['id']}"
        ),
    )
    return {"duplicate": False, "candle": inserted}


def refresh_market_structure():
    aggregate_result = aggregate_1m_candles()
    label_result = generate_smc_labels()
    append_log(
        "backend.log",
        (
            "Refreshed market structure "
            f"aggregated={aggregate_result['inserted_count']} "
            f"labels={label_result['inserted_count']}"
        ),
    )
    return {
        "aggregation": aggregate_result,
        "labels": label_result,
    }


def compact_market_structure_result(result):
    if not result:
        return None
    aggregation = result.get("aggregation", {})
    labels = result.get("labels", {})
    return {
        "aggregation": {
            "status": aggregation.get("status"),
            "timeframes": aggregation.get("timeframes", []),
            "inserted_count": aggregation.get("inserted_count", 0),
        },
        "labels": {
            "status": labels.get("status"),
            "timeframes": labels.get("timeframes", []),
            "label_types": labels.get("label_types", []),
            "inserted_count": labels.get("inserted_count", 0),
        },
    }


def build_mock_candles():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    fetched_at = datetime.now(timezone.utc)
    minute_offset = now.minute % 10

    return [
        {
            "instrument": "NATURALGAS",
            "market_type": "MCX",
            "source": "MOCK_INGEST",
            "timeframe": "1m",
            "ts": now,
            "fetched_at": fetched_at,
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
            "fetched_at": fetched_at,
            "open": 2340.0 + minute_offset * 0.2,
            "high": 2342.0 + minute_offset * 0.2,
            "low": 2338.7 + minute_offset * 0.2,
            "close": 2341.1 + minute_offset * 0.2,
            "volume": 0,
        },
    ]


def ingest_mock_candles():
    inserted = [save_ingested_candle(candle)["candle"] for candle in build_mock_candles()]
    market_structure = refresh_market_structure()
    append_log("mcx_live.log", "Mock MCX NATURALGAS candle ingested")
    append_log("forex_live.log", "Mock Forex XAUUSD candle ingested")
    return {
        "status": "ok",
        "mode": "mock",
        "inserted": inserted,
        "market_structure": market_structure,
    }


def ingest_twelvedata_forex():
    if not os.getenv("TWELVEDATA_API_KEY", ""):
        message = "TWELVEDATA_API_KEY is not configured; TwelveData ingestion skipped"
        append_log("forex_live.log", message)
        append_log("backend.log", message)
        return {"status": "skipped", "message": message}

    try:
        requested_symbol = twelvedata_symbol_forex()
        append_log(
            "forex_live.log",
            f"TwelveData request symbol={requested_symbol} instrument=XAUUSD",
        )
        candle = TwelveDataClient(symbol=requested_symbol).fetch_latest_forex_candle()
        provider = candle.get("provider", {})
        provider_query_symbol = provider.get("provider_query_symbol", requested_symbol)
        returned_symbol = provider.get("returned_symbol", requested_symbol)
        raw_datetime = provider.get("raw_datetime", "")
        timestamp_corrected = bool(provider.get("timestamp_corrected"))
        timestamp_correction_reason = provider.get("timestamp_correction_reason", "")
        append_log(
            "forex_live.log",
            (
                "TwelveData response "
                f"requested_symbol={requested_symbol} "
                f"provider_query_symbol={provider_query_symbol} "
                f"returned_symbol={returned_symbol} "
                f"raw_datetime={raw_datetime or 'unknown'} "
                f"timestamp_corrected={timestamp_corrected} "
                f"correction_reason={timestamp_correction_reason or 'none'} "
                "source=TWELVEDATA"
            ),
        )
        if timestamp_corrected:
            correction_message = (
                "TwelveData provider timestamp corrected "
                f"raw_datetime={raw_datetime or 'unknown'} "
                f"reason={timestamp_correction_reason}"
            )
            append_log("forex.log", correction_message)
            append_log("backend.log", correction_message)
        save_result = save_ingested_candle(candle, skip_duplicates=True)
        inserted = save_result["candle"]
        if save_result["duplicate"]:
            append_log(
                "forex.log",
                f"TwelveData duplicate skipped timestamp={inserted['timestamp']}",
            )
            append_log(
                "forex_live.log",
                f"TwelveData duplicate skipped timestamp={inserted['timestamp']}",
            )
            return {
                "status": "duplicate_skipped",
                "source": "TWELVEDATA",
                "requested_symbol": requested_symbol,
                "returned_symbol": returned_symbol,
                "provider_raw_datetime": raw_datetime,
                "timestamp_corrected": timestamp_corrected,
                "timestamp_correction_reason": timestamp_correction_reason,
                "inserted": None,
                "existing": inserted,
                "market_structure": None,
            }

        market_structure = refresh_market_structure()
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
    append_log("forex.log", f"TwelveData ingest success id={inserted['id']}")
    return {
        "status": "ok",
        "source": "TWELVEDATA",
        "requested_symbol": requested_symbol,
        "returned_symbol": returned_symbol,
        "provider_raw_datetime": raw_datetime,
        "timestamp_corrected": timestamp_corrected,
        "timestamp_correction_reason": timestamp_correction_reason,
        "inserted": inserted,
        "market_structure": market_structure,
    }


def backfill_twelvedata_forex(days=30, chunk_days=3, dry_run=False):
    if not os.getenv("TWELVEDATA_API_KEY", ""):
        message = "TWELVEDATA_API_KEY is not configured; TwelveData backfill skipped"
        append_log("forex.log", message)
        append_log("backend.log", message)
        return {"status": "skipped", "message": message}

    days = max(1, min(int(days), 90))
    chunk_days = max(1, min(int(chunk_days), 5))
    end_at = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start_at = end_at - timedelta(days=days)
    requested_symbol = twelvedata_symbol_forex()
    client = TwelveDataClient(symbol=requested_symbol)

    append_log(
        "forex.log",
        (
            "TwelveData backfill started "
            f"symbol={requested_symbol} days={days} chunk_days={chunk_days} "
            f"dry_run={dry_run}"
        ),
    )
    append_log(
        "backend.log",
        f"TwelveData backfill started symbol={requested_symbol} days={days}",
    )

    chunks = []
    cursor = start_at
    total_returned = 0
    total_accepted = 0
    total_rejected_future = 0
    total_inserted = 0
    total_duplicates = 0

    try:
        while cursor < end_at:
            chunk_end = min(cursor + timedelta(days=chunk_days), end_at)
            result = client.fetch_forex_candles(cursor, chunk_end)
            candles = [normalize_candle(candle) for candle in result["candles"]]
            total_returned += result["returned_count"]
            total_accepted += result["accepted_count"]
            total_rejected_future += result["rejected_future_count"]

            if dry_run:
                insert_result = {
                    "inserted_count": 0,
                    "duplicate_count": 0,
                    "inserted_ids": [],
                }
            else:
                insert_result = insert_market_candles_bulk(candles)
                total_inserted += insert_result["inserted_count"]
                total_duplicates += insert_result["duplicate_count"]

            chunk_summary = {
                "start_at": result["start_at"],
                "end_at": result["end_at"],
                "returned_count": result["returned_count"],
                "accepted_count": result["accepted_count"],
                "rejected_future_count": result["rejected_future_count"],
                "inserted_count": insert_result["inserted_count"],
                "duplicate_count": insert_result["duplicate_count"],
            }
            chunks.append(chunk_summary)
            append_log(
                "forex.log",
                (
                    "TwelveData backfill chunk "
                    f"start={chunk_summary['start_at']} end={chunk_summary['end_at']} "
                    f"returned={chunk_summary['returned_count']} "
                    f"inserted={chunk_summary['inserted_count']} "
                    f"duplicates={chunk_summary['duplicate_count']} "
                    f"future_rejected={chunk_summary['rejected_future_count']}"
                ),
            )
            cursor = chunk_end

        market_structure = (
            None if dry_run else compact_market_structure_result(refresh_market_structure())
        )
    except Exception as exc:
        message = f"TwelveData backfill failed: {exc}"
        append_log("forex.log", message)
        append_log("backend.log", message)
        return {"status": "error", "message": message, "chunks": chunks}

    append_log(
        "forex.log",
        (
            "TwelveData backfill completed "
            f"returned={total_returned} accepted={total_accepted} "
            f"inserted={total_inserted} duplicates={total_duplicates} "
            f"future_rejected={total_rejected_future}"
        ),
    )
    append_log(
        "backend.log",
        (
            "TwelveData backfill completed "
            f"inserted={total_inserted} duplicates={total_duplicates}"
        ),
    )
    return {
        "status": "dry_run" if dry_run else "ok",
        "source": "TWELVEDATA",
        "requested_symbol": requested_symbol,
        "days": days,
        "chunk_days": chunk_days,
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "total_returned": total_returned,
        "total_accepted": total_accepted,
        "total_inserted": total_inserted,
        "total_duplicates": total_duplicates,
        "total_rejected_future": total_rejected_future,
        "chunks": chunks,
        "market_structure": market_structure,
    }


def backfill_zerodha_mcx(days=60, chunk_days=5, dry_run=False):
    try:
        client = ZerodhaClient()
        client.ensure_credentials()
    except ZerodhaCredentialsMissing as exc:
        message = f"{exc}; Zerodha MCX backfill skipped"
        append_log("mcx_live.log", message)
        append_log("backend.log", message)
        return {"status": "skipped", "message": message}

    days = max(1, min(int(days), 90))
    chunk_days = max(1, min(int(chunk_days), 7))
    end_at = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start_at = end_at - timedelta(days=days)
    instrument = zerodha_mcx_instrument()
    configured_token = os.getenv("ZERODHA_MCX_INSTRUMENT_TOKEN", "").strip() or None
    configured_symbol = os.getenv("ZERODHA_MCX_TRADINGSYMBOL", "").strip() or None

    append_log(
        "mcx_live.log",
        (
            "Zerodha MCX backfill started "
            f"instrument={instrument} days={days} chunk_days={chunk_days} "
            f"dry_run={dry_run}"
        ),
    )
    append_log(
        "backend.log",
        f"Zerodha MCX backfill started instrument={instrument} days={days}",
    )

    chunks = []
    cursor = start_at
    total_returned = 0
    total_accepted = 0
    total_rejected_future = 0
    total_inserted = 0
    total_duplicates = 0
    instrument_meta = {}

    try:
        while cursor < end_at:
            chunk_end = min(cursor + timedelta(days=chunk_days), end_at)
            result = client.fetch_mcx_candles(
                cursor,
                chunk_end,
                instrument=instrument,
                instrument_token=configured_token,
                tradingsymbol=configured_symbol,
            )
            instrument_meta = {
                "instrument_token": result.get("instrument_token"),
                "tradingsymbol": result.get("tradingsymbol"),
                "expiry": result.get("expiry"),
                "instrument_source": result.get("instrument_source"),
            }
            candles = [normalize_candle(candle) for candle in result["candles"]]
            total_returned += result["returned_count"]
            total_accepted += result["accepted_count"]
            total_rejected_future += result["rejected_future_count"]

            if dry_run:
                insert_result = {
                    "inserted_count": 0,
                    "duplicate_count": 0,
                    "inserted_ids": [],
                }
            else:
                insert_result = insert_market_candles_bulk(candles)
                total_inserted += insert_result["inserted_count"]
                total_duplicates += insert_result["duplicate_count"]

            chunk_summary = {
                "start_at": result["start_at"],
                "end_at": result["end_at"],
                "returned_count": result["returned_count"],
                "accepted_count": result["accepted_count"],
                "rejected_future_count": result["rejected_future_count"],
                "inserted_count": insert_result["inserted_count"],
                "duplicate_count": insert_result["duplicate_count"],
            }
            chunks.append(chunk_summary)
            append_log(
                "mcx_live.log",
                (
                    "Zerodha MCX backfill chunk "
                    f"start={chunk_summary['start_at']} end={chunk_summary['end_at']} "
                    f"returned={chunk_summary['returned_count']} "
                    f"inserted={chunk_summary['inserted_count']} "
                    f"duplicates={chunk_summary['duplicate_count']} "
                    f"future_rejected={chunk_summary['rejected_future_count']}"
                ),
            )
            cursor = chunk_end

        market_structure = (
            None if dry_run else compact_market_structure_result(refresh_market_structure())
        )
    except Exception as exc:
        message = f"Zerodha MCX backfill failed: {exc}"
        append_log("mcx_live.log", message)
        append_log("backend.log", message)
        return {
            "status": "error",
            "message": message,
            "instrument": instrument,
            "instrument_meta": instrument_meta,
            "chunks": chunks,
        }

    append_log(
        "mcx_live.log",
        (
            "Zerodha MCX backfill completed "
            f"returned={total_returned} accepted={total_accepted} "
            f"inserted={total_inserted} duplicates={total_duplicates} "
            f"future_rejected={total_rejected_future}"
        ),
    )
    append_log(
        "backend.log",
        (
            "Zerodha MCX backfill completed "
            f"inserted={total_inserted} duplicates={total_duplicates}"
        ),
    )
    return {
        "status": "dry_run" if dry_run else "ok",
        "source": "ZERODHA",
        "instrument": instrument,
        "instrument_meta": instrument_meta,
        "days": days,
        "chunk_days": chunk_days,
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "total_returned": total_returned,
        "total_accepted": total_accepted,
        "total_inserted": total_inserted,
        "total_duplicates": total_duplicates,
        "total_rejected_future": total_rejected_future,
        "chunks": chunks,
        "market_structure": market_structure,
    }


def ingest_zerodha_mcx():
    try:
        candle = ZerodhaClient().fetch_latest_mcx_candle()
        save_result = save_ingested_candle(candle, skip_duplicates=True)
    except ZerodhaCredentialsMissing as exc:
        message = f"{exc}; Zerodha MCX ingestion skipped"
        append_log("mcx_live.log", message)
        append_log("backend.log", message)
        return {"status": "skipped", "message": message}
    except Exception as exc:
        message = f"Zerodha MCX ingestion failed: {exc}"
        append_log("mcx_live.log", message)
        append_log("backend.log", message)
        return {"status": "error", "message": message}

    inserted = save_result["candle"]
    if save_result["duplicate"]:
        append_log("mcx_live.log", f"Zerodha duplicate skipped timestamp={inserted['timestamp']}")
        return {
            "status": "duplicate_skipped",
            "source": "ZERODHA",
            "inserted": None,
            "existing": inserted,
        }

    market_structure = refresh_market_structure()
    append_log("mcx_live.log", f"Zerodha MCX candle ingested id={inserted['id']}")
    return {
        "status": "ok",
        "source": "ZERODHA",
        "inserted": inserted,
        "market_structure": compact_market_structure_result(market_structure),
    }
