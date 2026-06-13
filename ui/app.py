import html
import os
import threading
import time
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
    ["Live Market Intelligence", "Logs & Review Notes"],
)


def get_json(path: str):
    try:
        response = requests.get(f"{BACKEND_URL}{path}", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"error": str(exc)}


def post_json(path: str, timeout: int = 10, payload: dict | None = None):
    try:
        response = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"error": str(exc)}


def start_workflow_thread(analysis_scope: str = "MCX"):
    def run_workflow():
        try:
            requests.post(
                f"{BACKEND_URL}/agents/band/run-quasar-workflow",
                params={"analysis_scope": analysis_scope},
                timeout=120,
            )
        except Exception:
            pass

    thread = threading.Thread(target=run_workflow, daemon=True)
    thread.start()
    return thread


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
    .agent-response-preview {
        font-size: 10px;
        line-height: 1.25;
        opacity: 0.72;
        margin-top: 0.25rem;
        max-width: 100%;
        overflow: hidden;
        text-overflow: ellipsis;
        display: -webkit-box;
        -webkit-line-clamp: 1;
        -webkit-box-orient: vertical;
    }
    .agent-band-badge {
        border: 1px solid rgba(46, 160, 67, 0.45);
        border-radius: 999px;
        padding: 0.05rem 0.32rem;
        font-size: 10px;
        margin-top: 0.2rem;
        opacity: 0.9;
    }
    .workflow-section-title {
        font-size: 13px;
        font-weight: 700;
        margin: 0.75rem 0 0.35rem 0;
    }
    .decision-card {
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.03);
        padding: 0.55rem 0.65rem;
        margin-top: 0.55rem;
        font-size: 11px;
        line-height: 1.4;
    }
    .decision-title {
        font-size: 13px;
        font-weight: 700;
        margin-bottom: 0.3rem;
    }
    .decision-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.28rem 0.55rem;
        margin-bottom: 0.35rem;
    }
    .decision-label {
        opacity: 0.75;
        font-weight: 700;
    }
    .decision-list {
        margin: 0.15rem 0 0.35rem 0;
        padding-left: 1rem;
    }
    .scope-preview {
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.025);
        padding: 0.5rem 0.6rem;
        margin: 0.35rem 0 0.55rem 0;
        font-size: 11px;
        line-height: 1.35;
    }
    .scope-preview-title {
        font-weight: 700;
        margin-bottom: 0.25rem;
    }
    .scope-preview-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.25rem 0.55rem;
    }
    .response-scroll {
        max-height: 220px;
        overflow-y: auto;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.02);
        padding: 0.45rem 0.55rem;
        font-size: 11px;
        line-height: 1.38;
    }
    .response-block-title {
        font-weight: 700;
        margin-top: 0.35rem;
    }
    .response-block-title:first-child {
        margin-top: 0;
    }
    .delivery-section {
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.025);
        padding: 0.42rem 0.55rem;
        margin-bottom: 0.35rem;
        font-size: 11px;
        line-height: 1.35;
    }
    .delivery-title {
        font-weight: 700;
        margin-bottom: 0.15rem;
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


def render_live_feed_controls():
    status = get_json("/market/ingestion/status")
    feed = status.get("twelvedata", {}) if "error" not in status else {}
    mcx_feed = status.get("zerodha", {}) if "error" not in status else {}
    latest = get_json("/market/latest")
    forex = latest.get("forex", {}) if "error" not in latest else {}
    mcx = latest.get("mcx", {}) if "error" not in latest else {}
    forex_health = get_candle_health("FOREX", "XAUUSD")
    mcx_health = get_candle_health("MCX", "NATURALGAS")

    if "error" in status:
        feed = {"last_error": status["error"], "market_closed": True}

    forex_running = feed_worker_alive(feed)
    mcx_running = feed_worker_alive(mcx_feed)
    forex_error = feed_provider_error(feed)
    mcx_error_statuses = {"failed", "token_error", "missing_credentials", "no_data"}
    mcx_provider_error = mcx_feed.get("last_status") in mcx_error_statuses

    render_feed_card(
        title="Forex Live Feed",
        source="TwelveData",
        instrument="XAUUSD",
        status_label=feed_status_label(
            configured=bool(feed),
            running=forex_running,
            market_closed=bool(feed.get("market_closed")),
            provider_error=forex_error,
        ),
        feed_state=feed,
        exchange_candle=forex.get("exchange_candle_time") or feed.get("exchange_candle_time") or forex.get("timestamp") or "—",
        fetched_at=forex.get("fetched_at") or feed.get("fetched_at") or "—",
        last_price=feed.get("last_price") or forex.get("candle", {}).get("close"),
        health=forex_health,
        market_type="FOREX",
        instrument_code="XAUUSD",
    )

    source = mcx.get("source", "MOCK_INGEST")
    configured = source == "ZERODHA" or bool(mcx_feed)
    mcx_market_closed = bool(mcx_feed.get("market_closed")) or "Closed" in market_session_text("MCX", mcx.get("timestamp", ""))
    render_feed_card(
        title="MCX Live Feed",
        source="Zerodha" if configured else "Mock",
        instrument="NATURALGAS",
        status_label=feed_status_label(
            configured=configured,
            running=mcx_running,
            market_closed=mcx_market_closed,
            provider_error=mcx_provider_error,
        ),
        feed_state=mcx_feed,
        exchange_candle=mcx.get("exchange_candle_time") or mcx_feed.get("exchange_candle_time") or mcx.get("timestamp") or "—",
        fetched_at=mcx.get("fetched_at") or mcx_feed.get("fetched_at") or "—",
        last_price=mcx_feed.get("last_price") or mcx.get("candle", {}).get("close"),
        health=mcx_health,
        market_type="MCX",
        instrument_code="NATURALGAS",
    )

    with st.sidebar.expander("Advanced Feed Controls", expanded=False):
        st.caption("Forex")
        forex_start_cols = st.columns(2)
        with forex_start_cols[0]:
            if st.button(
                "🟢 Start Live Ingestion",
                key="start_forex_live_ingestion",
                use_container_width=True,
                disabled=forex_running,
            ):
                post_json("/market/ingestion/start")
                st.rerun()
        with forex_start_cols[1]:
            if st.button(
                "🔴 Pause Live Ingestion",
                key="pause_forex_live_ingestion",
                use_container_width=True,
                disabled=not forex_running,
            ):
                post_json("/market/ingestion/stop")
                st.rerun()
        if forex_running:
            st.caption("Current state: 🟢 Live ingestion worker is running.")
        else:
            st.caption("Current state: 🔴 Live ingestion worker is stopped.")
        if st.button(
            "Fill Missing Candles",
            key="backfill_forex_candles",
            use_container_width=True,
        ):
            st.session_state["forex_backfill_result"] = post_json(
                "/market/ingest/twelvedata/backfill?days=30&chunk_days=3&dry_run=false",
                timeout=300,
            )
            st.rerun()
        st.caption("Forex")
        st.caption(f"Auto ingest enabled/running: {feed.get('enabled', False)} / {feed.get('running', False)}")
        st.caption(f"Worker alive: {feed.get('worker_alive', False)}")
        st.caption(f"Last success: {feed.get('last_success_at') or '—'}")
        st.caption(f"Next run: {feed.get('next_run_at') or '—'}")
        st.caption(f"Failures: {feed.get('failure_count', 0)}")
        st.caption(f"Duplicate skips: {feed.get('duplicate_skipped_count', 0)}")
        st.caption(f"Provider raw candle time: {feed.get('provider_raw_datetime') or '—'}")
        st.caption(
            "Timestamp corrected: "
            f"{feed.get('timestamp_corrected', False)}"
        )
        st.caption(
            "Correction reason: "
            f"{feed.get('timestamp_correction_reason') or 'None'}"
        )
        st.caption(f"Expected candles: {forex_health.get('expected_candles', 0):,}")
        st.caption(f"Coverage percent: {forex_health.get('coverage_percent', 0)}%")
        st.caption(f"Provider error: {feed.get('last_error') or 'None'}")
        if st.session_state.get("forex_backfill_result"):
            result = st.session_state["forex_backfill_result"]
            st.caption(f"Last backfill status: {result.get('status', result.get('error', 'unknown'))}")

        st.caption("MCX")
        mcx_start_cols = st.columns(2)
        with mcx_start_cols[0]:
            if st.button(
                "🟢 Start Live Ingestion",
                key="start_mcx_live_ingestion",
                use_container_width=True,
                disabled=mcx_running,
            ):
                post_json("/market/mcx-ingestion/start")
                st.rerun()
        with mcx_start_cols[1]:
            if st.button(
                "🔴 Pause Live Ingestion",
                key="pause_mcx_live_ingestion",
                use_container_width=True,
                disabled=not mcx_running,
            ):
                post_json("/market/mcx-ingestion/stop")
                st.rerun()
        if mcx_running:
            st.caption("Current state: 🟢 Live ingestion worker is running.")
        else:
            st.caption("Current state: 🔴 Live ingestion worker is stopped.")
        if st.button(
            "Fill Missing Candles",
            key="backfill_mcx_candles",
            use_container_width=True,
        ):
            st.session_state["mcx_backfill_result"] = post_json(
                "/market/ingest/zerodha/backfill?days=60&chunk_days=5&dry_run=false",
                timeout=600,
            )
            st.rerun()
        st.caption("MCX")
        st.caption(f"Auto ingest enabled/running: {mcx_feed.get('enabled', False)} / {mcx_feed.get('running', False)}")
        st.caption(f"Worker alive: {mcx_feed.get('worker_alive', False)}")
        st.caption(f"Last success: {mcx_feed.get('last_success_at') or '—'}")
        st.caption(f"Next run: {mcx_feed.get('next_run_at') or '—'}")
        st.caption(f"Failures: {mcx_feed.get('failure_count', 0)}")
        st.caption(f"Credential errors: {mcx_feed.get('credential_error_count', 0)}")
        st.caption(f"No data: {mcx_feed.get('no_data_count', 0)}")
        st.caption(f"Duplicate skips: {mcx_feed.get('duplicate_skipped_count', 0)}")
        st.caption(f"Expected candles: {mcx_health.get('expected_candles', 0):,}")
        st.caption(f"Coverage percent: {mcx_health.get('coverage_percent', 0)}%")
        st.caption(f"Provider error: {mcx_feed.get('last_error') or 'None'}")
        if st.session_state.get("mcx_backfill_result"):
            result = st.session_state["mcx_backfill_result"]
            st.caption(f"Last backfill status: {result.get('status', result.get('error', 'unknown'))}")


def get_candle_health(market_type, instrument):
    return get_json(
        f"/market/candle-health?market_type={market_type}&instrument={instrument}&timeframe=1m"
    )


def feed_worker_alive(feed):
    return bool(feed.get("worker_alive", feed.get("task_alive", False)))


def feed_provider_error(feed):
    return bool(feed.get("last_error")) and feed.get("last_status") in {
        "failed",
        "token_error",
        "missing_credentials",
        "no_data",
    }


def feed_worker_label(feed):
    if feed_provider_error(feed):
        return "🟡 Error"
    return "🟢 Running" if feed_worker_alive(feed) else "🔴 Stopped"


def feed_status_label(configured, running, market_closed, provider_error):
    if provider_error:
        return "Error · Provider Failure"
    if not configured:
        return "Stopped · Not Configured"
    if running:
        return "Running · Market Closed" if market_closed else "Running · Market Open"
    if market_closed:
        return "Stopped · Market Closed"
    return "Stopped · Market Open"


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


def render_feed_card(
    title,
    source,
    instrument,
    status_label,
    feed_state,
    exchange_candle,
    fetched_at,
    last_price,
    health,
    market_type,
    instrument_code,
):
    st.sidebar.markdown(f"**{title}**")
    configured = "Not Configured" not in status_label
    st.sidebar.caption(f"Source: {source}")
    st.sidebar.caption(f"Instrument: {instrument}")
    st.sidebar.caption(f"Status: {status_label}")
    st.sidebar.caption(f"Worker Status: {feed_worker_label(feed_state)}")
    st.sidebar.caption(f"Worker: {'Alive' if feed_worker_alive(feed_state) else 'Stopped'}")
    last_tick = feed_state.get("last_tick") or feed_state.get("last_run_at") or "—"
    st.sidebar.caption(f"Last Tick: {format_short_timestamp(last_tick, 'IST') if last_tick and last_tick != '—' else '—'}")
    st.sidebar.caption(f"Latest Candle: {format_timestamp(exchange_candle, 'IST') if exchange_candle and exchange_candle != '—' else '—'}")
    if last_price is None:
        price_text = "—"
    else:
        price_text = format_price(last_price, market_type, instrument_code)
    st.sidebar.caption(f"Last Price: {price_text}")
    freshness = true_freshness_label(exchange_candle, 'IST') if exchange_candle and exchange_candle != '—' else '—'
    if "Market Closed" in status_label and freshness != "—":
        freshness = f"Market closed · {freshness}"
    st.sidebar.caption(f"Freshness: {freshness}")
    st.sidebar.caption(f"Candle History Available: {int(health.get('total_candles') or 0):,} candles")
    st.sidebar.caption(f"Coverage: {coverage_label(health)}")
    st.sidebar.caption(f"Largest Gap: {int(health.get('largest_gap_minutes') or 0)}m")
    st.sidebar.caption(f"Analysis Readiness: {analysis_readiness(health, configured=configured)}")
    if st.sidebar.button("Check Data Quality", key=f"sanity_{market_type}_{instrument_code}", use_container_width=True):
        st.session_state[f"sanity_{market_type}_{instrument_code}"] = post_json(
            "/market/sanity-check",
            payload={
                "market_type": market_type,
                "instrument": instrument_code,
                "timeframe": "1m",
            },
        )
        st.rerun()
    sanity = st.session_state.get(f"sanity_{market_type}_{instrument_code}")
    if sanity:
        st.sidebar.caption(
            f"Sanity: Coverage {sanity.get('coverage', '—')} · "
            f"Largest Gap {sanity.get('largest_gap_minutes', '—')}m"
        )
        st.sidebar.caption(sanity.get("recommendation", ""))


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


def clean_agent_output(text: str) -> str:
    prefixes = [
        "Requirement Agent response:",
        "Market Intelligence Agent response:",
        "Architecture Agent response:",
        "System Readiness Agent response:",
        "Risk Governance Agent response:",
        "Delivery Planning Agent response:",
        "Final Review Agent response:",
    ]
    cleaned = str(text or "").strip()
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :].strip()
    return cleaned


