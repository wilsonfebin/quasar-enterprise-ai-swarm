import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.data.ingestion_service import (
    append_log,
    backfill_twelvedata_forex,
    backfill_zerodha_mcx,
    compact_market_structure_result,
    ingest_twelvedata_forex,
    ingest_zerodha_mcx,
    refresh_market_structure,
    twelvedata_symbol_forex,
    zerodha_mcx_instrument,
)


TWELVEDATA_INGESTION_STATE: dict[str, Any] = {
    "running": False,
    "enabled": False,
    "source": "TWELVEDATA",
    "symbol": "XAUUSD",
    "interval_seconds": 60,
    "last_run_at": "",
    "next_run_at": "",
    "last_success_at": "",
    "last_inserted_timestamp": "",
    "exchange_candle_time": "",
    "fetched_at": "",
    "inserted_at": "",
    "last_price": None,
    "last_status": "stopped",
    "last_error": "",
    "market_open": False,
    "market_closed": True,
    "waiting_for_next_session": False,
    "stale_data_warning": "",
    "market_session": "Market Closed",
    "freshness_seconds": None,
    "freshness_label": "",
    "freshness_status": "unknown",
    "analysis_readiness": "Not Ready",
    "provider_raw_datetime": "",
    "timestamp_corrected": False,
    "timestamp_correction_reason": "",
    "success_count": 0,
    "failure_count": 0,
    "duplicate_skipped_count": 0,
}

_scheduler_task: asyncio.Task | None = None

ZERODHA_INGESTION_STATE: dict[str, Any] = {
    "running": False,
    "enabled": False,
    "source": "ZERODHA",
    "instrument": "NATURALGAS",
    "interval_seconds": 60,
    "last_run_at": "",
    "next_run_at": "",
    "last_success_at": "",
    "last_inserted_timestamp": "",
    "exchange_candle_time": "",
    "fetched_at": "",
    "inserted_at": "",
    "last_price": None,
    "last_status": "stopped",
    "last_error": "",
    "market_open": False,
    "market_closed": True,
    "waiting_for_next_session": False,
    "stale_data_warning": "",
    "market_session": "Market Closed",
    "freshness_seconds": None,
    "freshness_label": "",
    "freshness_status": "unknown",
    "analysis_readiness": "Not Ready",
    "success_count": 0,
    "failure_count": 0,
    "duplicate_skipped_count": 0,
    "no_data_count": 0,
    "credential_error_count": 0,
}

_zerodha_scheduler_task: asyncio.Task | None = None

MISSING_CANDLE_FILL_STATE: dict[str, Any] = {
    "running": False,
    "enabled": True,
    "interval_seconds": 300,
    "lookback_days": 1,
    "last_run_at": "",
    "next_run_at": "",
    "last_success_at": "",
    "last_status": "stopped",
    "last_error": "",
    "forex_status": "",
    "mcx_status": "",
    "forex_inserted": 0,
    "mcx_inserted": 0,
    "structure_refreshed": False,
    "success_count": 0,
    "failure_count": 0,
}

_missing_candle_fill_task: asyncio.Task | None = None


def append_mcx_log(message: str) -> None:
    append_log("mcx_live.log", message)
    append_log("mcx.log", message)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _env_enabled() -> bool:
    return os.getenv("TWELVEDATA_AUTO_INGEST", "false").lower() == "true"


def _env_interval() -> int:
    try:
        return max(5, int(os.getenv("TWELVEDATA_INGEST_INTERVAL_SECONDS", "60")))
    except ValueError:
        return 60


def _zerodha_env_enabled() -> bool:
    return os.getenv("ZERODHA_AUTO_INGEST", "false").lower() == "true"


def _zerodha_env_interval() -> int:
    try:
        return max(5, int(os.getenv("ZERODHA_INGEST_INTERVAL_SECONDS", "60")))
    except ValueError:
        return 60


def _missing_candle_fill_enabled() -> bool:
    return os.getenv("MISSING_CANDLE_FILL_ENABLED", "true").lower() == "true"


def _missing_candle_fill_interval() -> int:
    try:
        return max(
            60,
            int(os.getenv("MISSING_CANDLE_FILL_INTERVAL_SECONDS", "300")),
        )
    except ValueError:
        return 300


