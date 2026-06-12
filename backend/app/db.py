import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import Json, RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")


class DatabaseUnavailable(RuntimeError):
    pass


@contextmanager
def get_connection():
    if not DATABASE_URL:
        raise DatabaseUnavailable("DATABASE_URL is not configured")

    connection = None
    try:
        connection = psycopg2.connect(DATABASE_URL)
        yield connection
    except psycopg2.Error as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        if connection is not None:
            connection.close()


def seed_mock_market_data():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    candles = [
        {
            "instrument": "NATURALGAS",
            "market_type": "MCX",
            "source": "MOCK_MCX",
            "timeframe": "1m",
            "ts": now - timedelta(minutes=2),
            "open": 296.8,
            "high": 297.4,
            "low": 296.2,
            "close": 297.1,
            "volume": 11800,
        },
        {
            "instrument": "NATURALGAS",
            "market_type": "MCX",
            "source": "MOCK_MCX",
            "timeframe": "1m",
            "ts": now - timedelta(minutes=1),
            "open": 297.1,
            "high": 298.1,
            "low": 296.8,
            "close": 297.6,
            "volume": 12500,
        },
        {
            "instrument": "XAUUSD",
            "market_type": "FOREX",
            "source": "MOCK_FOREX",
            "timeframe": "1m",
            "ts": now - timedelta(minutes=2),
            "open": 2337.6,
            "high": 2340.2,
            "low": 2336.9,
            "close": 2338.8,
            "volume": 0,
        },
        {
            "instrument": "XAUUSD",
            "market_type": "FOREX",
            "source": "MOCK_FOREX",
            "timeframe": "1m",
            "ts": now - timedelta(minutes=1),
            "open": 2338.8,
            "high": 2341.5,
            "low": 2337.9,
            "close": 2340.4,
            "volume": 0,
        },
    ]

    labels = [
        {
            "instrument": "NATURALGAS",
            "market_type": "MCX",
            "timeframe": "1m",
            "ts": now - timedelta(minutes=1),
            "label_type": "BOS_BULLISH",
            "direction": "BULLISH",
            "price_level": 297.6,
            "confidence": 0.81,
            "metadata": {"source": "day_1_seed"},
        },
        {
            "instrument": "NATURALGAS",
            "market_type": "MCX",
            "timeframe": "1m",
            "ts": now - timedelta(minutes=1),
            "label_type": "FVG_BULLISH",
            "direction": "BULLISH",
            "price_level": 296.8,
            "confidence": 0.73,
            "metadata": {"source": "day_1_seed"},
        },
        {
            "instrument": "XAUUSD",
            "market_type": "FOREX",
            "timeframe": "1m",
            "ts": now - timedelta(minutes=1),
            "label_type": "LIQUIDITY_SWEEP_HIGH",
            "direction": "BEARISH",
            "price_level": 2341.5,
            "confidence": 0.78,
            "metadata": {"source": "day_1_seed"},
        },
        {
            "instrument": "XAUUSD",
            "market_type": "FOREX",
            "timeframe": "1m",
            "ts": now - timedelta(minutes=1),
            "label_type": "CHOCH_BEARISH",
            "direction": "BEARISH",
            "price_level": 2337.9,
            "confidence": 0.69,
            "metadata": {"source": "day_1_seed"},
        },
    ]

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM market_candles
                WHERE source IN ('MOCK_MCX', 'MOCK_FOREX')
                """
            )
            if cursor.fetchone()[0] > 0:
                return

            cursor.executemany(
                """
                INSERT INTO market_candles (
                    instrument, market_type, source, timeframe, ts,
                    open, high, low, close, volume
                )
                VALUES (
                    %(instrument)s, %(market_type)s, %(source)s, %(timeframe)s, %(ts)s,
                    %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s
                )
                """,
                candles,
            )
            cursor.executemany(
                """
                INSERT INTO smc_labels (
                    instrument, market_type, timeframe, ts, label_type,
                    direction, price_level, confidence, metadata
                )
                VALUES (
                    %(instrument)s, %(market_type)s, %(timeframe)s, %(ts)s, %(label_type)s,
                    %(direction)s, %(price_level)s, %(confidence)s, %(metadata)s
                )
                """,
                [{**label, "metadata": Json(label["metadata"])} for label in labels],
            )
        connection.commit()


def insert_market_candle(candle):
    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO market_candles (
                    instrument, market_type, source, timeframe, ts,
                    open, high, low, close, volume
                )
                VALUES (
                    %(instrument)s, %(market_type)s, %(source)s, %(timeframe)s, %(ts)s,
                    %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s
                )
                RETURNING id, instrument, market_type, source, timeframe, ts,
                    open, high, low, close, volume
                """,
                candle,
            )
            inserted = cursor.fetchone()
        connection.commit()

    return format_candle(inserted)


