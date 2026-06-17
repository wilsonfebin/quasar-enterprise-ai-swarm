import streamlit as st

from api_client import (
    backfill_forex,
    backfill_mcx,
    candle_health,
    feed_status,
    latest_market,
    pause_forex_ingestion,
    pause_mcx_ingestion,
    start_forex_ingestion,
    start_mcx_ingestion,
)
from components.feed_health import (
    feed_provider_error,
    feed_status_label,
    feed_worker_alive,
    render_feed_card,
    render_feed_control_state,
)
from utils.formatting import market_session_text


def render_status_strip():
    st.sidebar.markdown("**Safety Mode**")
    st.sidebar.caption("🛡 Advisory Only")
    st.sidebar.caption("🚫 No Orders")
    st.sidebar.caption("🚫 No Buy/Sell Signals")


def render_live_feed_controls():
    status = feed_status()
    feed = status.get("twelvedata", {}) if "error" not in status else {}
    mcx_feed = status.get("zerodha", {}) if "error" not in status else {}
    latest = latest_market()
    forex = latest.get("forex", {}) if "error" not in latest else {}
    mcx = latest.get("mcx", {}) if "error" not in latest else {}
    forex_health = candle_health("FOREX", "XAUUSD")
    mcx_health = candle_health("MCX", "NATURALGAS")

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
        render_feed_control_state(forex_running)
        forex_start_cols = st.columns(2)
        with forex_start_cols[0]:
            if st.button(
                "🟢 Start Live Ingestion",
                key="start_forex_live_ingestion",
                use_container_width=True,
            ):
                start_forex_ingestion()
                st.rerun()
        with forex_start_cols[1]:
            if st.button(
                "🔴 Pause Live Ingestion",
                key="pause_forex_live_ingestion",
                use_container_width=True,
            ):
                pause_forex_ingestion()
                st.rerun()
        if st.button(
            "Fill Missing Candles",
            key="backfill_forex_candles",
            use_container_width=True,
        ):
            st.session_state["forex_backfill_result"] = backfill_forex()
            st.rerun()
        if st.session_state.get("forex_backfill_result"):
            result = st.session_state["forex_backfill_result"]
            st.caption(f"Last backfill status: {result.get('status', result.get('error', 'unknown'))}")

        st.caption("MCX")
        render_feed_control_state(mcx_running)
        mcx_start_cols = st.columns(2)
        with mcx_start_cols[0]:
            if st.button(
                "🟢 Start Live Ingestion",
                key="start_mcx_live_ingestion",
                use_container_width=True,
            ):
                start_mcx_ingestion()
                st.rerun()
        with mcx_start_cols[1]:
            if st.button(
                "🔴 Pause Live Ingestion",
                key="pause_mcx_live_ingestion",
                use_container_width=True,
            ):
                pause_mcx_ingestion()
                st.rerun()
        if st.button(
            "Fill Missing Candles",
            key="backfill_mcx_candles",
            use_container_width=True,
        ):
            st.session_state["mcx_backfill_result"] = backfill_mcx()
            st.rerun()
        if st.session_state.get("mcx_backfill_result"):
            result = st.session_state["mcx_backfill_result"]
            st.caption(f"Last backfill status: {result.get('status', result.get('error', 'unknown'))}")
            backfill = result.get("backfill", {}) if isinstance(result, dict) else {}
            message = backfill.get("message") or result.get("message")
            action_hint = backfill.get("action_hint") or result.get("action_hint")
            if message:
                st.caption(message)
            if action_hint:
                st.caption(action_hint)

    render_status_strip()
