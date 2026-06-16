import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Body, Query

from app.data.ingestion_service import (
    backfill_twelvedata_forex,
    backfill_zerodha_mcx,
    ingest_mock_candles,
    ingest_twelvedata_forex,
    ingest_zerodha_mcx,
    twelvedata_symbol_forex,
    zerodha_mcx_instrument,
)
from app.data.scheduler import (
    get_zerodha_ingestion_status,
    get_twelvedata_ingestion_status,
    run_zerodha_ingest_once,
    run_twelvedata_ingest_once,
    start_twelvedata_scheduler,
    start_zerodha_scheduler,
    stop_zerodha_scheduler,
    stop_twelvedata_scheduler,
)
from app.db import (
    DatabaseUnavailable,
    fetch_candle_timestamps,
    fetch_latest_candle_by_source,
    fetch_latest_market_snapshot,
    fetch_market_candles,
)
from app.intelligence.multi_timeframe_engine import (
    build_intelligence_evolution,
    build_multi_timeframe_snapshot,
)

router = APIRouter()
HIGHER_TIMEFRAMES = {"1H", "4H"}


def is_forex_market_open(now=None):
    current = now or datetime.now(timezone.utc)
    return current.weekday() < 5


def is_mcx_market_open(now=None):
    current = (now or datetime.now(timezone.utc)).astimezone(
        timezone(timedelta(hours=5, minutes=30))
    )
    return current.weekday() < 5 and 9 <= current.hour < 23


def is_market_open(market_type, now=None):
    return is_mcx_market_open(now) if market_type.upper() == "MCX" else is_forex_market_open(now)


