import os
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen


class TwelveDataCredentialsMissing(RuntimeError):
    pass


class TwelveDataClient:
    base_url = "https://api.twelvedata.com/time_series"

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("TWELVEDATA_API_KEY", "")

    def fetch_latest_forex_candle(
        self,
        instrument="XAUUSD",
        symbol="XAU/USD",
        timeframe="1m",
    ):
        if not self.api_key:
            raise TwelveDataCredentialsMissing("TWELVEDATA_API_KEY is not configured")

        params = urlencode(
            {
                "symbol": symbol,
                "interval": "1min",
                "outputsize": 1,
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

        value = values[0]
        ts = datetime.fromisoformat(value["datetime"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        return {
            "instrument": instrument,
            "market_type": "FOREX",
            "source": "TWELVEDATA",
            "timeframe": timeframe,
            "ts": ts,
            "open": float(value["open"]),
            "high": float(value["high"]),
            "low": float(value["low"]),
            "close": float(value["close"]),
            "volume": float(value.get("volume") or 0),
        }
