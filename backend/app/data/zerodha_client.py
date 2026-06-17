import csv
import os
from datetime import datetime, timedelta, timezone
from io import StringIO
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError


class ZerodhaCredentialsMissing(RuntimeError):
    pass


class ZerodhaInstrumentMissing(RuntimeError):
    pass


class ZerodhaApiError(RuntimeError):
    def __init__(self, status_code, message, error_type="", path=""):
        self.status_code = status_code
        self.message = message
        self.error_type = error_type
        self.path = path
        detail = f"Zerodha API {status_code}: {message}"
        if error_type:
            detail = f"{detail} ({error_type})"
        super().__init__(detail)


class ZerodhaClient:
    base_url = "https://api.kite.trade"
    exchange_timezone = timezone(timedelta(hours=5, minutes=30))

    def __init__(self, api_key=None, access_token=None):
        self.api_key = api_key or os.getenv("ZERODHA_API_KEY", "")
        self.access_token = access_token or os.getenv("ZERODHA_ACCESS_TOKEN", "")

    def ensure_credentials(self):
        missing = []
        if not self.api_key:
            missing.append("ZERODHA_API_KEY")
        if not self.access_token:
            missing.append("ZERODHA_ACCESS_TOKEN")

        if missing:
            raise ZerodhaCredentialsMissing(
                f"Missing Zerodha credentials: {', '.join(missing)}"
            )

    def _headers(self):
        self.ensure_credentials()
        return {
            "X-Kite-Version": "3",
            "Authorization": f"token {self.api_key}:{self.access_token}",
        }

    def _get_text(self, path, params=None, timeout=30):
        query = f"?{urlencode(params)}" if params else ""
        request = Request(
            f"{self.base_url}{path}{query}",
            headers=self._headers(),
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read().decode()
        except HTTPError as exc:
            body = exc.read().decode(errors="replace")
            message = exc.reason or "Zerodha API request failed"
            error_type = ""
            if body:
                try:
                    import json

                    payload = json.loads(body)
                    message = payload.get("message") or message
                    error_type = payload.get("error_type") or ""
                except Exception:
                    message = body[:240]
            raise ZerodhaApiError(
                status_code=exc.code,
                message=message,
                error_type=error_type,
                path=path,
            ) from exc

    def _get_json(self, path, params=None, timeout=30):
        import json

        payload = self._get_text(path, params=params, timeout=timeout)
        data = json.loads(payload)
        if data.get("status") == "error":
            message = data.get("message") or data.get("error_type") or "Zerodha API error"
            raise RuntimeError(message)
        return data

    def resolve_mcx_instrument(self, base_instrument=None, tradingsymbol=None):
        configured_token = os.getenv("ZERODHA_MCX_INSTRUMENT_TOKEN", "").strip()
        configured_symbol = tradingsymbol or os.getenv("ZERODHA_MCX_TRADINGSYMBOL", "").strip()
        base = (base_instrument or os.getenv("ZERODHA_MCX_INSTRUMENT", "NATURALGAS")).upper()

        if configured_token:
            return {
                "instrument_token": configured_token,
                "tradingsymbol": configured_symbol or base,
                "name": base,
                "expiry": "",
                "source": "env_token",
            }

        csv_text = self._get_text("/instruments/MCX", timeout=45)
        today = datetime.now(timezone.utc).date()
        candidates = []
        for row in csv.DictReader(StringIO(csv_text)):
            symbol = (row.get("tradingsymbol") or "").upper()
            name = (row.get("name") or "").upper()
            instrument_type = (row.get("instrument_type") or "").upper()
            if configured_symbol and symbol != configured_symbol.upper():
                continue
            if not configured_symbol and not (symbol.startswith(base) or name == base):
                continue
            if instrument_type != "FUT":
                continue
            expiry_raw = row.get("expiry") or ""
            try:
                expiry = datetime.fromisoformat(expiry_raw).date()
            except ValueError:
                continue
            if expiry < today:
                continue
            candidates.append((expiry, row))

        if not candidates:
            target = configured_symbol or base
            raise ZerodhaInstrumentMissing(
                f"No live MCX futures instrument found for {target}"
            )

        expiry, selected = sorted(candidates, key=lambda item: item[0])[0]
        return {
            "instrument_token": selected["instrument_token"],
            "tradingsymbol": selected["tradingsymbol"],
            "name": selected.get("name") or base,
            "expiry": expiry.isoformat(),
            "source": "instrument_dump",
        }

    def fetch_mcx_candles(
        self,
        start_at,
        end_at,
        instrument="NATURALGAS",
        instrument_token=None,
        tradingsymbol=None,
        timeframe="1m",
    ):
        resolved = (
            {
                "instrument_token": str(instrument_token),
                "tradingsymbol": tradingsymbol or instrument,
                "name": instrument,
                "expiry": "",
                "source": "argument",
            }
            if instrument_token
            else self.resolve_mcx_instrument(instrument, tradingsymbol=tradingsymbol)
        )
        token = resolved["instrument_token"]
        fetched_at = datetime.now(timezone.utc)
        exchange_start = start_at.astimezone(self.exchange_timezone)
        exchange_end = end_at.astimezone(self.exchange_timezone)
        params = {
            "from": exchange_start.strftime("%Y-%m-%d %H:%M:%S"),
            "to": exchange_end.strftime("%Y-%m-%d %H:%M:%S"),
            "continuous": 0,
            "oi": 0,
        }
        data = self._get_json(
            f"/instruments/historical/{token}/minute",
            params=params,
            timeout=45,
        )
        rows = (data.get("data") or {}).get("candles") or []
        candles = []
        rejected_future = 0
        for row in rows:
            ts = datetime.fromisoformat(str(row[0]))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=self.exchange_timezone)
            ts = ts.astimezone(timezone.utc)
            if ts > fetched_at + timedelta(minutes=2):
                rejected_future += 1
                continue
            candles.append(
                {
                    "instrument": instrument,
                    "market_type": "MCX",
                    "source": "ZERODHA",
                    "timeframe": timeframe,
                    "ts": ts,
                    "fetched_at": fetched_at,
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5] if len(row) > 5 else 0),
                }
            )

        return {
            "instrument": instrument,
            "instrument_token": token,
            "tradingsymbol": resolved.get("tradingsymbol", ""),
            "expiry": resolved.get("expiry", ""),
            "instrument_source": resolved.get("source", ""),
            "start_at": start_at.astimezone(timezone.utc).isoformat(),
            "end_at": end_at.astimezone(timezone.utc).isoformat(),
            "fetched_at": fetched_at.isoformat(),
            "returned_count": len(rows),
            "accepted_count": len(candles),
            "rejected_future_count": rejected_future,
            "candles": candles,
        }

    def fetch_latest_mcx_candle(self):
        end_at = datetime.now(timezone.utc)
        start_at = end_at - timedelta(days=1)
        result = self.fetch_mcx_candles(start_at, end_at)
        candles = result["candles"]
        if not candles:
            raise RuntimeError("Zerodha returned no MCX candle values")
        latest = candles[-1]
        latest["provider"] = {
            "instrument_token": result["instrument_token"],
            "tradingsymbol": result["tradingsymbol"],
            "expiry": result["expiry"],
        }
        return latest