def short_time(timestamp: str) -> str:
    if not timestamp:
        return "—"
    try:
        return datetime.fromisoformat(timestamp).strftime("%H:%M:%S")
    except ValueError:
        return timestamp[:8] or "—"


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


def parse_prompt_context(prompt: str) -> dict[str, object]:
    context = {
        "scope": extract_line_value(prompt, "Scope") or extract_line_value(prompt, "Selected scope"),
        "timeframe": extract_line_value(prompt, "Timeframe") or "1m",
        "candle": extract_line_value(prompt, "Candle"),
        "bias": extract_line_value(prompt, "Dominant Bias") or "Neutral",
        "session": extract_line_value(prompt, "Session"),
        "data_age": extract_line_value(prompt, "Data Age"),
        "source": extract_line_value(prompt, "Source"),
        "labels": [],
    }
    labels = extract_section_lines(
        prompt,
        "Top Labels",
        ["Dominant Bias", "Session", "Data Age", "Source", "Safety"],
    )
    context["labels"] = labels[:3]
    return context


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


def final_decision_data(workflow_details: dict, selected_scope: str) -> dict[str, object]:
    summary = workflow_details.get("final_summary", "")
    steps = workflow_details.get("steps", [])
    final_step = next(
        (step for step in steps if step.get("agent") == "Final Review Agent"),
        {},
    )
    prompt_context = parse_prompt_context(final_step.get("prompt_sent", ""))
    scope = (
        prompt_context.get("scope")
        or workflow_details.get("analysis_scope")
        or selected_scope
    )
    decision_state = extract_line_value(summary, "Decision State") or (
        "Waiting" if workflow_details.get("status") == "waiting" else "WATCH"
    )
    evidence = extract_section_lines(
        summary,
        "Evidence",
        ["Confidence", "Next Validation", "Specialist Notes", "Safety"],
    )
    if not evidence:
        evidence = list(prompt_context.get("labels", []))
    next_validation = extract_line_value(summary, "Next Validation")
    if not next_validation:
        next_lines = extract_section_lines(summary, "Next Validation", ["Specialist Notes", "Safety"])
        next_validation = next_lines[0] if next_lines else "Waiting for Band analysis."
    return {
        "scope": display_scope_label(str(scope), selected_scope),
        "decision_state": decision_state,
        "confidence": confidence_label(summary),
        "evidence": evidence[:3],
        "next_validation": next_validation,
        "safety": "Advisory-only. No orders. No buy/sell signals.",
    }


