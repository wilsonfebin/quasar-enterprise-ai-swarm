import html
import os
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
TIMEFRAMES = ["1m", "3m", "5m", "15m", "1H", "4H"]
TIMEZONE_OPTIONS = {
    "UTC": timezone.utc,
    "IST": timezone(timedelta(hours=5, minutes=30), "IST"),
    "GMT": timezone.utc,
    "EST": timezone(timedelta(hours=-5), "EST"),
}

st.set_page_config(
    page_title="Quasar Enterprise AI Delivery Swarm",
    layout="wide",
)

st.title("Quasar Enterprise AI Delivery Swarm")
st.caption("Live Market Intelligence + Band Agent Workflow Monitor")

page = st.sidebar.radio(
    "Navigation",
    ["Live Market Intelligence", "Logs & Delivery Pack"],
)


def get_json(path: str):
    try:
        response = requests.get(f"{BACKEND_URL}{path}", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"error": str(exc)}


def post_json(path: str):
    try:
        response = requests.post(f"{BACKEND_URL}{path}", timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"error": str(exc)}


st.markdown(
    """
    <style>
    html, body, [class*="css"] {
        font-family: Arial, sans-serif;
        font-size: 11px;
    }
    h1, h2, h3, h4 {
        font-family: Arial, sans-serif;
        font-weight: 700;
    }
    h1 {
        font-size: 24px;
    }
    h2 {
        font-size: 18px;
    }
    h3 {
        font-size: 14px;
    }
    .market-card-title {
        font-size: 18px;
        font-weight: 700;
        margin-bottom: 0.55rem;
    }
    .section-header {
        font-size: 12px;
        font-weight: 700;
        margin: 0.7rem 0 0.45rem 0;
    }
    .body-text {
        font-size: 11px;
    }
    .metric-label {
        font-size: 11px;
        font-weight: 700;
        text-align: center;
    }
    .metric-value {
        font-size: 12px;
        font-weight: 700;
        text-align: center;
    }
    .status-strip, .log-card {
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.035);
    }
    .status-strip {
        padding: 0.45rem 0.65rem;
        margin-bottom: 0.75rem;
        font-size: 0.9rem;
    }
    .candle-direction {
        font-size: 0.86rem;
        font-weight: 600;
        margin: 0.65rem 0 0.35rem 0;
    }
    .market-meta {
        margin: 0.25rem 0 0.7rem 0;
    }
    .market-instrument {
        font-size: 0.88rem;
        font-weight: 700;
        line-height: 1.25;
    }
    .market-feed {
        font-size: 0.78rem;
        opacity: 0.86;
        margin: 0.1rem 0 0.35rem 0;
    }
    .meta-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
    }
    .meta-badge {
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.035);
        padding: 0.16rem 0.42rem;
        font-size: 0.72rem;
        line-height: 1.25;
        white-space: nowrap;
    }
    .ohlc-card {
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.035);
        padding: 0.45rem 0.5rem;
        min-width: 0;
        overflow-wrap: anywhere;
    }
    .ohlc-card.bullish {
        border-color: rgba(46, 160, 67, 0.55);
        box-shadow: inset 3px 0 0 rgba(46, 160, 67, 0.55);
    }
    .ohlc-card.bearish {
        border-color: rgba(248, 81, 73, 0.55);
        box-shadow: inset 3px 0 0 rgba(248, 81, 73, 0.55);
    }
    .ohlc-label {
        opacity: 0.72;
        margin-bottom: 0.15rem;
    }
    .ohlc-value {
        white-space: nowrap;
    }
    .label-chip {
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.035);
        padding: 0.42rem 0.45rem;
        font-size: 0.78rem;
        line-height: 1.25;
        min-height: 34px;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin: 0.18rem 0 0.65rem 0;
    }
    .label-section {
        margin-top: 0.8rem;
    }
    .label-grid-spacer {
        height: 0.15rem;
    }
    .additional-labels-note {
        margin-top: 0.35rem;
        font-size: 0.78rem;
        opacity: 0.82;
    }
    .label-chip-content {
        display: inline-block;
        max-width: 100%;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .label-chip.bullish {
        border-color: rgba(46, 160, 67, 0.55);
        box-shadow: inset 3px 0 0 rgba(46, 160, 67, 0.55);
    }
    .label-chip.bearish {
        border-color: rgba(248, 81, 73, 0.55);
        box-shadow: inset 3px 0 0 rgba(248, 81, 73, 0.55);
    }
    .label-chip.neutral {
        border-color: rgba(187, 128, 9, 0.55);
        box-shadow: inset 3px 0 0 rgba(187, 128, 9, 0.55);
    }
    .log-card {
        height: 300px;
        overflow-y: auto;
        padding: 0.65rem;
        white-space: pre-wrap;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        font-size: 0.78rem;
        line-height: 1.35;
    }
    .agent-card, .agent-summary-card {
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.035);
    }
    .agent-summary-card {
        min-height: 52px;
        padding: 0.42rem 0.4rem;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        opacity: 0.96;
    }
    .agent-card {
        min-height: 72px;
        padding: 0.45rem 0.35rem;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
    }
    .agent-card.completed {
        border-color: rgba(46, 160, 67, 0.55);
        box-shadow: inset 3px 0 0 rgba(46, 160, 67, 0.55);
    }
    .agent-card.running {
        border-color: rgba(56, 139, 253, 0.6);
        box-shadow: inset 3px 0 0 rgba(56, 139, 253, 0.6);
    }
    .agent-card.waiting {
        border-color: rgba(187, 128, 9, 0.55);
        box-shadow: inset 3px 0 0 rgba(187, 128, 9, 0.55);
    }
    .agent-card.failed {
        border-color: rgba(248, 81, 73, 0.55);
        box-shadow: inset 3px 0 0 rgba(248, 81, 73, 0.55);
    }
    .agent-name {
        font-size: 11px;
        font-weight: 700;
        line-height: 1.15;
    }
    .agent-status {
        font-size: 11px;
        opacity: 0.82;
        margin-top: 0.2rem;
    }
    .band-test-card {
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.025);
        padding: 0.55rem 0.65rem;
        margin-top: 0.65rem;
    }
    .band-test-title {
        font-size: 12px;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }
    .band-test-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin-bottom: 0.35rem;
    }
    .band-test-pill {
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.035);
        padding: 0.16rem 0.42rem;
        font-size: 0.72rem;
        line-height: 1.25;
    }
    .band-response {
        border-left: 3px solid rgba(56, 139, 253, 0.55);
        padding-left: 0.5rem;
        margin-top: 0.35rem;
        font-size: 11px;
        line-height: 1.35;
        overflow-wrap: anywhere;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color: rgba(255, 255, 255, 0.10);
        background: rgba(255, 255, 255, 0.015);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def health_ok():
    health = get_json("/health")
    return "error" not in health and health.get("status") == "healthy"


def render_status_strip():
    backend_status = "Backend Healthy" if health_ok() else "Backend Disconnected"
    latest = get_json("/market/latest")
    db_status = "TimescaleDB Healthy" if "error" not in latest else "TimescaleDB Unknown"
    st.sidebar.markdown("**System Status**")
    st.sidebar.caption(f"🟢 {backend_status}")
    st.sidebar.caption(f"🟢 {db_status}")
    st.sidebar.caption("🟡 Live Feed Mode")
    st.sidebar.caption("🟢 Agent Workflow Ready")
    st.sidebar.markdown("**Safety Mode**")
    st.sidebar.caption("🛡 Advisory Only")
    st.sidebar.caption("🚫 No Orders")
    st.sidebar.caption("🚫 No Buy/Sell Signals")


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
        "TWELVEDATA": "TwelveData",
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


def split_label(label_type):
    if label_type in {"LIQUIDITY_SWEEP_HIGH", "LIQUIDITY_SWEEP_LOW"}:
        return "Liquidity Sweep", "NEUTRAL"

    parts = label_type.rsplit("_", 1)
    if len(parts) == 2 and parts[1] in {"BULLISH", "BEARISH"}:
        return parts[0], parts[1]
    return label_type, "NEUTRAL"


def direction_display(direction):
    if direction == "BULLISH":
        return "▲ BULLISH"
    if direction == "BEARISH":
        return "▼ BEARISH"
    return direction


def render_ohlc_row(latest):
    market_type = latest["market_type"]
    instrument = latest["instrument"]
    direction = "bullish" if float(latest["close"]) >= float(latest["open"]) else "bearish"
    direction_text = "🟢 Bullish Candle" if direction == "bullish" else "🔴 Bearish Candle"
    st.markdown(
        f'<div class="candle-direction">{direction_text}</div>',
        unsafe_allow_html=True,
    )
    values = [
        ("Open", format_price(latest["open"], market_type, instrument)),
        ("High", format_price(latest["high"], market_type, instrument)),
        ("Low", format_price(latest["low"], market_type, instrument)),
        ("Close", format_price(latest["close"], market_type, instrument)),
        ("Volume", format_volume(latest["volume"])),
    ]
    columns = st.columns(5)
    for column, (label, value) in zip(columns, values):
        with column:
            st.markdown(
                (
                    f'<div class="ohlc-card {direction}">'
                    f'<div class="ohlc-label metric-label">{html.escape(label)}</div>'
                    f'<div class="ohlc-value metric-value">{html.escape(value)}</div>'
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


def render_smc_labels(label_rows):
    if not label_rows:
        st.info("No SMC labels available.")
        return

    def label_parts(label):
        category, direction = split_label(label["label_type"])
        return category, direction, float(label["confidence"])

    def dedupe_labels(labels):
        best = {}
        for label in labels:
            category, direction, confidence = label_parts(label)
            key = (category, direction)
            if key not in best or confidence > label_parts(best[key])[2]:
                best[key] = label
        return sorted(
            best.values(),
            key=lambda label: label_parts(label)[2],
            reverse=True,
        )

    def render_label_chip(label):
        category, direction, confidence = label_parts(label)
        direction_class = direction.lower() if direction in {"BULLISH", "BEARISH"} else "neutral"
        st.markdown(
            (
                f'<div class="label-chip {direction_class}">'
                '<span class="label-chip-content">'
                f'<strong>{html.escape(category)}</strong>&nbsp;&nbsp;'
                f'{html.escape(direction_display(direction))}&nbsp;&nbsp;'
                f'{html.escape(format_confidence(confidence))}'
                "</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

    unique_labels = dedupe_labels(label_rows)
    visible_labels = unique_labels[:3]
    additional_labels = unique_labels[3:]

    st.markdown('<div class="label-grid-spacer"></div>', unsafe_allow_html=True)
    label_cols = st.columns(3)
    for index, label in enumerate(visible_labels):
        with label_cols[index % 3]:
            render_label_chip(label)

    st.markdown('<div class="label-grid-spacer"></div>', unsafe_allow_html=True)
    with st.expander("Additional Market Structure Labels", expanded=False):
        if not additional_labels:
            st.markdown(
                '<div class="additional-labels-note">No additional labels.</div>',
                unsafe_allow_html=True,
            )
        else:
            for start in range(0, len(additional_labels), 3):
                row_labels = additional_labels[start : start + 3]
                row_cols = st.columns(3)
                for col, label in zip(row_cols, row_labels):
                    with col:
                        render_label_chip(label)


def render_market_card(title, market_type, instrument, timezone_name):
    with st.container(border=True):
        st.markdown(
            f'<div class="market-card-title">{html.escape(title)}</div>',
            unsafe_allow_html=True,
        )
        timeframe = st.radio(
            "Timeframe",
            TIMEFRAMES,
            key=f"{market_type.lower()}_timeframe",
            horizontal=True,
        )
        candles = get_json(
            f"/market/candles?market_type={market_type}&instrument={instrument}&timeframe={timeframe}&limit=20"
        )
        labels = get_json(
            f"/smc/labels?market_type={market_type}&instrument={instrument}&timeframe={timeframe}&limit=20"
        )

        if "error" in candles:
            st.error(candles["error"])
            return

        candle_rows = candles.get("candles", [])
        if not candle_rows:
            st.info(candles.get("message", f"No {timeframe} candles available."))
            return

        latest = candle_rows[0]
        updated_at = format_short_timestamp(latest["timestamp"], timezone_name)
        data_age = format_freshness(latest["timestamp"], timezone_name)
        session_text = market_session_text(market_type, latest["timestamp"])
        st.markdown(
            (
                '<div class="market-meta">'
                f'<div class="market-instrument">{html.escape(latest["instrument"])}</div>'
                '<div class="market-feed">'
                f'{html.escape(status_badge(candles.get("status"), latest["source"]))}'
                f' &bull; Source: {html.escape(readable_source(latest["source"], timeframe))}'
                "</div>"
                '<div class="meta-badges">'
                f'<span class="meta-badge">Updated {html.escape(updated_at)}</span>'
                f'<span class="meta-badge">Data Age {html.escape(data_age)}</span>'
                f'<span class="meta-badge">{html.escape(session_text)}</span>'
                "</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        render_ohlc_row(latest)

        st.markdown(
            '<div class="section-header label-section">Market Structure Labels</div>',
            unsafe_allow_html=True,
        )
        if "error" in labels:
            st.error(labels["error"])
        elif not labels.get("labels"):
            st.info(labels.get("message", "No market structure labels available."))
        else:
            render_smc_labels(labels.get("labels", []))


def render_agent_monitor():
    workflow = get_json("/agents/workflow-status")
    band_status = get_json("/agents/band/status")
    band_chats = get_json("/agents/band/chats")

    with st.container(border=True):
        st.markdown(
            '<div class="market-card-title">Agent Swarm Monitor</div>',
            unsafe_allow_html=True,
        )

        if "error" in workflow:
            st.error(workflow["error"])
            return

        completed_agents = sum(
            1 for step in workflow["steps"] if step["status"] == "completed"
        )
        if band_status.get("status") == "connected":
            band_label = "🟢 Connected"
        elif band_status.get("status") == "missing_credentials":
            band_label = "🟡 Config Missing"
        else:
            band_label = "🔴 Disconnected"
        summary_cards = [
            ("Workflow Progress", f"{workflow['progress']}%"),
            ("Completed Agents", f"{completed_agents}/{len(workflow['steps'])}"),
            ("Active Agent", workflow["current_agent"]),
            ("Band Status", band_label),
        ]
        summary_cols = st.columns(4)
        for col, (label, value) in zip(summary_cols, summary_cards):
            with col:
                st.markdown(
                    (
                        '<div class="agent-summary-card">'
                        f'<div class="metric-label">{html.escape(label)}</div>'
                        f'<div class="metric-value">{html.escape(value)}</div>'
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )

        st.progress(workflow["progress"] / 100)

        display_names = {
            "Requirement Agent": "Requirement",
            "Market Intelligence Agent": "Market Intelligence",
            "Architecture Agent": "Architecture",
            "Risk Governance Agent": "Risk Governance",
            "Delivery Planning Agent": "Delivery Planning",
            "Final Review Agent": "Final Review",
        }
        status_labels = {
            "completed": "✅ Completed",
            "running": "🔄 Running",
            "waiting": "⏳ Waiting",
            "failed": "⚠ Failed",
        }
        agent_cols = st.columns(6)
        for col, step in zip(agent_cols, workflow["steps"]):
            with col:
                status_class = step["status"] if step["status"] in status_labels else "waiting"
                st.markdown(
                    (
                        f'<div class="agent-card {status_class}">'
                        f'<div class="agent-name">{html.escape(display_names.get(step["agent"], step["agent"]))}</div>'
                        f'<div class="agent-status">{html.escape(status_labels.get(step["status"], step["status"].title()))}</div>'
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )

        chat_count = band_chats.get("count", 0) if "error" not in band_chats else 0
        last_test = st.session_state.get("band_workflow_test", {})
        last_process = st.session_state.get("band_process_next", {})
        workflow_band = workflow.get("band", {})
        last_test_status = "Not run"
        if last_test:
            last_test_status = "Success" if last_test.get("success") else "Failed"
        last_process_status = (
            last_process.get("status")
            or workflow_band.get("last_message_status")
            or "not_run"
        )
        last_chat_id = last_process.get("chat_id") or workflow_band.get("last_chat_id") or "—"
        last_message_id = (
            last_process.get("message_id")
            or workflow_band.get("last_message_id")
            or "—"
        )
        last_response_time = last_test.get("response_time", "—")
        latest_response = last_test.get("latest_message", "")

        st.markdown(
            (
                '<div class="band-test-card">'
                '<div class="band-test-title">Band Workflow Test</div>'
                '<div class="band-test-row">'
                f'<span class="band-test-pill">Band Connected: {html.escape("Yes" if band_status.get("status") == "connected" else "No")}</span>'
                f'<span class="band-test-pill">Chat Rooms Available: {html.escape(str(chat_count))}</span>'
                f'<span class="band-test-pill">Last Workflow Test: {html.escape(last_test_status)}</span>'
                f'<span class="band-test-pill">Last Band Processing Status: {html.escape(str(last_process_status))}</span>'
                f'<span class="band-test-pill">Last Chat ID: {html.escape(str(last_chat_id))}</span>'
                f'<span class="band-test-pill">Last Message ID: {html.escape(str(last_message_id))}</span>'
                f'<span class="band-test-pill">Last Response Time: {html.escape(last_response_time)}</span>'
                "</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        if st.button("Run Band Test", key="run_band_test", use_container_width=True):
            st.session_state["band_workflow_test"] = post_json(
                "/agents/band/test-workflow"
            )
            st.rerun()
        if st.button(
            "Process Next Band Message",
            key="process_next_band_message",
            use_container_width=True,
        ):
            st.session_state["band_process_next"] = post_json(
                "/agents/band/process-next"
            )
            st.rerun()

        if last_process:
            process_status = last_process.get("status", "unknown")
            if process_status == "processed":
                st.success("Band message processed.")
            elif process_status == "no_messages":
                st.info("No pending Band messages.")
            else:
                st.warning(last_process.get("error", "Band processing did not complete."))

        if last_test:
            if last_test.get("success"):
                st.success("Band workflow test completed.")
            else:
                st.warning(last_test.get("message", "Band workflow test did not complete."))
            st.markdown(
                (
                    '<div class="band-response">'
                    f'<strong>Chat ID:</strong> {html.escape(str(last_test.get("chat_id", "—")))}<br>'
                    f'<strong>Latest Band Response:</strong> {html.escape(str(latest_response or "No response text returned."))}'
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


if page == "Live Market Intelligence":
    render_status_strip()

    selected_timezone = st.sidebar.radio(
        "Timezone",
        list(TIMEZONE_OPTIONS.keys()),
        horizontal=True,
        key="global_timezone",
    )
    if st.sidebar.button("Simulate Live Market Update", use_container_width=True):
        refresh_result = post_json("/market/ingest/mock")
        st.session_state["last_refresh_result"] = refresh_result
        st.session_state["last_refresh_snapshot"] = get_json("/market/latest")
        if "error" in refresh_result:
            st.sidebar.error(refresh_result["error"])
        else:
            st.sidebar.success("Mock data refreshed.")
            st.rerun()

    if "last_refresh_result" in st.session_state:
        result = st.session_state["last_refresh_result"]
        if "inserted" in result:
            st.sidebar.caption(f"Last refresh inserted {len(result['inserted'])} candles.")

    col1, col2 = st.columns(2)

    with col1:
        render_market_card(
            "MCX Live Intelligence",
            market_type="MCX",
            instrument="NATURALGAS",
            timezone_name=selected_timezone,
        )

    with col2:
        render_market_card(
            "Forex Live Intelligence",
            market_type="FOREX",
            instrument="XAUUSD",
            timezone_name=selected_timezone,
        )

    st.divider()
    render_agent_monitor()

else:
    st.subheader("System Logs")

    def render_log_card(title, log_name):
        st.write(title)
        log_data = get_json(f"/logs/{log_name}")
        lines = log_data.get("lines", [])[-18:]
        padded_lines = lines + [""] * max(0, 18 - len(lines))
        escaped_log = html.escape("\n".join(padded_lines))
        st.markdown(
            f'<div class="log-card">{escaped_log}</div>',
            unsafe_allow_html=True,
        )

    log_col1, log_col2 = st.columns(2)

    with log_col1:
        render_log_card("MCX Logs", "mcx")
        render_log_card("Backend Logs", "backend")

    with log_col2:
        render_log_card("Forex Logs", "forex")
        render_log_card("Agent Workflow Logs", "agent")

    st.divider()

    st.subheader("Enterprise Delivery Pack")
    st.markdown(
        """
        ### Requirement Summary
        Build a regulated financial AI delivery platform with live MCX and Forex intelligence.

        ### Architecture Summary
        FastAPI, Streamlit, TimescaleDB, Docker, Band agents, and AWS deployment.

        ### Governance Summary
        No trade execution. No buy/sell recommendations. SMC labels are used only for market-structure intelligence.

        ### Delivery Roadmap
        Foundation → Live Data → SMC Labels → Band Agents → Logs → AWS Deployment.
        """
    )
