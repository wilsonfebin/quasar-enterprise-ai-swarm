from psycopg2.extras import Json, RealDictCursor

from app.db import get_connection

SUPPORTED_LABEL_TIMEFRAMES = ("1m", "3m", "5m", "15m", "1H", "4H")
LABEL_TYPES = (
    "BOS_BULLISH",
    "BOS_BEARISH",
    "CHOCH_BULLISH",
    "CHOCH_BEARISH",
    "FVG_BULLISH",
    "FVG_BEARISH",
)


def generate_smc_labels():
    inserted = []
    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT DISTINCT market_type, instrument, timeframe
                FROM market_candles
                WHERE timeframe = ANY(%s)
                ORDER BY market_type, instrument, timeframe
                """,
                (list(SUPPORTED_LABEL_TIMEFRAMES),),
            )
            markets = cursor.fetchall()

            for market in markets:
                cursor.execute(
                    """
                    DELETE FROM smc_labels
                    WHERE market_type = %s
                        AND instrument = %s
                        AND timeframe = %s
                        AND metadata->>'source' = 'phase3_smc_engine'
                    """,
                    (
                        market["market_type"],
                        market["instrument"],
                        market["timeframe"],
                    ),
                )
                cursor.execute(
                    """
                    SELECT *
                    FROM (
                        SELECT id, instrument, market_type, source, timeframe, ts,
                            open, high, low, close, volume
                        FROM market_candles
                        WHERE market_type = %s
                            AND instrument = %s
                            AND timeframe = %s
                        ORDER BY ts DESC, id DESC
                        LIMIT 200
                    ) recent_candles
                    ORDER BY ts ASC, id ASC
                    """,
                    (
                        market["market_type"],
                        market["instrument"],
                        market["timeframe"],
                    ),
                )
                candles = cursor.fetchall()
                labels = build_labels_for_candles(candles)
                if not labels:
                    continue

                cursor.executemany(
                    """
                    INSERT INTO smc_labels (
                        instrument, market_type, timeframe, ts, label_type,
                        direction, price_level, confidence, metadata
                    )
                    VALUES (
                        %(instrument)s, %(market_type)s, %(timeframe)s, %(ts)s,
                        %(label_type)s, %(direction)s, %(price_level)s,
                        %(confidence)s, %(metadata)s
                    )
                    """,
                    [{**label, "metadata": Json(label["metadata"])} for label in labels],
                )
                inserted.extend(range(len(labels)))
        connection.commit()

    return {
        "status": "ok",
        "timeframes": list(SUPPORTED_LABEL_TIMEFRAMES),
        "label_types": list(LABEL_TYPES),
        "inserted_count": len(inserted),
    }


def build_labels_for_candles(candles):
    if not candles:
        return []

    latest = candles[-1]
    previous = candles[-2] if len(candles) > 1 else latest
    earlier = candles[-3] if len(candles) > 2 else previous
    prior_high = max(candle["high"] for candle in candles[:-1]) if len(candles) > 1 else latest["high"]
    prior_low = min(candle["low"] for candle in candles[:-1]) if len(candles) > 1 else latest["low"]

    bullish = latest["close"] >= latest["open"]
    prior_bullish = previous["close"] >= previous["open"]
    fvg_bullish = latest["low"] > earlier["high"]
    fvg_bearish = latest["high"] < earlier["low"]

    candidates = [
        {
            "label_type": "BOS_BULLISH",
            "direction": "BULLISH",
            "price_level": max(latest["close"], prior_high),
            "confidence": 0.84 if latest["close"] >= prior_high else 0.62,
            "rule": "latest_close_breaks_prior_high",
        },
        {
            "label_type": "BOS_BEARISH",
            "direction": "BEARISH",
            "price_level": min(latest["close"], prior_low),
            "confidence": 0.84 if latest["close"] <= prior_low else 0.6,
            "rule": "latest_close_breaks_prior_low",
        },
        {
            "label_type": "CHOCH_BULLISH",
            "direction": "BULLISH",
            "price_level": latest["close"],
            "confidence": 0.78 if bullish and not prior_bullish else 0.58,
            "rule": "bearish_to_bullish_close_shift",
        },
        {
            "label_type": "CHOCH_BEARISH",
            "direction": "BEARISH",
            "price_level": latest["close"],
            "confidence": 0.78 if not bullish and prior_bullish else 0.58,
            "rule": "bullish_to_bearish_close_shift",
        },
        {
            "label_type": "FVG_BULLISH",
            "direction": "BULLISH",
            "price_level": latest["low"],
            "confidence": 0.8 if fvg_bullish else 0.57,
            "rule": "latest_low_above_two_candles_back_high",
        },
        {
            "label_type": "FVG_BEARISH",
            "direction": "BEARISH",
            "price_level": latest["high"],
            "confidence": 0.8 if fvg_bearish else 0.57,
            "rule": "latest_high_below_two_candles_back_low",
        },
    ]

    return [
        {
            "instrument": latest["instrument"],
            "market_type": latest["market_type"],
            "timeframe": latest["timeframe"],
            "ts": latest["ts"],
            "label_type": candidate["label_type"],
            "direction": candidate["direction"],
            "price_level": candidate["price_level"],
            "confidence": candidate["confidence"],
            "metadata": {
                "source": "phase3_smc_engine",
                "rule": candidate["rule"],
                "latest_candle_id": latest["id"],
            },
        }
        for candidate in candidates
    ]