def normalize_label_text(label: str) -> str:
    return str(label or "UNKNOWN").replace("_", " ").title()


def label_direction(label: dict) -> str:
    direction = str(label.get("direction") or "").upper()
    if direction:
        return direction
    label_name = str(label.get("label") or "").upper()
    if "BULLISH" in label_name:
        return "BULLISH"
    if "BEARISH" in label_name:
        return "BEARISH"
    return "NEUTRAL"


def dominant_bias_from_labels(labels: list[dict]) -> str:
    bullish = sum(float(label.get("confidence") or 0) for label in labels if label_direction(label) == "BULLISH")
    bearish = sum(float(label.get("confidence") or 0) for label in labels if label_direction(label) == "BEARISH")
    if bullish > bearish:
        return "Mixed Bullish" if bearish else "Bullish"
    if bearish > bullish:
        return "Mixed Bearish" if bullish else "Bearish"
    if bullish or bearish:
        return "Conflicted"
    return "Neutral"


def selected_market_params(analysis_scope: str) -> tuple[str, str, str]:
    if analysis_scope == "FOREX":
        return "FOREX", "XAUUSD", "Forex XAUUSD"
    return "MCX", "NATURALGAS", "MCX NATURALGAS"


def get_selected_market_preview(analysis_scope: str, timezone_name: str = "UTC") -> dict[str, str]:
    market_type, instrument, scope_label = selected_market_params(analysis_scope)
    candles = get_json(
        f"/market/candles?market_type={market_type}&instrument={instrument}&timeframe=1m&limit=1"
    )
    labels_response = get_json(
        f"/smc/labels?market_type={market_type}&instrument={instrument}&timeframe=1m&limit=20"
    )
    labels = labels_response.get("labels", []) if "error" not in labels_response else []
    top_label = labels[0] if labels else {}
    top_signal = "Waiting for labels"
    if top_label:
        confidence = int(round(float(top_label.get("confidence") or 0) * 100))
        top_signal = f"{normalize_label_text(top_label.get('label'))} {confidence}%"

    candle_rows = candles.get("candles", []) if "error" not in candles else []
    latest = candle_rows[0] if candle_rows else {}
    timestamp = latest.get("timestamp", "")
    session = market_session_text(market_type, timestamp) if timestamp else "Waiting"
    data_age = format_freshness(timestamp, timezone_name) if timestamp else "Waiting"
    return {
        "scope": scope_label,
        "dominant_bias": dominant_bias_from_labels(labels),
        "top_signal": top_signal,
        "session": session,
        "data_age": data_age,
        "safety": "Advisory-only",
    }


