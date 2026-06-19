import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import urlopen


class TwelveDataCredentialsMissing(RuntimeError):
    pass


class TwelveDataClient:
    base_url = "https://api.twelvedata.com/time_series"

    def __init__(self, api_key=None, symbol=None):
        self.api_key = api_key or os.getenv("TWELVEDATA_API_KEY", "")
        self.symbol = symbol or os.getenv("TWELVEDATA_SYMBOL_FOREX", "XAUUSD")
        self.exchange_timezone = os.getenv("TWELVEDATA_EXCHANGE_TIMEZONE", "Asia/Kolkata")

    def fetch_latest_forex_candle(
        self,
        instrument="XAUUSD",
        symbol=None,
        timeframe="1m",
    ):
        if not self.api_key:
            raise TwelveDataCredentialsMissing("TWELVEDATA_API_KEY is not configured")
        requested_symbol = symbol or self.symbol
        api_symbol = self._provider_symbol(requested_symbol)
        fetched_at = datetime.now(timezone.utc)

        params = urlencode(
            {
                "symbol": api_symbol,
                "interval": "1min",
                "outputsize": 1,
                "timezone": "UTC",
                "apikey": self.api_key,
            }
        )
        with urlopen(f"{self.base_url}?{params}", timeout=10) as response:
            payload = response.read().decode()

        import json

        data = json.loads(payload)
        if data.get("status") == "error":
            raise RuntimeError(data.get("message", "TwelveData returned an error"))

        values = data.get("values") or []
        if not values:
            raise RuntimeError("TwelveData returned no candle values")

        meta = data.get("meta") or {}
        returned_symbol = (
            meta.get("symbol")
            or meta.get("currency_pair")
            or meta.get("instrument")
            or api_symbol
        )
        value = values[0]
        raw_datetime = value["datetime"]
        ts = datetime.fromisoformat(raw_datetime)
        if ts.tzinfo is None:
            # The request asks TwelveData for timezone=UTC. Latest responses can
            # still arrive without a tz suffix, so interpret naive values as UTC.
            ts = ts.replace(tzinfo=timezone.utc)
        ts = ts.astimezone(timezone.utc)
        timestamp_corrected = False
        timestamp_correction_reason = ""
        if ts > fetched_at + timedelta(minutes=2):
            timestamp_corrected = True
            timestamp_correction_reason = "provider_timestamp_ahead_of_fetch_time"
            ts = fetched_at.replace(second=0, microsecond=0)

        return {
            "instrument": instrument,
            "market_type": "FOREX",
            "source": "TWELVEDATA",
            "timeframe": timeframe,
            "ts": ts,
            "fetched_at": fetched_at,
            "open": float(value["open"]),
            "high": float(value["high"]),
            "low": float(value["low"]),
            "close": float(value["close"]),
            "volume": float(value.get("volume") or 0),
            "provider": {
                "requested_symbol": requested_symbol,
                "provider_query_symbol": api_symbol,
                "returned_symbol": returned_symbol,
                "raw_datetime": raw_datetime,
                "timestamp_corrected": timestamp_corrected,
                "timestamp_correction_reason": timestamp_correction_reason,
                "exchange": meta.get("exchange"),
                "type": meta.get("type"),
            },
        }

    def fetch_latest_forex_candles(
        self,
        instrument="XAUUSD",
        symbol=None,
        timeframe="1m",
        outputsize=None,
    ):
        if not self.api_key:
            raise TwelveDataCredentialsMissing("TWELVEDATA_API_KEY is not configured")
        requested_symbol = symbol or self.symbol
        api_symbol = self._provider_symbol(requested_symbol)
        fetched_at = datetime.now(timezone.utc)
        window = outputsize if outputsize is not None else int(
            os.getenv("TWELVEDATA_LIVE_OUTPUTSIZE", "300")
        )
        window = max(1, min(int(window), 500))

        params = urlencode(
            {
                "symbol": api_symbol,
                "interval": "1min",
                "outputsize": window,
                "order": "ASC",
                "timezone": "UTC",
                "apikey": self.api_key,
            }
        )
        with urlopen(f"{self.base_url}?{params}", timeout=15) as response:
            payload = response.read().decode()

        import json

        data = json.loads(payload)
        if data.get("status") == "error":
            raise RuntimeError(data.get("message", "TwelveData returned an error"))

        values = data.get("values") or []
        if not values:
            raise RuntimeError("TwelveData returned no candle values")

        meta = data.get("meta") or {}
        returned_symbol = (
            meta.get("symbol")
            or meta.get("currency_pair")
            or meta.get("instrument")
            or api_symbol
        )
        candles = []
        rejected_future = 0
        for value in values:
            raw_datetime = value["datetime"]
            ts = datetime.fromisoformat(raw_datetime)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ts = ts.astimezone(timezone.utc)
            timestamp_corrected = False
            timestamp_correction_reason = ""
            if ts > fetched_at + timedelta(minutes=2):
                rejected_future += 1
                timestamp_corrected = True
                timestamp_correction_reason = "provider_timestamp_ahead_of_fetch_time"
                continue
            candles.append(
                {
                    "instrument": instrument,
                    "market_type": "FOREX",
                    "source": "TWELVEDATA",
                    "timeframe": timeframe,
                    "ts": ts,
                    "fetched_at": fetched_at,
                    "open": float(value["open"]),
                    "high": float(value["high"]),
                    "low": float(value["low"]),
                    "close": float(value["close"]),
                    "volume": float(value.get("volume") or 0),
                    "provider": {
                        "requested_symbol": requested_symbol,
                        "provider_query_symbol": api_symbol,
                        "returned_symbol": returned_symbol,
                        "raw_datetime": raw_datetime,
                        "timestamp_corrected": timestamp_corrected,
                        "timestamp_correction_reason": timestamp_correction_reason,
                        "exchange": meta.get("exchange"),
                        "type": meta.get("type"),
                    },
                }
            )

        if not candles:
            raise RuntimeError("TwelveData returned no usable candle values")

        return {
            "requested_symbol": requested_symbol,
            "provider_query_symbol": api_symbol,
            "returned_symbol": returned_symbol,
            "fetched_at": fetched_at.isoformat(),
            "outputsize": window,
            "returned_count": len(values),
            "accepted_count": len(candles),
            "rejected_future_count": rejected_future,
            "candles": candles,
        }

    def fetch_forex_candles(
        self,
        start_at,
        end_at,
        instrument="XAUUSD",
        symbol=None,
        timeframe="1m",
    ):
        if not self.api_key:
            raise TwelveDataCredentialsMissing("TWELVEDATA_API_KEY is not configured")
        requested_symbol = symbol or self.symbol
        api_symbol = self._provider_symbol(requested_symbol)
        fetched_at = datetime.now(timezone.utc)

        params = urlencode(
            {
                "symbol": api_symbol,
                "interval": "1min",
                "start_date": start_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "end_date": end_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "order": "ASC",
                "timezone": "UTC",
                "apikey": self.api_key,
            }
        )
        with urlopen(f"{self.base_url}?{params}", timeout=30) as response:
            payload = response.read().decode()

        import json

        data = json.loads(payload)
        if data.get("status") == "error":
            raise RuntimeError(data.get("message", "TwelveData returned an error"))

        values = data.get("values") or []
        meta = data.get("meta") or {}
        returned_symbol = (
            meta.get("symbol")
            or meta.get("currency_pair")
            or meta.get("instrument")
            or api_symbol
        )

        candles = []
        rejected_future = 0
        for value in values:
            raw_datetime = value["datetime"]
            ts = datetime.fromisoformat(raw_datetime)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ts = ts.astimezone(timezone.utc)
            if ts > fetched_at + timedelta(minutes=2):
                rejected_future += 1
                continue
            candles.append(
                {
                    "instrument": instrument,
                    "market_type": "FOREX",
                    "source": "TWELVEDATA",
                    "timeframe": timeframe,
                    "ts": ts,
                    "fetched_at": fetched_at,
                    "open": float(value["open"]),
                    "high": float(value["high"]),
                    "low": float(value["low"]),
                    "close": float(value["close"]),
                    "volume": float(value.get("volume") or 0),
                }
            )

        return {
            "requested_symbol": requested_symbol,
            "provider_query_symbol": api_symbol,
            "returned_symbol": returned_symbol,
            "start_at": start_at.astimezone(timezone.utc).isoformat(),
            "end_at": end_at.astimezone(timezone.utc).isoformat(),
            "fetched_at": fetched_at.isoformat(),
            "returned_count": len(values),
            "accepted_count": len(candles),
            "rejected_future_count": rejected_future,
            "candles": candles,
        }

    @staticmethod
    def _provider_symbol(symbol):
        compact = str(symbol or "").replace("/", "").upper()
        if compact == "XAUUSD":
            return "XAU/USD"
        return symbol
