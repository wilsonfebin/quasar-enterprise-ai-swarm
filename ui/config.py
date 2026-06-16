import os
from datetime import timedelta, timezone

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
TIMEFRAMES = ["1m", "3m", "5m", "15m", "1H", "4H"]
TIMEZONE_OPTIONS = {
    "UTC": timezone.utc,
    "IST": timezone(timedelta(hours=5, minutes=30), "IST"),
    "GMT": timezone.utc,
    "EST": timezone(timedelta(hours=-5), "EST"),
}
PAGE_OPTIONS = ["Live Market Intelligence", "Logs & Review Notes"]