def render_selected_market_preview(preview: dict[str, str]):
    st.markdown(
        (
            '<div class="scope-preview">'
            '<div class="scope-preview-title">Selected Market Preview</div>'
            '<div class="scope-preview-grid">'
            f'<div><span class="decision-label">Selected Scope:</span> {html.escape(preview.get("scope", ""))}</div>'
            f'<div><span class="decision-label">Dominant Bias:</span> {html.escape(preview.get("dominant_bias", ""))}</div>'
            f'<div><span class="decision-label">Top Signal:</span> {html.escape(preview.get("top_signal", ""))}</div>'
            f'<div><span class="decision-label">Session:</span> {html.escape(preview.get("session", ""))}</div>'
            f'<div><span class="decision-label">Data Age:</span> {html.escape(preview.get("data_age", ""))}</div>'
            f'<div><span class="decision-label">Safety Mode:</span> {html.escape(preview.get("safety", ""))}</div>'
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_final_decision_card(decision: dict[str, object]):
    evidence_items = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in decision.get("evidence", [])
    )
    if not evidence_items:
        evidence_items = "<li>Waiting for Band analysis.</li>"
    st.markdown(
        (
            '<div class="decision-card">'
            '<div class="decision-title">Final Specialist Decision</div>'
            '<div class="decision-grid">'
            f'<div><span class="decision-label">Scope:</span> {html.escape(str(decision.get("scope", "")))}</div>'
            f'<div><span class="decision-label">Decision State:</span> {html.escape(str(decision.get("decision_state", "")))}</div>'
            f'<div><span class="decision-label">Confidence:</span> {html.escape(str(decision.get("confidence", "")))}</div>'
            f'<div><span class="decision-label">Safety Mode:</span> Advisory-only</div>'
            "</div>"
            '<div class="decision-label">Key Evidence</div>'
            f'<ul class="decision-list">{evidence_items}</ul>'
            '<div class="decision-label">Next Validation</div>'
            f'<div>{html.escape(str(decision.get("next_validation", "")))}</div>'
            '<div class="decision-label" style="margin-top:0.35rem;">Safety</div>'
            f'<div>{html.escape(str(decision.get("safety", "")))}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_formatted_agent_response(step: dict, selected_scope: str):
    response_text = clean_agent_output(
        step.get("response_text") or step.get("summary") or "Waiting for Band analysis."
    )
    prompt_context = parse_prompt_context(step.get("prompt_sent", ""))
    labels = list(prompt_context.get("labels", []))
    decision_state = (
        extract_line_value(response_text, "Decision State")
        or extract_line_value(response_text, "State")
        or str(prompt_context.get("bias") or step.get("status", "waiting")).title()
    )
    evidence = labels[:3] or extract_section_lines(
        response_text,
        "Evidence",
        ["Next Validation", "Next Step", "Safety", "Specialist Notes"],
    )
    if not evidence:
        evidence = [response_text[:180]]
    next_step = (
        extract_line_value(response_text, "Next Validation")
        or extract_line_value(response_text, "Next Step")
        or "Wait for next candle close and validate higher timeframe context."
    )
    agent = step.get("agent", "")
    if agent == "Requirement Agent":
        decision_state = "Scope Confirmed"
        next_step = "Continue specialist review for the selected market only."
    elif agent == "Architecture Agent":
        decision_state = "Readiness Review"
        next_step = "Check freshness, session state, feed source, and label availability."
        evidence = [
            f"Data age: {prompt_context.get('data_age') or 'Unknown'}",
            f"Session: {prompt_context.get('session') or 'Unknown'}",
            f"Source: {prompt_context.get('source') or 'Unknown'}",
        ]
    elif agent == "Risk Governance Agent":
        decision_state = "Guardrails Active"
        next_step = "Require confirmation and avoid stale or conflicted structure."
    elif agent == "Delivery Planning Agent":
        decision_state = "Next-Step Plan"
    elif agent == "Final Review Agent":
        decision_state = extract_line_value(response_text, "Decision State") or "WATCH"

    duration = step.get("duration_seconds")
    completed_at = short_time(step.get("completed_at", ""))
    timing = f"{completed_at} • {duration}s" if step.get("completed_at") and duration is not None else ""
    evidence_items = "".join(f"<li>{html.escape(str(item))}</li>" for item in evidence[:3])
    timing_block = (
        '<div class="response-block-title">Timing</div>'
        f'<div>{html.escape(timing)}</div>'
        if timing
        else ""
    )
    st.markdown(
        (
            '<div class="response-scroll">'
            '<div class="response-block-title">State</div>'
            f'<div>{html.escape(str(decision_state))}</div>'
            '<div class="response-block-title">Evidence</div>'
            f'<ul class="decision-list">{evidence_items}</ul>'
            '<div class="response-block-title">Next Step</div>'
            f'<div>{html.escape(str(next_step))}</div>'
            f"{timing_block}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_agent_monitor():
    workflow = get_json("/agents/workflow-status")
    workflow_details = get_json("/agents/workflow/details")
    band_status = get_json("/agents/band/status")
    band_participants = get_json("/agents/band/participants")

    with st.container(border=True):
        st.markdown(
            '<div class="market-card-title">Agent Swarm Monitor</div>',
            unsafe_allow_html=True,
        )

        if "error" in workflow:
            st.error(workflow["error"])
            return
        if "error" in workflow_details:
            workflow_details = workflow

        detail_steps = workflow_details.get("steps") or workflow["steps"]
        completed_agents = sum(1 for step in detail_steps if step["status"] == "completed")
        current_state = workflow_details.get("status") or workflow.get("current_state", "waiting")
        workflow_thread = st.session_state.get("quasar_workflow_thread")
        thread_alive = bool(workflow_thread and workflow_thread.is_alive())
        if current_state in {"completed", "failed"} or (
            current_state == "waiting" and not thread_alive
        ):
            st.session_state["quasar_workflow_running"] = False
        if band_status.get("status") == "connected":
            band_label = "🟢 Connected"
            band_compact = "Connected"
        elif band_status.get("status") == "missing_credentials":
            band_label = "🟡 Config Missing"
            band_compact = "Config Missing"
        else:
            band_label = "🔴 Disconnected"
            band_compact = "Disconnected"

        analysis_scope_label = st.radio(
            "Analysis Scope",
            ["MCX NATURALGAS", "Forex XAUUSD"],
            horizontal=True,
            key="analysis_scope",
        )
        analysis_scope = "FOREX" if analysis_scope_label == "Forex XAUUSD" else "MCX"
        selected_scope = display_scope_label(analysis_scope)
        selected_timezone = st.session_state.get("global_timezone", "UTC")
        selected_preview = get_selected_market_preview(analysis_scope, selected_timezone)
        render_selected_market_preview(selected_preview)

        if st.button(
            "Get Specialist Analysis",
            key="run_quasar_band_workflow",
            use_container_width=True,
            type="primary",
            disabled=bool(st.session_state.get("quasar_workflow_running")),
        ):
            post_json("/agents/workflow/reset")
            st.session_state["quasar_band_workflow"] = {}
            st.session_state["quasar_workflow_running"] = True
            st.session_state["quasar_workflow_thread"] = start_workflow_thread(
                analysis_scope
            )
            time.sleep(0.3)
            st.rerun()

        workflow_scope = str(workflow_details.get("analysis_scope") or "MCX").upper()
        decision = final_decision_data(workflow_details, selected_scope)
        workflow_matches_selection = workflow_scope == analysis_scope
        if str(current_state).lower() == "waiting":
            decision["decision_state"] = "Waiting"
            decision["confidence"] = "Waiting"

        summary_cards = [
            ("Selected Market", selected_preview.get("scope", selected_scope)),
            (
                "Decision State",
                str(decision.get("decision_state", "Waiting"))
                if workflow_matches_selection
                else "Waiting",
            ),
            (
                "Confidence",
                str(decision.get("confidence", "Waiting"))
                if workflow_matches_selection
                else "Waiting",
            ),
            ("Band Status", band_compact),
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

        st.progress((workflow_details.get("progress", workflow["progress"]) or 0) / 100)
        st.caption(
            f"Run State: {str(current_state).title()} | "
            f"Progress: {workflow_details.get('progress', workflow['progress'])}% | "
            f"Completed Agents: {completed_agents}/{len(detail_steps)} | "
            f"Band Status: {band_label}"
        )

        if str(current_state).lower() == "completed" and workflow_matches_selection:
            render_final_decision_card(decision)

        display_names = {
            "Requirement Agent": "Requirement",
            "Market Intelligence Agent": "Market Intelligence",
            "Architecture Agent": "System Readiness",
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
        registry_agents = (
            band_participants.get("registry", {}).get("agents", [])
            if "error" not in band_participants
            else []
        )
        registry_by_name = {
            agent.get("agent_name"): agent for agent in registry_agents
        }
        agent_cols = st.columns(6)
        for col, step in zip(agent_cols, detail_steps):
            with col:
                status_class = step["status"] if step["status"] in status_labels else "waiting"
                registry_entry = registry_by_name.get(step["agent"], {})
                band_badge = "Band ✓" if registry_entry.get("connected") else "Internal"
                st.markdown(
                    (
                        f'<div class="agent-card {status_class}">'
                        f'<div class="agent-name">{html.escape(display_names.get(step["agent"], step["agent"]))}</div>'
                        f'<div class="agent-status">{html.escape(status_labels.get(step["status"], step["status"].title()))}</div>'
                        f'<div class="agent-band-badge">{html.escape(band_badge)}</div>'
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
                with st.expander("View Response", expanded=False):
                    render_formatted_agent_response(step, selected_scope)

        last_quasar_workflow = st.session_state.get("quasar_band_workflow", {})
        if last_quasar_workflow:
            if last_quasar_workflow.get("success"):
                st.success("Quasar Band workflow completed.")
            elif last_quasar_workflow.get("status") == "no_messages":
                st.info("No pending Band workflow message.")
            else:
                st.warning(
                    last_quasar_workflow.get("error")
                    or last_quasar_workflow.get("message")
                    or "Quasar Band workflow did not complete."
                )

        failed_steps = [step for step in detail_steps if step.get("status") == "failed"]
        has_failure = bool(failed_steps) or str(current_state).lower() == "failed"
        if has_failure:
            diagnostics = workflow_details.get("delivery_pack", {}).get("diagnostics", {})
            failed_agent = failed_steps[0] if failed_steps else {}
            with st.expander("Advanced Diagnostics", expanded=False):
                st.write(f"Workflow ID: {workflow_details.get('workflow_id', '—')}")
                st.write(f"Chat ID: {workflow_details.get('chat_id') or diagnostics.get('band_chat_id') or '—'}")
                st.write(f"Message ID: {workflow_details.get('message_id') or diagnostics.get('source_message_id') or '—'}")
                st.write(f"Failed Agent: {failed_agent.get('agent', '—')}")
                st.write(
                    "Error Reason: "
                    f"{failed_agent.get('summary') or last_quasar_workflow.get('error') or 'Unknown'}"
                )
                st.write(f"Scanned Message Count: {failed_agent.get('scanned_message_count', '—')}")

        if (
            st.session_state.get("quasar_workflow_running")
            or current_state == "running"
            or thread_alive
        ):
            time.sleep(1.5)
            st.rerun()


if page == "Live Market Intelligence":
    render_live_feed_controls()
    render_status_strip()
    selected_timezone = st.sidebar.radio(
        "Timezone",
        list(TIMEZONE_OPTIONS.keys()),
        horizontal=True,
        key="global_timezone",
        index=list(TIMEZONE_OPTIONS.keys()).index("IST"),
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

    st.subheader("Enterprise Review Notes")
    st.markdown(
        """
        ### Requirement Summary
        Build a regulated financial AI delivery platform with live MCX and Forex intelligence.

        ### System Readiness Summary
        FastAPI, Streamlit, TimescaleDB, Docker, Band agents, and AWS deployment.

        ### Governance Summary
        No trade execution. No buy/sell recommendations. SMC labels are used only for market-structure intelligence.

        ### Delivery Roadmap
        Foundation → Live Data → SMC Labels → Band Agents → Logs → AWS Deployment.
        """
    )
