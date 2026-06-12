import os


class ZerodhaCredentialsMissing(RuntimeError):
    pass


class ZerodhaClient:
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

    def fetch_latest_mcx_candle(self):
        self.ensure_credentials()
        raise NotImplementedError(
            "Zerodha live MCX ingestion is intentionally not enabled in Phase 2."
        )