def fetch_latest_market_snapshot(timeframe="1m"):
    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT DISTINCT ON (market_type, instrument, timeframe)
                    id, instrument, market_type, source, timeframe, ts,
                    open, high, low, close, volume
                FROM market_candles
                WHERE (market_type, instrument, timeframe) IN (
                    ('MCX', 'NATURALGAS', %s),
                    ('FOREX', 'XAUUSD', %s)
                )
                ORDER BY market_type, instrument, timeframe, ts DESC, id DESC
                """,
                (timeframe, timeframe),
            )
            candles = cursor.fetchall()

            snapshot = {}
            for candle in candles:
                labels = fetch_smc_labels(
                    candle["market_type"],
                    candle["instrument"],
                    candle["timeframe"],
                    limit=10,
                    connection=connection,
                )
                key = "mcx" if candle["market_type"] == "MCX" else "forex"
                snapshot[key] = format_market_card(candle, labels, status="DB")

            return snapshot


def fetch_market_candles(market_type, instrument, timeframe, limit=50):
    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, instrument, market_type, source, timeframe, ts,
                    open, high, low, close, volume
                FROM market_candles
                WHERE market_type = %s
                    AND instrument = %s
                    AND timeframe = %s
                ORDER BY ts DESC, id DESC
                LIMIT %s
                """,
                (market_type, instrument, timeframe, limit),
            )
            return [format_candle(row) for row in cursor.fetchall()]


def fetch_smc_labels(market_type, instrument, timeframe, limit=50, connection=None):
    owns_connection = connection is None
    if owns_connection:
        if not DATABASE_URL:
            raise DatabaseUnavailable("DATABASE_URL is not configured")
        try:
            connection = psycopg2.connect(DATABASE_URL)
        except psycopg2.Error as exc:
            raise DatabaseUnavailable(str(exc)) from exc

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, instrument, market_type, timeframe, ts, label_type,
                    direction, price_level, confidence, metadata
                FROM smc_labels
                WHERE market_type = %s
                    AND instrument = %s
                    AND timeframe = %s
                ORDER BY ts DESC, id DESC
                LIMIT %s
                """,
                (market_type, instrument, timeframe, limit),
            )
            return [format_label(row) for row in cursor.fetchall()]
    except psycopg2.Error as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    finally:
        if owns_connection:
            connection.close()


def format_market_card(candle, labels, status):
    return {
        "instrument": candle["instrument"],
        "market_type": candle["market_type"],
        "source": candle["source"],
        "timeframe": candle["timeframe"],
        "timestamp": candle["ts"].isoformat(),
        "candle": {
            "open": candle["open"],
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
            "volume": candle["volume"],
        },
        "smc_labels": [
            {
                "label": label["label_type"],
                "direction": label["direction"],
                "confidence": label["confidence"],
            }
            for label in labels
        ],
        "status": status,
    }


def format_candle(row):
    return {
        "id": row["id"],
        "instrument": row["instrument"],
        "market_type": row["market_type"],
        "source": row["source"],
        "timeframe": row["timeframe"],
        "timestamp": row["ts"].isoformat(),
        "open": row["open"],
        "high": row["high"],
        "low": row["low"],
        "close": row["close"],
        "volume": row["volume"],
    }


def format_label(row):
    return {
        "id": row["id"],
        "instrument": row["instrument"],
        "market_type": row["market_type"],
        "timeframe": row["timeframe"],
        "timestamp": row["ts"].isoformat(),
        "label_type": row["label_type"],
        "direction": row["direction"],
        "price_level": row["price_level"],
        "confidence": row["confidence"],
        "metadata": row["metadata"],
    }