def _missing_candle_fill_days() -> int:
    try:
        return max(1, min(int(os.getenv("MISSING_CANDLE_FILL_DAYS", "1")), 7))
    except ValueError:
        return 1


def _forex_market_open(now: datetime | None = None) -> bool:
    current = now or _utc_now()
    return current.weekday() < 5


def _mcx_market_open(now: datetime | None = None) -> bool:
    ist = timezone(timedelta(hours=5, minutes=30))
    current = (now or _utc_now()).astimezone(ist)
    return current.weekday() < 5 and 9 <= current.hour < 24


def _stale_warning(last_timestamp: str, market_open: bool, provider_name: str) -> str:
    if not last_timestamp:
        return f"No {provider_name} candle has been ingested yet"
    try:
        parsed = datetime.fromisoformat(last_timestamp)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    age_minutes = int((_utc_now() - parsed).total_seconds() // 60)
    if market_open and age_minutes > 5:
        return f"Latest candle is stale: {age_minutes}m old"
    return ""


def _freshness_seconds(exchange_timestamp: str) -> int | None:
    if not exchange_timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(exchange_timestamp)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return int((_utc_now() - parsed).total_seconds())


def _freshness_label(seconds: int | None) -> str:
    if seconds is None:
        return ""
    if seconds < -60:
        return "provider time ahead"
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m old"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if hours < 24:
        return f"{hours}h {remaining_minutes}m old"
    days = hours // 24
    return f"{days}d old"


def _freshness_status(seconds: int | None, market_open: bool) -> str:
    if seconds is None:
        return "unknown"
    if seconds < -60:
        return "time_ahead"
    if not market_open:
        return "market_closed"
    if seconds <= 180:
        return "fresh"
    if seconds <= 900:
        return "delayed"
    return "stale"


def _analysis_readiness(seconds: int | None, market_open: bool, has_candle: bool) -> str:
    if not has_candle:
        return "Not Ready"
    if not market_open or seconds is None or seconds < -60 or seconds > 900:
        return "Weak"
    return "Weak"


def _sync_env_state() -> None:
    market_open = _forex_market_open()
    exchange_time = TWELVEDATA_INGESTION_STATE.get("exchange_candle_time", "")
    freshness_seconds = _freshness_seconds(exchange_time)
    TWELVEDATA_INGESTION_STATE.update(
        {
            "enabled": _env_enabled() or TWELVEDATA_INGESTION_STATE.get("running", False),
            "symbol": twelvedata_symbol_forex(),
            "interval_seconds": _env_interval(),
            "market_open": market_open,
            "market_closed": not market_open,
            "waiting_for_next_session": not market_open,
            "market_session": "Market Open" if market_open else "Market Closed",
            "freshness_seconds": freshness_seconds,
            "freshness_label": _freshness_label(freshness_seconds),
            "freshness_status": _freshness_status(freshness_seconds, market_open),
            "analysis_readiness": _analysis_readiness(
                freshness_seconds,
                market_open,
                bool(exchange_time),
            ),
            "stale_data_warning": _stale_warning(
                exchange_time,
                market_open,
                "TwelveData",
            ),
        }
    )


def _task_alive() -> bool:
    return _scheduler_task is not None and not _scheduler_task.done()


def _zerodha_task_alive() -> bool:
    return _zerodha_scheduler_task is not None and not _zerodha_scheduler_task.done()


def _missing_candle_fill_alive() -> bool:
    return _missing_candle_fill_task is not None and not _missing_candle_fill_task.done()


def get_twelvedata_ingestion_status() -> dict[str, Any]:
    _sync_env_state()
    worker_alive = _task_alive()
    return {
        **TWELVEDATA_INGESTION_STATE,
        "worker_alive": worker_alive,
        "task_alive": worker_alive,
        "last_tick": TWELVEDATA_INGESTION_STATE.get("last_run_at", ""),
        "last_candle": TWELVEDATA_INGESTION_STATE.get("exchange_candle_time", ""),
        "freshness": TWELVEDATA_INGESTION_STATE.get("freshness_label", ""),
        "worker_status": "running" if worker_alive else "stopped",
        "market_session": "open"
        if TWELVEDATA_INGESTION_STATE.get("market_open")
        else "closed",
    }


def _sync_zerodha_env_state() -> None:
    market_open = _mcx_market_open()
    exchange_time = ZERODHA_INGESTION_STATE.get("exchange_candle_time", "")
    freshness_seconds = _freshness_seconds(exchange_time)
    ZERODHA_INGESTION_STATE.update(
        {
            "enabled": _zerodha_env_enabled()
            or ZERODHA_INGESTION_STATE.get("running", False),
            "instrument": zerodha_mcx_instrument(),
            "interval_seconds": _zerodha_env_interval(),
            "market_open": market_open,
            "market_closed": not market_open,
            "waiting_for_next_session": not market_open,
            "market_session": "Market Open" if market_open else "Market Closed",
            "freshness_seconds": freshness_seconds,
            "freshness_label": _freshness_label(freshness_seconds),
            "freshness_status": _freshness_status(freshness_seconds, market_open),
            "analysis_readiness": _analysis_readiness(
                freshness_seconds,
                market_open,
                bool(exchange_time),
            ),
            "stale_data_warning": _stale_warning(exchange_time, market_open, "Zerodha"),
        }
    )


def get_zerodha_ingestion_status() -> dict[str, Any]:
    _sync_zerodha_env_state()
    worker_alive = _zerodha_task_alive()
    return {
        **ZERODHA_INGESTION_STATE,
        "worker_alive": worker_alive,
        "task_alive": worker_alive,
        "last_tick": ZERODHA_INGESTION_STATE.get("last_run_at", ""),
        "last_candle": ZERODHA_INGESTION_STATE.get("exchange_candle_time", ""),
        "freshness": ZERODHA_INGESTION_STATE.get("freshness_label", ""),
        "worker_status": "running" if worker_alive else "stopped",
        "market_session": "open"
        if ZERODHA_INGESTION_STATE.get("market_open")
        else "closed",
    }


def get_missing_candle_fill_status() -> dict[str, Any]:
    worker_alive = _missing_candle_fill_alive()
    MISSING_CANDLE_FILL_STATE.update(
        {
            "enabled": _missing_candle_fill_enabled()
            or MISSING_CANDLE_FILL_STATE.get("running", False),
            "interval_seconds": _missing_candle_fill_interval(),
            "lookback_days": _missing_candle_fill_days(),
        }
    )
    return {
        **MISSING_CANDLE_FILL_STATE,
        "worker_alive": worker_alive,
        "task_alive": worker_alive,
        "worker_status": "running" if worker_alive else "stopped",
    }


def run_twelvedata_ingest_once() -> dict[str, Any]:
    _sync_env_state()
    now = _utc_now()
    append_log(
        "forex.log",
        f"TwelveData scheduler tick market_open={TWELVEDATA_INGESTION_STATE['market_open']}",
    )
    append_log(
        "backend.log",
        f"TwelveData scheduler tick market_open={TWELVEDATA_INGESTION_STATE['market_open']}",
    )
    if not TWELVEDATA_INGESTION_STATE["market_open"]:
        append_log("forex.log", "TwelveData market closed / waiting for next session")
        append_log("backend.log", "TwelveData market closed / waiting for next session")
    TWELVEDATA_INGESTION_STATE.update(
        {
            "last_run_at": _iso(now),
            "next_run_at": _iso(now + timedelta(seconds=_env_interval())),
            "last_error": "",
        }
    )

    try:
        result = ingest_twelvedata_forex()
        status = result.get("status", "unknown")
        candle = result.get("inserted") or result.get("existing") or {}
        last_price = candle.get("close")
        exchange_time = candle.get("exchange_candle_time") or candle.get("timestamp", "")
        fetched_at = candle.get("fetched_at", "")
        inserted_at = candle.get("inserted_at", "")
        timestamp_corrected = bool(result.get("timestamp_corrected"))
        timestamp_correction_reason = result.get("timestamp_correction_reason", "")
        provider_raw_datetime = result.get("provider_raw_datetime", "")

        if status == "ok":
            TWELVEDATA_INGESTION_STATE["success_count"] += 1
            TWELVEDATA_INGESTION_STATE["last_success_at"] = _iso(_utc_now())
            TWELVEDATA_INGESTION_STATE["last_status"] = "success"
            append_log("forex.log", "TwelveData scheduler ingest success")
            append_log("backend.log", "TwelveData scheduler ingest success")
        elif status == "duplicate_skipped":
            TWELVEDATA_INGESTION_STATE["duplicate_skipped_count"] += 1
            TWELVEDATA_INGESTION_STATE["last_status"] = "duplicate_skipped"
            append_log("forex.log", "TwelveData scheduler duplicate skipped")
            append_log("backend.log", "TwelveData scheduler duplicate skipped")
            if not TWELVEDATA_INGESTION_STATE["market_open"]:
                append_log("forex.log", "TwelveData market closed / no new candle")
                append_log("backend.log", "TwelveData market closed / no new candle")
        elif status == "skipped":
            TWELVEDATA_INGESTION_STATE["last_status"] = "skipped"
            TWELVEDATA_INGESTION_STATE["last_error"] = result.get("message", "")
            append_log("forex.log", f"TwelveData scheduler skipped: {result.get('message', '')}")
            append_log("backend.log", f"TwelveData scheduler skipped: {result.get('message', '')}")
        else:
            TWELVEDATA_INGESTION_STATE["failure_count"] += 1
            TWELVEDATA_INGESTION_STATE["last_status"] = "failed"
            TWELVEDATA_INGESTION_STATE["last_error"] = result.get("message", "Ingest failed")
            append_log("forex.log", f"TwelveData scheduler ingest failure: {TWELVEDATA_INGESTION_STATE['last_error']}")
            append_log("backend.log", f"TwelveData scheduler ingest failure: {TWELVEDATA_INGESTION_STATE['last_error']}")

        if last_price is not None:
            TWELVEDATA_INGESTION_STATE["last_price"] = last_price
        if exchange_time:
            TWELVEDATA_INGESTION_STATE["last_inserted_timestamp"] = exchange_time
            TWELVEDATA_INGESTION_STATE["exchange_candle_time"] = exchange_time
        if fetched_at:
            TWELVEDATA_INGESTION_STATE["fetched_at"] = fetched_at
        if inserted_at:
            TWELVEDATA_INGESTION_STATE["inserted_at"] = inserted_at
        TWELVEDATA_INGESTION_STATE["provider_raw_datetime"] = provider_raw_datetime
        TWELVEDATA_INGESTION_STATE["timestamp_corrected"] = timestamp_corrected
        TWELVEDATA_INGESTION_STATE["timestamp_correction_reason"] = timestamp_correction_reason
        freshness_seconds = _freshness_seconds(exchange_time)
        append_log(
            "forex.log",
            (
                "TwelveData cycle detail "
                f"exchange_candle_time={exchange_time or 'unknown'} "
                f"fetched_at={fetched_at or 'unknown'} "
                f"inserted_at={inserted_at or 'unknown'} "
                f"insert_status={status} "
                f"duplicate_skipped={str(status == 'duplicate_skipped').lower()} "
                f"timestamp_corrected={str(timestamp_corrected).lower()} "
                f"correction_reason={timestamp_correction_reason or 'none'} "
                f"market_session={TWELVEDATA_INGESTION_STATE['market_session']} "
                f"true_freshness={_freshness_label(freshness_seconds) or 'unknown'}"
            ),
        )
        append_log(
            "backend.log",
            (
                "TwelveData cycle detail "
                f"exchange_candle_time={exchange_time or 'unknown'} "
                f"fetched_at={fetched_at or 'unknown'} "
                f"inserted_at={inserted_at or 'unknown'} "
                f"insert_status={status} "
                f"duplicate_skipped={str(status == 'duplicate_skipped').lower()} "
                f"timestamp_corrected={str(timestamp_corrected).lower()} "
                f"correction_reason={timestamp_correction_reason or 'none'} "
                f"market_session={TWELVEDATA_INGESTION_STATE['market_session']} "
                f"true_freshness={_freshness_label(freshness_seconds) or 'unknown'}"
            ),
        )
        return {"scheduler": get_twelvedata_ingestion_status(), "ingest_result": result}
    except Exception as exc:
        message = str(exc)
        TWELVEDATA_INGESTION_STATE["failure_count"] += 1
        TWELVEDATA_INGESTION_STATE["last_status"] = "failed"
        TWELVEDATA_INGESTION_STATE["last_error"] = message
        append_log("forex.log", f"TwelveData scheduler ingest failure: {message}")
        append_log("backend.log", f"TwelveData scheduler ingest failure: {message}")
        return {
            "scheduler": get_twelvedata_ingestion_status(),
            "ingest_result": {"status": "error", "message": message},
        }


def _zerodha_error_status(message: str) -> str:
    lowered = message.lower()
    if "missing zerodha credentials" in lowered:
        return "missing_credentials"
    if "api_key" in lowered or "access_token" in lowered or "token" in lowered:
        return "token_error"
    if "no mcx candle" in lowered or "no data" in lowered or "no candles" in lowered:
        return "no_data"
    return "failed"


def run_zerodha_ingest_once() -> dict[str, Any]:
    _sync_zerodha_env_state()
    now = _utc_now()
    append_mcx_log(
        f"Zerodha scheduler tick market_open={ZERODHA_INGESTION_STATE['market_open']}"
    )
    append_log(
        "backend.log",
        f"Zerodha scheduler tick market_open={ZERODHA_INGESTION_STATE['market_open']}",
    )
    if not ZERODHA_INGESTION_STATE["market_open"]:
        append_mcx_log("Zerodha market closed / waiting for next session")
        append_log("backend.log", "Zerodha market closed / waiting for next session")
    ZERODHA_INGESTION_STATE.update(
        {
            "last_run_at": _iso(now),
            "next_run_at": _iso(now + timedelta(seconds=_zerodha_env_interval())),
            "last_error": "",
        }
    )

    try:
        result = ingest_zerodha_mcx()
        status = result.get("status", "unknown")
        candle = result.get("inserted") or result.get("existing") or {}
        last_price = candle.get("close")
        exchange_time = candle.get("exchange_candle_time") or candle.get("timestamp", "")
        fetched_at = candle.get("fetched_at", "")
        inserted_at = candle.get("inserted_at", "")

        if status == "ok":
            ZERODHA_INGESTION_STATE["success_count"] += 1
            ZERODHA_INGESTION_STATE["last_success_at"] = _iso(_utc_now())
            ZERODHA_INGESTION_STATE["last_status"] = "success"
            append_mcx_log("Zerodha scheduler ingest success")
            append_log("backend.log", "Zerodha scheduler ingest success")
        elif status == "duplicate_skipped":
            ZERODHA_INGESTION_STATE["duplicate_skipped_count"] += 1
            ZERODHA_INGESTION_STATE["last_status"] = "duplicate_skipped"
            append_mcx_log("Zerodha scheduler duplicate skipped")
            append_log("backend.log", "Zerodha scheduler duplicate skipped")
            if not ZERODHA_INGESTION_STATE["market_open"]:
                append_mcx_log("Zerodha market closed / no new candle")
                append_log("backend.log", "Zerodha market closed / no new candle")
        elif status == "skipped":
            ZERODHA_INGESTION_STATE["credential_error_count"] += 1
            ZERODHA_INGESTION_STATE["last_status"] = "missing_credentials"
            ZERODHA_INGESTION_STATE["last_error"] = result.get("message", "")
            append_mcx_log(f"Zerodha scheduler skipped: {result.get('message', '')}")
            append_log("backend.log", f"Zerodha scheduler skipped: {result.get('message', '')}")
        else:
            message = result.get("message", "Zerodha ingest failed")
            mapped_status = _zerodha_error_status(message)
            ZERODHA_INGESTION_STATE["failure_count"] += 1
            if mapped_status == "no_data":
                ZERODHA_INGESTION_STATE["no_data_count"] += 1
            if mapped_status in {"token_error", "missing_credentials"}:
                ZERODHA_INGESTION_STATE["credential_error_count"] += 1
            ZERODHA_INGESTION_STATE["last_status"] = mapped_status
            ZERODHA_INGESTION_STATE["last_error"] = message
            append_mcx_log(f"Zerodha scheduler ingest failure: {message}")
            append_log("backend.log", f"Zerodha scheduler ingest failure: {message}")

        if last_price is not None:
            ZERODHA_INGESTION_STATE["last_price"] = last_price
        if exchange_time:
            ZERODHA_INGESTION_STATE["last_inserted_timestamp"] = exchange_time
            ZERODHA_INGESTION_STATE["exchange_candle_time"] = exchange_time
        if fetched_at:
            ZERODHA_INGESTION_STATE["fetched_at"] = fetched_at
        if inserted_at:
            ZERODHA_INGESTION_STATE["inserted_at"] = inserted_at
        freshness_seconds = _freshness_seconds(exchange_time)
        append_mcx_log(
            "Zerodha cycle detail "
            f"exchange_candle_time={exchange_time or 'unknown'} "
            f"fetched_at={fetched_at or 'unknown'} "
            f"inserted_at={inserted_at or 'unknown'} "
            f"insert_status={status} "
            f"duplicate_skipped={str(status == 'duplicate_skipped').lower()} "
            f"market_session={ZERODHA_INGESTION_STATE['market_session']} "
            f"true_freshness={_freshness_label(freshness_seconds) or 'unknown'}"
        )
        append_log(
            "backend.log",
            (
                "Zerodha cycle detail "
                f"exchange_candle_time={exchange_time or 'unknown'} "
                f"fetched_at={fetched_at or 'unknown'} "
                f"inserted_at={inserted_at or 'unknown'} "
                f"insert_status={status} "
                f"duplicate_skipped={str(status == 'duplicate_skipped').lower()} "
                f"market_session={ZERODHA_INGESTION_STATE['market_session']} "
                f"true_freshness={_freshness_label(freshness_seconds) or 'unknown'}"
            ),
        )
        return {"scheduler": get_zerodha_ingestion_status(), "ingest_result": result}
    except Exception as exc:
        message = str(exc)
        mapped_status = _zerodha_error_status(message)
        ZERODHA_INGESTION_STATE["failure_count"] += 1
        if mapped_status == "no_data":
            ZERODHA_INGESTION_STATE["no_data_count"] += 1
        if mapped_status in {"token_error", "missing_credentials"}:
            ZERODHA_INGESTION_STATE["credential_error_count"] += 1
        ZERODHA_INGESTION_STATE["last_status"] = mapped_status
        ZERODHA_INGESTION_STATE["last_error"] = message
        append_mcx_log(f"Zerodha scheduler ingest failure: {message}")
        append_log("backend.log", f"Zerodha scheduler ingest failure: {message}")
        return {
            "scheduler": get_zerodha_ingestion_status(),
            "ingest_result": {"status": "error", "message": message},
        }


def run_missing_candle_fill_once() -> dict[str, Any]:
    now = _utc_now()
    interval = _missing_candle_fill_interval()
    days = _missing_candle_fill_days()
    MISSING_CANDLE_FILL_STATE.update(
        {
            "interval_seconds": interval,
            "lookback_days": days,
            "last_run_at": _iso(now),
            "next_run_at": _iso(now + timedelta(seconds=interval)),
            "last_error": "",
            "structure_refreshed": False,
        }
    )
    append_log(
        "backend.log",
        f"Missing candle fill started interval={interval}s lookback_days={days}",
    )

    forex_result: dict[str, Any] = {"status": "not_run", "total_inserted": 0}
    mcx_result: dict[str, Any] = {"status": "not_run", "total_inserted": 0}
    errors: list[str] = []

    try:
        forex_result = backfill_twelvedata_forex(
            days=days,
            chunk_days=1,
            dry_run=False,
            refresh_structure=False,
        )
    except Exception as exc:
        errors.append(f"Forex fill failed: {exc}")

    try:
        mcx_result = backfill_zerodha_mcx(
            days=days,
            chunk_days=1,
            dry_run=False,
            refresh_structure=False,
        )
    except Exception as exc:
        errors.append(f"MCX fill failed: {exc}")

    forex_inserted = int(forex_result.get("total_inserted") or 0)
    mcx_inserted = int(mcx_result.get("total_inserted") or 0)
    structure_result = None
    if forex_inserted or mcx_inserted:
        try:
            structure_result = compact_market_structure_result(refresh_market_structure())
            MISSING_CANDLE_FILL_STATE["structure_refreshed"] = True
        except Exception as exc:
            errors.append(f"Market structure refresh failed: {exc}")

    if errors:
        MISSING_CANDLE_FILL_STATE["failure_count"] += 1
        MISSING_CANDLE_FILL_STATE["last_status"] = "partial_failure"
        MISSING_CANDLE_FILL_STATE["last_error"] = "; ".join(errors)
    else:
        MISSING_CANDLE_FILL_STATE["success_count"] += 1
        MISSING_CANDLE_FILL_STATE["last_success_at"] = _iso(_utc_now())
        MISSING_CANDLE_FILL_STATE["last_status"] = "success"

    MISSING_CANDLE_FILL_STATE.update(
        {
            "forex_status": forex_result.get("status", ""),
            "mcx_status": mcx_result.get("status", ""),
            "forex_inserted": forex_inserted,
            "mcx_inserted": mcx_inserted,
        }
    )
    append_log(
        "backend.log",
        (
            "Missing candle fill completed "
            f"forex_status={MISSING_CANDLE_FILL_STATE['forex_status']} "
            f"forex_inserted={forex_inserted} "
            f"mcx_status={MISSING_CANDLE_FILL_STATE['mcx_status']} "
            f"mcx_inserted={mcx_inserted} "
            f"structure_refreshed={str(MISSING_CANDLE_FILL_STATE['structure_refreshed']).lower()}"
        ),
    )
    return {
        "scheduler": get_missing_candle_fill_status(),
        "forex": forex_result,
        "mcx": mcx_result,
        "market_structure": structure_result,
    }


async def _scheduler_loop() -> None:
    append_log("forex.log", "TwelveData scheduler started")
    append_log("backend.log", "TwelveData scheduler started")
    TWELVEDATA_INGESTION_STATE["running"] = True
    try:
        while True:
            await asyncio.to_thread(run_twelvedata_ingest_once)
            await asyncio.sleep(_env_interval())
    except asyncio.CancelledError:
        append_log("forex.log", "TwelveData scheduler stopped")
        append_log("backend.log", "TwelveData scheduler stopped")
        raise
    finally:
        TWELVEDATA_INGESTION_STATE["running"] = False
        TWELVEDATA_INGESTION_STATE["next_run_at"] = ""
        if TWELVEDATA_INGESTION_STATE["last_status"] not in {
            "success",
            "duplicate_skipped",
            "failed",
            "skipped",
        }:
            TWELVEDATA_INGESTION_STATE["last_status"] = "stopped"


def start_twelvedata_scheduler(force: bool = False) -> dict[str, Any]:
    global _scheduler_task
    _sync_env_state()
    if not force and not _env_enabled():
        TWELVEDATA_INGESTION_STATE.update({"running": False, "last_status": "stopped"})
        return get_twelvedata_ingestion_status()
    if _task_alive():
        TWELVEDATA_INGESTION_STATE["running"] = True
        return get_twelvedata_ingestion_status()
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    TWELVEDATA_INGESTION_STATE.update(
        {
            "running": True,
            "enabled": True if force else _env_enabled(),
            "last_status": "starting",
            "next_run_at": _iso(_utc_now()),
        }
    )
    return get_twelvedata_ingestion_status()


async def _zerodha_scheduler_loop() -> None:
    append_mcx_log("Zerodha scheduler started")
    append_log("backend.log", "Zerodha scheduler started")
    ZERODHA_INGESTION_STATE["running"] = True
    try:
        while True:
            await asyncio.to_thread(run_zerodha_ingest_once)
            await asyncio.sleep(_zerodha_env_interval())
    except asyncio.CancelledError:
        append_mcx_log("Zerodha scheduler stopped")
        append_log("backend.log", "Zerodha scheduler stopped")
        raise
    finally:
        ZERODHA_INGESTION_STATE["running"] = False
        ZERODHA_INGESTION_STATE["next_run_at"] = ""
        if ZERODHA_INGESTION_STATE["last_status"] not in {
            "success",
            "duplicate_skipped",
            "failed",
            "skipped",
            "missing_credentials",
            "token_error",
            "no_data",
        }:
            ZERODHA_INGESTION_STATE["last_status"] = "stopped"


async def _missing_candle_fill_loop() -> None:
    append_log("backend.log", "Missing candle fill scheduler started")
    MISSING_CANDLE_FILL_STATE["running"] = True
    try:
        while True:
            await asyncio.to_thread(run_missing_candle_fill_once)
            await asyncio.sleep(_missing_candle_fill_interval())
    except asyncio.CancelledError:
        append_log("backend.log", "Missing candle fill scheduler stopped")
        raise
    finally:
        MISSING_CANDLE_FILL_STATE["running"] = False
        MISSING_CANDLE_FILL_STATE["next_run_at"] = ""
        if MISSING_CANDLE_FILL_STATE["last_status"] not in {
            "success",
            "partial_failure",
        }:
            MISSING_CANDLE_FILL_STATE["last_status"] = "stopped"


def start_zerodha_scheduler(force: bool = False) -> dict[str, Any]:
    global _zerodha_scheduler_task
    _sync_zerodha_env_state()
    if not force and not _zerodha_env_enabled():
        ZERODHA_INGESTION_STATE.update({"running": False, "last_status": "stopped"})
        return get_zerodha_ingestion_status()
    if _zerodha_task_alive():
        ZERODHA_INGESTION_STATE["running"] = True
        return get_zerodha_ingestion_status()
    _zerodha_scheduler_task = asyncio.create_task(_zerodha_scheduler_loop())
    ZERODHA_INGESTION_STATE.update(
        {
            "running": True,
            "enabled": True if force else _zerodha_env_enabled(),
            "last_status": "starting",
            "next_run_at": _iso(_utc_now()),
        }
    )
    return get_zerodha_ingestion_status()


def start_missing_candle_fill_scheduler(force: bool = False) -> dict[str, Any]:
    global _missing_candle_fill_task
    if not force and not _missing_candle_fill_enabled():
        MISSING_CANDLE_FILL_STATE.update({"running": False, "last_status": "stopped"})
        return get_missing_candle_fill_status()
    if _missing_candle_fill_alive():
        MISSING_CANDLE_FILL_STATE["running"] = True
        return get_missing_candle_fill_status()
    _missing_candle_fill_task = asyncio.create_task(_missing_candle_fill_loop())
    MISSING_CANDLE_FILL_STATE.update(
        {
            "running": True,
            "enabled": True if force else _missing_candle_fill_enabled(),
            "last_status": "starting",
            "interval_seconds": _missing_candle_fill_interval(),
            "lookback_days": _missing_candle_fill_days(),
            "next_run_at": _iso(_utc_now()),
        }
    )
    return get_missing_candle_fill_status()


async def stop_zerodha_scheduler() -> dict[str, Any]:
    global _zerodha_scheduler_task
    if _zerodha_task_alive():
        _zerodha_scheduler_task.cancel()
        try:
            await _zerodha_scheduler_task
        except asyncio.CancelledError:
            pass
    _zerodha_scheduler_task = None
    ZERODHA_INGESTION_STATE.update(
        {
            "running": False,
            "next_run_at": "",
            "last_status": "stopped",
        }
    )
    return get_zerodha_ingestion_status()


async def stop_twelvedata_scheduler() -> dict[str, Any]:
    global _scheduler_task
    if _task_alive():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    _scheduler_task = None
    TWELVEDATA_INGESTION_STATE.update(
        {
            "running": False,
            "next_run_at": "",
            "last_status": "stopped",
        }
    )
    return get_twelvedata_ingestion_status()


async def stop_missing_candle_fill_scheduler() -> dict[str, Any]:
    global _missing_candle_fill_task
    if _missing_candle_fill_alive():
        _missing_candle_fill_task.cancel()
        try:
            await _missing_candle_fill_task
        except asyncio.CancelledError:
            pass
    _missing_candle_fill_task = None
    MISSING_CANDLE_FILL_STATE.update(
        {
            "running": False,
            "next_run_at": "",
            "last_status": "stopped",
        }
    )
    return get_missing_candle_fill_status()
