from datetime import datetime, timezone

from config import TIMEZONE_OPTIONS

def format_price(value, market_type=None, instrument=None):
    if market_type == "MCX" and instrument == "NATURALGAS":
        return f"{float(value):.2f}"
    return f"{float(value):.5f}"


def format_volume(value):
    return f"{float(value):,.0f}"


def format_confidence(value):
    return f"{float(value) * 100:.0f}%"


def format_timestamp(value, timezone_name):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        target = parsed.astimezone(TIMEZONE_OPTIONS[timezone_name])
        return target.strftime(f"%Y-%m-%d %H:%M:%S {timezone_name}")
    except Exception:
        return value


def format_short_timestamp(value, timezone_name):
    try:
        parsed = parse_timestamp(value)
        target = parsed.astimezone(TIMEZONE_OPTIONS[timezone_name])
        return target.strftime(f"%H:%M {timezone_name}")
    except Exception:
        return value


def parse_timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_freshness(value, timezone_name):
    try:
        target_time = parse_timestamp(value).astimezone(TIMEZONE_OPTIONS[timezone_name])
        now = datetime.now(TIMEZONE_OPTIONS[timezone_name])
        elapsed = max(0, int((now - target_time).total_seconds()))
        if elapsed < 60:
            return "just now"
        if elapsed < 3600:
            return f"{elapsed // 60}m"
        if elapsed < 86400:
            return f"{elapsed // 3600}h"
        return f"{elapsed // 86400}d"
    except Exception:
        return "unavailable"


def true_freshness_label(value, timezone_name):
    try:
        target_time = parse_timestamp(value).astimezone(TIMEZONE_OPTIONS[timezone_name])
        now = datetime.now(TIMEZONE_OPTIONS[timezone_name])
        elapsed = int((now - target_time).total_seconds())
        if elapsed < -60:
            return "provider time ahead"
        if elapsed < 60:
            return "just now"
        if elapsed < 3600:
            return f"{elapsed // 60}m old"
        if elapsed < 86400:
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            return f"{hours}h {minutes}m old"
        return f"{elapsed // 86400}d old"
    except Exception:
        return "unavailable"


def market_session_text(market_type, timestamp):
    try:
        parsed = parse_timestamp(timestamp)
    except Exception:
        return "Session unavailable"

    if market_type == "MCX":
        ist_time = parsed.astimezone(TIMEZONE_OPTIONS["IST"])
        if ist_time.weekday() < 5 and 9 <= ist_time.hour < 23:
            return "MCX Active"
        return "MCX Closed"

    utc_hour = parsed.astimezone(timezone.utc).hour
    if 12 <= utc_hour < 16:
        return "Forex: Overlap"
    if 0 <= utc_hour < 7:
        return "Forex: Asia"
    if 7 <= utc_hour < 12:
        return "Forex: London"
    if 16 <= utc_hour < 21:
        return "Forex: New York"
    return "Forex: Off Hours"


def readable_source(source, timeframe):
    source_map = {
        "AGG_1M": f"Aggregated {timeframe}",
        "MOCK_INGEST": "Mock Ingest",
        "MOCK_MCX": "Mock MCX",
        "MOCK_FOREX": "Mock Forex",
        "TWELVEDATA": "TWELVEDATA",
        "ZERODHA": "Zerodha",
    }
    return source_map.get(source, source.replace("_", " ").title())


def status_badge(status, source=None):
    if status in {"MOCK_LIVE", "MOCK_INGEST"} or source in {
        "MOCK_INGEST",
        "MOCK_MCX",
        "MOCK_FOREX",
    }:
        return "🟡 Live Feed"
    if source in {"TWELVEDATA", "ZERODHA"}:
        return "🟢 Live Data"
    if status == "DB":
        return "🟢 DB"
    return "🔴 DISCONNECTED"


def coverage_label(health):
    percent = float(health.get("coverage_percent") or 0)
    if percent >= 90:
        return "Strong"
    if percent >= 50:
        return "Moderate"
    if percent > 0:
        return "Low"
    return "None"


def analysis_readiness(health, configured=True):
    total = int(health.get("total_candles") or 0)
    expected_7d = 10080
    expected_30d = 43200
    gap = int(health.get("largest_gap_minutes") or 0)
    if not configured or total == 0:
        return "Not Ready"
    if total >= expected_30d and gap <= 10:
        return "Strong"
    if total >= expected_7d:
        return "Moderate"
    return "Weak"


def display_scope_label(scope_value: str, fallback: str = "MCX NATURALGAS") -> str:
    scope = str(scope_value or "").upper()
    if scope == "FOREX" or "XAUUSD" in str(scope_value).upper():
        return "Forex XAUUSD"
    if scope == "MCX" or "NATURALGAS" in str(scope_value).upper():
        return "MCX NATURALGAS"
    return fallback


def extract_line_value(text: str, label: str) -> str:
    lines = str(text or "").splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith(label.lower()):
            value = stripped[len(label) :].strip(" :")
            if value:
                return value
            if index + 1 < len(lines):
                return lines[index + 1].strip(" -")
    return ""


def extract_section_lines(text: str, start_label: str, stop_labels: list[str]) -> list[str]:
    lines = str(text or "").splitlines()
    collected: list[str] = []
    collecting = False
    for line in lines:
        stripped = line.strip()
        if not collecting and stripped.lower().startswith(start_label.lower()):
            collecting = True
            remainder = stripped[len(start_label) :].strip(" :")
            if remainder:
                collected.append(remainder)
            continue
        if collecting:
            if any(stripped.lower().startswith(stop.lower()) for stop in stop_labels):
                break
            if stripped:
                collected.append(stripped.strip("- "))
    return collected


def confidence_label(summary: str) -> str:
    text = str(summary or "")
    percents = []
    for token in text.replace(",", " ").split():
        if token.endswith("%"):
            try:
                percents.append(int(token.strip("%.")))
            except ValueError:
                pass
    if not percents:
        return "Waiting" if not summary else "Moderate"
    average = sum(percents[:3]) / min(len(percents), 3)
    if average >= 75:
        return "Strong"
    if average >= 55:
        return "Moderate"
    return "Weak"
