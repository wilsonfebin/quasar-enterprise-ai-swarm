from app.db import get_connection

SUPPORTED_AGGREGATE_TIMEFRAMES = ("3m", "5m", "15m", "1H", "4H")
MIN_SOURCE_CANDLES = {
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "1H": 60,
    "4H": 240,
}


def _interval_for_timeframe(timeframe):
    if timeframe.endswith("H"):
        hours = int(timeframe.removesuffix("H"))
        return f"{hours} hours"

    minutes = int(timeframe.removesuffix("m"))
    return f"{minutes} minutes"


def _source_priority_sql():
    return """
        CASE
            WHEN source IN ('TWELVEDATA', 'ZERODHA') THEN 0
            WHEN source = 'AGG_1M' THEN 1
            ELSE 2
        END
    """


def aggregate_1m_candles():
    inserted = []
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT market_type, instrument
                FROM market_candles
                WHERE timeframe = '1m'
                """
            )
            markets = cursor.fetchall()

            for market_type, instrument in markets:
                cursor.execute(
                    f"""
                    SELECT source
                    FROM market_candles
                    WHERE market_type = %s
                        AND instrument = %s
                        AND timeframe = '1m'
                    ORDER BY {_source_priority_sql()}, inserted_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (market_type, instrument),
                )
                source_row = cursor.fetchone()
                source = source_row[0] if source_row else None
                if not source:
                    continue

                for timeframe in SUPPORTED_AGGREGATE_TIMEFRAMES:
                    cursor.execute(
                        """
                        DELETE FROM market_candles
                        WHERE market_type = %s
                            AND instrument = %s
                            AND timeframe = %s
                            AND source = 'AGG_1M'
                        """,
                        (market_type, instrument, timeframe),
                    )
                    cursor.execute(
                        """
                        INSERT INTO market_candles (
                            instrument, market_type, source, timeframe, ts,
                            open, high, low, close, volume
                        )
                        SELECT
                            instrument,
                            market_type,
                            'AGG_1M' AS source,
                            %s AS timeframe,
                            time_bucket((%s)::interval, ts) AS bucket_ts,
                            (array_agg(open ORDER BY ts ASC, id ASC))[1] AS open,
                            MAX(high) AS high,
                            MIN(low) AS low,
                            (array_agg(close ORDER BY ts DESC, id DESC))[1] AS close,
                            SUM(volume) AS volume
                        FROM market_candles
                        WHERE market_type = %s
                            AND instrument = %s
                            AND timeframe = '1m'
                            AND source = %s
                            AND ts < time_bucket((%s)::interval, NOW())
                        GROUP BY instrument, market_type, bucket_ts
                        HAVING COUNT(*) >= %s
                        ORDER BY bucket_ts ASC
                        RETURNING id
                        """,
                        (
                            timeframe,
                            _interval_for_timeframe(timeframe),
                            market_type,
                            instrument,
                            source,
                            _interval_for_timeframe(timeframe),
                            MIN_SOURCE_CANDLES.get(timeframe, 1),
                        ),
                    )
                    inserted.extend(row[0] for row in cursor.fetchall())
        connection.commit()

    return {
        "status": "ok",
        "timeframes": list(SUPPORTED_AGGREGATE_TIMEFRAMES),
        "inserted_count": len(inserted),
        "inserted_ids": inserted,
    }
