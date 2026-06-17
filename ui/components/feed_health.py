import html

import streamlit as st

from api_client import sanity_check
from utils.formatting import (
    analysis_readiness,
    coverage_label,
    format_price,
    format_short_timestamp,
    format_timestamp,
    true_freshness_label,
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


def render_feed_control_state(running):
    state_class = "running" if running else "stopped"
    state_text = (
        "🟢 Live ingestion running"
        if running
        else "🔴 Live ingestion stopped"
    )
    st.markdown(
        (
            f'<div class="feed-state-card {state_class}">'
            f"Current State: {html.escape(state_text)}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_feed_diagnostics(title, feed, health):
    st.caption(
        f"Auto ingest enabled/running: "
        f"{feed.get('enabled', False)} / {feed.get('running', False)}"
    )
    st.caption(f"Worker alive: {feed.get('worker_alive', False)}")
    st.caption(f"Last success: {feed.get('last_success_at') or '—'}")
    st.caption(f"Next run: {feed.get('next_run_at') or '—'}")
    st.caption(f"Failures: {feed.get('failure_count', 0)}")
    if title == "MCX":
        st.caption(f"Credential errors: {feed.get('credential_error_count', 0)}")
        st.caption(f"No data: {feed.get('no_data_count', 0)}")
    st.caption(f"Duplicate skips: {feed.get('duplicate_skipped_count', 0)}")
    st.caption(f"Expected candles: {health.get('expected_candles', 0):,}")
    st.caption(f"Coverage percent: {health.get('coverage_percent', 0)}%")
    if title == "Forex":
        st.caption(f"Provider raw candle time: {feed.get('provider_raw_datetime') or '—'}")
        st.caption(f"Timestamp corrected: {feed.get('timestamp_corrected', False)}")
        st.caption(f"Correction reason: {feed.get('timestamp_correction_reason') or 'None'}")
    st.caption(f"Provider error: {feed.get('last_error') or 'None'}")


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


def normalize_quality_result(result, health):
    if not result:
        return {}
    if "error" in result:
        return {
            "status": "critical",
            "reason": result["error"],
            "coverage_label": "None",
            "available_candles": 0,
            "largest_unexpected_gap_minutes": 0,
            "analysis_readiness": "Not Ready",
            "recommendation": "Check backend connectivity and retry.",
        }
    return {
        "status": result.get("status", "warning"),
        "market_type": result.get("market_type", ""),
        "instrument": result.get("instrument", ""),
        "available_candles": result.get("available_candles", 0),
        "coverage_label": result.get("coverage_label") or result.get("coverage") or "None",
        "largest_unexpected_gap_minutes": result.get(
            "largest_unexpected_gap_minutes",
            result.get("largest_gap_minutes", health.get("largest_gap_minutes", 0)),
        ),
        "analysis_readiness": result.get(
            "analysis_readiness",
            analysis_readiness(health),
        ),
        "recommendation": result.get("recommendation", ""),
        "checked_at": result.get("checked_at", ""),
    }


def quality_result_key(market_type):
    return "forex_quality_result" if market_type == "FOREX" else "mcx_quality_result"


def render_quality_result(market_label, result, health, result_key):
    normalized = normalize_quality_result(result, health)
    if not normalized:
        return
    status = str(normalized.get("status", "warning")).lower()
    if status == "ok":
        title = f"✅ {market_label} Quality OK"
        card_class = "ok"
    elif status == "critical":
        title = f"❌ {market_label} Quality Failed"
        card_class = "critical"
    else:
        title = f"⚠ {market_label} Quality Warning"
        card_class = "warning"
    reason = normalized.get("reason")
    header_col, close_col = st.sidebar.columns([0.82, 0.18])
    with close_col:
        if st.button("×", key=f"close_{result_key}", use_container_width=True):
            st.session_state.pop(result_key, None)
            st.rerun()
    lines = [f"<strong>{html.escape(title)}</strong>"]
    if reason:
        lines.append(f"Reason: {html.escape(str(reason))}")
    lines.extend(
        [
            (
                "History: "
                f"{html.escape(str(normalized.get('coverage_label', '—')))} · "
                f"{int(normalized.get('available_candles') or 0):,} candles"
            ),
            (
                "Gap: "
                f"{int(normalized.get('largest_unexpected_gap_minutes') or 0)}m"
            ),
            f"Readiness: {html.escape(str(normalized.get('analysis_readiness', '—')))}",
            html.escape(str(normalized.get("recommendation", ""))),
        ]
    )
    with header_col:
        st.markdown(
            (
                f'<div class="quality-result-card {card_class}">'
                + "<br>".join(lines)
                + "</div>"
            ),
            unsafe_allow_html=True,
        )


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
    market_label = "Forex" if market_type == "FOREX" else "MCX"
    st.sidebar.caption(f"Status: {status_label}")
    st.sidebar.caption(f"Worker: {feed_worker_label(feed_state)}")
    last_tick = feed_state.get("last_tick") or feed_state.get("last_run_at") or "—"
    if last_price is None:
        price_text = "—"
    else:
        price_text = format_price(last_price, market_type, instrument_code)
    latest_time = (
        format_short_timestamp(exchange_candle, "IST")
        if exchange_candle and exchange_candle != "—"
        else "—"
    )
    st.sidebar.caption(f"Latest: {latest_time} · {price_text}")
    freshness = true_freshness_label(exchange_candle, 'IST') if exchange_candle and exchange_candle != '—' else '—'
    st.sidebar.caption(f"Freshness: {freshness}")
    st.sidebar.caption(
        f"History: {coverage_label(health)} · "
        f"{int(health.get('db_total_candles') or health.get('total_candles') or 0):,} candles"
    )
    st.sidebar.caption(f"Readiness: {analysis_readiness(health, configured=configured)}")
    with st.sidebar.expander(f"Advanced {market_label} Details", expanded=False):
        st.caption(f"Source: {source}")
        st.caption(f"Instrument: {instrument}")
        st.caption(
            f"Last Tick: {format_short_timestamp(last_tick, 'IST') if last_tick and last_tick != '—' else '—'}"
        )
        st.caption(
            "Latest Candle: "
            f"{format_timestamp(exchange_candle, 'IST') if exchange_candle and exchange_candle != '—' else '—'}"
        )
        st.caption(f"Coverage: {coverage_label(health)}")
        st.caption(
            f"Largest Unexpected Gap: {int(health.get('largest_gap_minutes') or 0)}m"
        )
        st.caption(f"Expected candles: {health.get('expected_candles', 0):,}")
        render_feed_diagnostics(market_label, feed_state, health)
    result_key = quality_result_key(market_type)
    if st.sidebar.button(
        f"Check {market_label} Data Quality",
        key=f"quality_button_{market_type}_{instrument_code}",
        use_container_width=True,
    ):
        st.session_state[result_key] = sanity_check(market_type, instrument_code, "1m")
        st.rerun()
    sanity = st.session_state.get(result_key)
    render_quality_result(market_label, sanity, health, result_key)