def expected_1m_candles(market_type, start, end):
    if start >= end:
        return 0
    if market_type.upper() == "FOREX":
        total = 0
        cursor = start.replace(second=0, microsecond=0)
        end = end.replace(second=0, microsecond=0)
        while cursor < end:
            if cursor.weekday() < 5:
                total += 1
            cursor += timedelta(minutes=1)
        return total
    if market_type.upper() == "MCX":
        ist = timezone(timedelta(hours=5, minutes=30))
        total = 0
        cursor = start.replace(second=0, microsecond=0)
        end = end.replace(second=0, microsecond=0)
        while cursor < end:
            local = cursor.astimezone(ist)
            if local.weekday() < 5 and 9 <= local.hour < 23:
                total += 1
            cursor += timedelta(minutes=1)
        return total
    return int((end - start).total_seconds() // 60)


def session_missing_minutes(market_type, previous, current):
    start = previous + timedelta(minutes=1)
    return expected_1m_candles(market_type, start, current)


def largest_gap_minutes(timestamps, market_type=None):
    if len(timestamps) < 2:
        return 0
    gaps = []
    for index in range(1, len(timestamps)):
        previous = timestamps[index - 1]
        current = timestamps[index]
        if market_type:
            gaps.append(session_missing_minutes(market_type, previous, current))
        else:
            gaps.append(int((current - previous).total_seconds() / 60))
    return max(gaps) if gaps else 0


def missing_ranges(timestamps, threshold_minutes=5, market_type=None):
    ranges = []
    if len(timestamps) < 2:
        return ranges
    for index in range(1, len(timestamps)):
        previous = timestamps[index - 1]
        current = timestamps[index]
        raw_gap = int((current - previous).total_seconds() / 60)
        gap = (
            session_missing_minutes(market_type, previous, current)
            if market_type
            else raw_gap
        )
        if gap > threshold_minutes:
            ranges.append(
                {
                    "from": previous.isoformat(),
                    "to": current.isoformat(),
                    "minutes": gap,
                    "raw_gap_minutes": raw_gap,
                }
            )
    return sorted(ranges, key=lambda item: item["minutes"], reverse=True)[:10]


def candle_health_status(coverage_percent, largest_gap, market_open):
    if coverage_percent >= 90 and largest_gap <= 10:
        return "ok"
    if coverage_percent >= 70:
        return "warning"
    if not market_open:
        return "warning"
    return "critical"


def coverage_bucket(coverage_percent):
    if coverage_percent >= 90:
        return "Strong"
    if coverage_percent >= 50:
        return "Moderate"
    if coverage_percent > 0:
        return "Low"
    return "None"


def freshness_payload(exchange_time):
    if not exchange_time:
        return {"seconds": None, "label": "", "status": "unknown"}
    try:
        parsed = datetime.fromisoformat(str(exchange_time).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return {"seconds": None, "label": "", "status": "unknown"}
    seconds = int((datetime.now(timezone.utc) - parsed).total_seconds())
    if seconds < -60:
        label = "provider time ahead"
    elif seconds < 60:
        label = "just now"
    elif seconds < 3600:
        label = f"{seconds // 60}m old"
    elif seconds < 86400:
        label = f"{seconds // 3600}h {(seconds % 3600) // 60}m old"
    else:
        label = f"{seconds // 86400}d old"
    if seconds < -60:
        status = "time_ahead"
    else:
        status = "fresh" if seconds <= 180 else "delayed" if seconds <= 900 else "stale"
    return {"seconds": seconds, "label": label, "status": status}


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


def unavailable_market_data(instrument, market_type, timeframe, message):
    return {
        "instrument": instrument,
        "market_type": market_type,
        "source": "UNAVAILABLE",
        "timeframe": timeframe,
        "timestamp": "",
        "exchange_candle_time": "",
        "fetched_at": "",
        "inserted_at": "",
        "candle": {},
        "smc_labels": [],
        "status": "NO_DB_ROWS",
        "message": message,
    }


@router.get("/latest")
def latest_market_data(timeframe: str = Query("1m")):
    try:
        snapshot = fetch_latest_market_snapshot(timeframe=timeframe)
        if snapshot:
            snapshot.setdefault(
                "mcx",
                unavailable_market_data(
                    "NATURALGAS",
                    "MCX",
                    timeframe,
                    "No MCX database candles available.",
                ),
            )
            snapshot.setdefault(
                "forex",
                unavailable_market_data(
                    "XAUUSD",
                    "FOREX",
                    timeframe,
                    "No Forex database candles available.",
                ),
            )
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
        if not candles and timeframe in HIGHER_TIMEFRAMES:
            return {
                "status": "EMPTY",
                "message": "Insufficient candles for selected timeframe",
                "candles": [],
            }
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


@router.get("/candle-health")
def market_candle_health(
    market_type: str = Query("FOREX"),
    instrument: str = Query("XAUUSD"),
    timeframe: str = Query("1m"),
    days: int = Query(30, ge=1, le=90),
):
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    since = now - timedelta(days=days)
    normalized_market = market_type.upper()
    normalized_instrument = instrument.upper()
    try:
        timestamps = fetch_candle_timestamps(
            normalized_market,
            normalized_instrument,
            timeframe,
            since,
        )
    except DatabaseUnavailable:
        timestamps = []

    first = timestamps[0] if timestamps else None
    last = timestamps[-1] if timestamps else None
    market_open = is_market_open(normalized_market, now)
    expected = (
        expected_1m_candles(normalized_market, since, now)
        if timeframe == "1m"
        else 0
    )
    total = len(timestamps)
    missing = max(0, expected - total) if expected else 0
    coverage = min(100.0, round((total / expected) * 100, 1)) if expected else 0
    gap = largest_gap_minutes(timestamps, market_type=normalized_market)
    status = candle_health_status(coverage, gap, market_open)
    gaps = missing_ranges(timestamps, market_type=normalized_market)
    return {
        "instrument": normalized_instrument,
        "market_type": normalized_market,
        "timeframe": timeframe,
        "lookback_days": days,
        "first_candle": first.isoformat() if first else "",
        "last_candle": last.isoformat() if last else "",
        "total_candles": total,
        "expected_candles": expected,
        "missing_candles": missing,
        "coverage_percent": coverage,
        "largest_gap_minutes": gap,
        "missing_ranges": gaps,
        "market_open": market_open,
        "session_state": "market_open" if market_open else "market_closed",
        "status": status,
        "recommended_history": {
            "minimum": "3-5 trading days",
            "recommended": "30 days",
            "strong": "90 days",
        },
    }


@router.get("/intelligence/multi-timeframe")
def market_multi_timeframe_intelligence(
    market_type: str = Query("FOREX"),
    instrument: str = Query("XAUUSD"),
    selected_timeframe: str = Query("1m"),
):
    try:
        return build_multi_timeframe_snapshot(
            market_type=market_type,
            instrument=instrument,
            selected_timeframe=selected_timeframe,
        )
    except DatabaseUnavailable as exc:
        return {
            "status": "DB_UNAVAILABLE",
            "message": str(exc),
            "market_type": market_type.upper(),
            "instrument": instrument.upper(),
            "selected_timeframe": selected_timeframe,
            "timeframes": {},
            "alignment": {},
            "decision": {
                "state": "WAIT",
                "confidence": 0,
                "reason": "Database unavailable.",
                "next_validation": "Restore database connectivity.",
            },
        }


@router.get("/intelligence/evolution")
def market_intelligence_evolution(
    market_type: str = Query("FOREX"),
    instrument: str = Query("XAUUSD"),
    selected_timeframe: str = Query("1m"),
):
    try:
        return build_intelligence_evolution(
            market_type=market_type,
            instrument=instrument,
            selected_timeframe=selected_timeframe,
        )
    except DatabaseUnavailable as exc:
        return {
            "status": "DB_UNAVAILABLE",
            "message": str(exc),
            "market_type": market_type.upper(),
            "instrument": instrument.upper(),
            "selected_timeframe": selected_timeframe,
            "evolution": {
                "has_previous": False,
                "summary": "No previous intelligence snapshot available yet.",
                "regime_change": {"previous": "", "current": "", "changed": False},
                "decision_change": {"previous": "", "current": "", "changed": False},
                "timeframe_changes": [],
                "confidence_change": {"previous": None, "current": 0, "delta": None},
            },
        }


@router.post("/sanity-check")
def market_sanity_check(payload: dict = Body(default={})):
    market_type = str(payload.get("market_type", "FOREX")).upper()
    instrument = str(payload.get("instrument", "XAUUSD")).upper()
    timeframe = str(payload.get("timeframe", "1m"))
    days = int(payload.get("days", 30) or 30)
    health = market_candle_health(
        market_type=market_type,
        instrument=instrument,
        timeframe=timeframe,
        days=max(1, min(days, 90)),
    )
    coverage = coverage_bucket(health.get("coverage_percent", 0))
    status = health.get("status", "warning")
    largest_gap = int(health.get("largest_gap_minutes", 0) or 0)
    readiness = coverage
    if health.get("total_candles", 0) == 0:
        recommendation = "Configure provider credentials and run backfill."
        status = "critical" if health.get("market_open") else "warning"
        readiness = "Not Ready"
    elif largest_gap > 180:
        recommendation = "Run backfill before relying on multi-timeframe analysis."
        status = "warning"
        readiness = "Moderate" if coverage in {"Strong", "Moderate"} else "Weak"
    elif coverage in {"None", "Low"}:
        recommendation = "Backfill at least 7 trading days before relying on specialist review."
        readiness = "Weak"
    elif coverage == "Moderate":
        recommendation = "Backfill toward 30 days for stronger specialist review."
        readiness = "Moderate"
    else:
        recommendation = "Ready for specialist review."
        readiness = "Strong"
    return {
        "status": status,
        "instrument": instrument,
        "market_type": market_type,
        "timeframe": timeframe,
        "available_candles": health.get("total_candles", 0),
        "coverage": coverage,
        "coverage_label": coverage,
        "largest_gap_minutes": largest_gap,
        "largest_unexpected_gap_minutes": largest_gap,
        "analysis_readiness": readiness,
        "missing_ranges": health.get("missing_ranges", []),
        "recommendation": recommendation,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/ingest/mock")
def ingest_mock_market_data():
    return ingest_mock_candles()


@router.post("/ingest/twelvedata")
def ingest_twelvedata_market_data():
    return ingest_twelvedata_forex()


@router.post("/ingest/twelvedata/backfill")
def backfill_twelvedata_market_data(
    days: int = Query(30, ge=1, le=90),
    chunk_days: int = Query(3, ge=1, le=5),
    dry_run: bool = Query(False),
):
    before = market_sanity_check(
        {
            "market_type": "FOREX",
            "instrument": "XAUUSD",
            "timeframe": "1m",
            "days": days,
        }
    )
    result = backfill_twelvedata_forex(
        days=days,
        chunk_days=chunk_days,
        dry_run=dry_run,
    )
    after = market_sanity_check(
        {
            "market_type": "FOREX",
            "instrument": "XAUUSD",
            "timeframe": "1m",
            "days": days,
        }
    )
    return {
        "status": result.get("status"),
        "sanity_before": before,
        "backfill": result,
        "sanity_after": after,
    }


@router.get("/provider-status")
def market_provider_status():
    configured = bool(os.getenv("TWELVEDATA_API_KEY", ""))
    symbol = twelvedata_symbol_forex()
    try:
        latest = fetch_latest_candle_by_source(
            "FOREX", "XAUUSD", "1m", "TWELVEDATA"
        )
    except DatabaseUnavailable:
        latest = None
    latest_price = latest.get("close") if latest else None
    return {
        "twelvedata_configured": configured,
        "twelvedata_symbol": symbol,
        "last_twelvedata_ingest_time": latest.get("timestamp") if latest else "",
        "latest_twelvedata_price": latest_price,
    }


@router.get("/ingestion/status")
def market_ingestion_status():
    state = get_twelvedata_ingestion_status()
    zerodha_state = get_zerodha_ingestion_status()
    try:
        latest = fetch_latest_candle_by_source(
            "FOREX", "XAUUSD", "1m", "TWELVEDATA"
        )
    except DatabaseUnavailable:
        latest = None
    if latest:
        exchange_time = latest.get("exchange_candle_time") or latest.get("timestamp", "")
        freshness = freshness_payload(exchange_time)
        state.update(
            {
                "instrument": "XAUUSD",
                "exchange_candle_time": state.get("exchange_candle_time") or exchange_time,
                "fetched_at": state.get("fetched_at") or latest.get("fetched_at", ""),
                "inserted_at": state.get("inserted_at") or latest.get("inserted_at", ""),
                "last_candle_time": state.get("exchange_candle_time") or exchange_time,
                "last_price": state.get("last_price") or latest.get("close"),
                "freshness_seconds": state.get("freshness_seconds")
                if state.get("freshness_seconds") is not None
                else freshness["seconds"],
                "freshness_label": state.get("freshness_label") or freshness["label"],
                "freshness_status": freshness["status"]
                if state.get("freshness_status") in {"", "unknown", None}
                else state.get("freshness_status"),
                "market_session": "open" if is_forex_market_open() else "closed",
                "analysis_readiness": "Weak" if latest else "Not Ready",
            }
        )
        state.update(
            {
                "worker_alive": state.get("worker_alive", state.get("task_alive", False)),
                "last_tick": state.get("last_run_at", ""),
                "last_candle": state.get("exchange_candle_time") or exchange_time,
                "freshness": state.get("freshness_label", ""),
                "market_session": "open" if is_forex_market_open() else "closed",
                "worker_status": "running"
                if state.get("worker_alive", state.get("task_alive", False))
                else "stopped",
            }
        )
    try:
        latest_mcx = fetch_latest_candle_by_source(
            "MCX", "NATURALGAS", "1m", "ZERODHA"
        )
    except DatabaseUnavailable:
        latest_mcx = None
    if latest_mcx:
        exchange_time = latest_mcx.get("exchange_candle_time") or latest_mcx.get("timestamp", "")
        freshness = freshness_payload(exchange_time)
        zerodha_state.update(
            {
                "instrument": "NATURALGAS",
                "exchange_candle_time": zerodha_state.get("exchange_candle_time") or exchange_time,
                "fetched_at": zerodha_state.get("fetched_at") or latest_mcx.get("fetched_at", ""),
                "inserted_at": zerodha_state.get("inserted_at") or latest_mcx.get("inserted_at", ""),
                "last_candle_time": zerodha_state.get("exchange_candle_time") or exchange_time,
                "last_price": zerodha_state.get("last_price") or latest_mcx.get("close"),
                "freshness_seconds": zerodha_state.get("freshness_seconds")
                if zerodha_state.get("freshness_seconds") is not None
                else freshness["seconds"],
                "freshness_label": zerodha_state.get("freshness_label") or freshness["label"],
                "freshness_status": freshness["status"]
                if zerodha_state.get("freshness_status") in {"", "unknown", None}
                else zerodha_state.get("freshness_status"),
                "market_session": "open" if is_mcx_market_open() else "closed",
                "analysis_readiness": "Weak" if latest_mcx else "Not Ready",
                "stale_data_warning": ""
                if not is_mcx_market_open() or freshness["seconds"] <= 900
                else f"Latest candle is stale: {freshness['seconds'] // 60}m old",
            }
        )
        zerodha_state.update(
            {
                "worker_alive": zerodha_state.get(
                    "worker_alive", zerodha_state.get("task_alive", False)
                ),
                "last_tick": zerodha_state.get("last_run_at", ""),
                "last_candle": zerodha_state.get("exchange_candle_time") or exchange_time,
                "freshness": zerodha_state.get("freshness_label", ""),
                "market_session": "open" if is_mcx_market_open() else "closed",
                "worker_status": "running"
                if zerodha_state.get(
                    "worker_alive", zerodha_state.get("task_alive", False)
                )
                else "stopped",
            }
        )
    return {"twelvedata": state, "zerodha": zerodha_state}


@router.post("/ingestion/start")
async def market_ingestion_start():
    return {"twelvedata": start_twelvedata_scheduler(force=True)}


@router.post("/ingestion/stop")
async def market_ingestion_stop():
    return {"twelvedata": await stop_twelvedata_scheduler()}


@router.post("/ingestion/run-once")
def market_ingestion_run_once():
    return run_twelvedata_ingest_once()


@router.post("/mcx-ingestion/start")
async def market_mcx_ingestion_start():
    return {"zerodha": start_zerodha_scheduler(force=True)}


@router.post("/mcx-ingestion/stop")
async def market_mcx_ingestion_stop():
    return {"zerodha": await stop_zerodha_scheduler()}


@router.post("/mcx-ingestion/run-once")
def market_mcx_ingestion_run_once():
    return run_zerodha_ingest_once()


@router.post("/ingest/zerodha")
def ingest_zerodha_market_data():
    return ingest_zerodha_mcx()


@router.post("/ingest/zerodha/backfill")
def backfill_zerodha_market_data(
    days: int = Query(60, ge=1, le=90),
    chunk_days: int = Query(5, ge=1, le=7),
    dry_run: bool = Query(False),
):
    instrument = zerodha_mcx_instrument().upper()
    before = market_sanity_check(
        {
            "market_type": "MCX",
            "instrument": instrument,
            "timeframe": "1m",
            "days": days,
        }
    )
    result = backfill_zerodha_mcx(
        days=days,
        chunk_days=chunk_days,
        dry_run=dry_run,
    )
    after = market_sanity_check(
        {
            "market_type": "MCX",
            "instrument": instrument,
            "timeframe": "1m",
            "days": days,
        }
    )
    return {
        "status": result.get("status"),
        "sanity_before": before,
        "backfill": result,
        "sanity_after": after,
    }
