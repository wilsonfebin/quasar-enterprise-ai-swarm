import html
from datetime import datetime, timedelta, timezone

import plotly.graph_objects as go
import streamlit as st

from api_client import feed_status, market_candles, smc_labels
from config import TIMEFRAMES, TIMEZONE_OPTIONS
from utils.formatting import (
    format_confidence,
    format_freshness,
    format_price,
    format_short_timestamp,
    format_volume,
    market_session_text,
    readable_source,
    status_badge,
)

CHART_REFRESH_SECONDS = 30
CHART_CACHE_TTL_SECONDS = 15
LABEL_CACHE_TTL_SECONDS = 300
CHART_DEFAULT_VISIBLE_CANDLES = 100
CHART_MIN_VISIBLE_CANDLES = 20
CHART_ZOOM_STEP = 20


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
    direction_text = "Bullish Candle" if direction == "bullish" else "Bearish Candle"
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
                    f'<div class="candle-summary-cell {direction}">'
                    f'<div class="ohlc-label metric-label">{html.escape(label)}</div>'
                    f'<div class="ohlc-value metric-value">{html.escape(value)}</div>'
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


@st.cache_data(ttl=10, show_spinner=False)
def cached_feed_status():
    return feed_status()


def feed_state_for_market(market_type):
    status = cached_feed_status()
    if not isinstance(status, dict) or "error" in status:
        return {}
    key = "zerodha" if market_type == "MCX" else "twelvedata"
    feed = status.get(key)
    return feed if isinstance(feed, dict) else {}


def feed_worker_alive(feed):
    return bool(feed.get("worker_alive", feed.get("task_alive", False)))


def feed_provider_error(feed):
    return bool(feed.get("last_error")) and feed.get("last_status") in {
        "failed",
        "token_error",
        "missing_credentials",
        "no_data",
    }


def card_feed_status(candle_status, source, feed):
    if not feed:
        return status_badge(candle_status, source)
    if feed.get("last_status") == "rate_limited":
        return "🟡 Rate Limited"
    if feed_provider_error(feed):
        return "🟡 Feed Error"
    if feed_worker_alive(feed):
        return "🟢 Live Data"
    return "🔴 Worker Stopped"


def card_worker_badge(feed):
    if not feed:
        return "Worker Unknown"
    if feed.get("last_status") == "rate_limited":
        return "Worker Cooling Down"
    return "Worker Running" if feed_worker_alive(feed) else "Worker Stopped"


def card_session_text(market_type, timestamp, feed):
    if feed and market_type == "MCX":
        return "MCX Closed" if feed.get("market_closed") else "MCX Active"
    if feed and market_type == "FOREX" and feed.get("market_closed"):
        return "Forex Closed"
    return market_session_text(market_type, timestamp)


def timeframe_delta(timeframe):
    try:
        if str(timeframe).endswith("H"):
            return timedelta(hours=int(str(timeframe).removesuffix("H")))
        if str(timeframe).endswith("m"):
            return timedelta(minutes=int(str(timeframe).removesuffix("m")))
    except Exception:
        pass
    return timedelta(0)


def candle_formed_timestamp(value, timeframe):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (parsed + timeframe_delta(timeframe)).isoformat()
    except Exception:
        return value


def chart_datetime(value, timezone_name, timeframe):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed + timeframe_delta(timeframe)
        return parsed.astimezone(TIMEZONE_OPTIONS[timezone_name]).replace(tzinfo=None)
    except Exception:
        return value


def chart_date_label(chart_times, timezone_name):
    dates = [
        value.strftime("%Y-%m-%d")
        for value in chart_times
        if isinstance(value, datetime)
    ]
    if not dates:
        return timezone_name
    if dates[0] == dates[-1]:
        return f"{dates[0]} {timezone_name}"
    return f"{dates[0]} to {dates[-1]} {timezone_name}"


def chart_axis_labels(chart_times):
    labels = []
    previous_date = None
    for value in chart_times:
        if not isinstance(value, datetime):
            labels.append(str(value))
            previous_date = None
            continue

        current_date = value.date()
        if current_date != previous_date:
            labels.append(value.strftime("%d %b %H:%M"))
        else:
            labels.append(value.strftime("%H:%M"))
        previous_date = current_date
    return labels


def chart_tick_indices(chart_times, max_ticks=7):
    if len(chart_times) <= max_ticks:
        return list(range(len(chart_times)))
    step = max(1, len(chart_times) // max_ticks)
    ticks = list(range(0, len(chart_times), step))
    last_index = len(chart_times) - 1
    if last_index not in ticks:
        ticks.append(last_index)
    return ticks


def render_candlestick_chart(
    candle_rows,
    market_type,
    instrument,
    timeframe,
    timezone_name,
    visible_candles,
):
    if not candle_rows:
        st.info("No candle history available for this timeframe.")
        return

    visible_rows = candle_rows[:visible_candles]
    chart_rows = list(reversed(visible_rows))
    chart_times = [
        chart_datetime(row["timestamp"], timezone_name, timeframe)
        for row in chart_rows
    ]
    chart_x = list(range(len(chart_rows)))
    tick_values = chart_tick_indices(chart_times)
    all_labels = chart_axis_labels(chart_times)
    tick_labels = [all_labels[index] for index in tick_values]
    date_label = chart_date_label(chart_times, timezone_name)
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=chart_x,
                open=[row["open"] for row in chart_rows],
                high=[row["high"] for row in chart_rows],
                low=[row["low"] for row in chart_rows],
                close=[row["close"] for row in chart_rows],
                increasing_line_color="#2ea043",
                increasing_fillcolor="rgba(46, 160, 67, 0.55)",
                decreasing_line_color="#f85149",
                decreasing_fillcolor="rgba(248, 81, 73, 0.55)",
            )
        ]
    )
    fig.update_layout(
        title={
            "text": f"{market_type} {instrument} - {timeframe} | {date_label}",
            "font": {"size": 12},
            "x": 0.01,
            "xanchor": "left",
        },
        template="plotly_dark",
        height=320,
        margin={"l": 8, "r": 8, "t": 34, "b": 44},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.025)",
        showlegend=False,
        xaxis_rangeslider_visible=False,
    )
    fig.update_xaxes(
        showgrid=False,
        tickfont={"size": 10},
        title={
            "text": "Time",
            "font": {"size": 10},
            "standoff": 14,
        },
        type="category",
        tickmode="array",
        tickvals=tick_values,
        ticktext=tick_labels,
        tickangle=0,
        automargin=True,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="rgba(255,255,255,0.08)",
        tickfont={"size": 10},
        fixedrange=False,
    )
    st.plotly_chart(
        fig,
        width="stretch",
        config={"displayModeBar": False, "responsive": True},
    )


def chart_cache_key(market_type, instrument, timeframe):
    return f"{market_type.upper()}:{instrument.upper()}:{timeframe}"


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def cached_chart_candles(market_type, instrument, timeframe, limit=100):
    key = chart_cache_key(market_type, instrument, timeframe)
    candle_cache = st.session_state.setdefault("chart_candles_by_market_timeframe", {})
    refresh_times = st.session_state.setdefault("last_chart_refresh_at", {})
    last_timestamps = st.session_state.setdefault("last_candle_timestamp", {})
    force_key = f"force_chart_refresh_{key}"
    force_refresh = bool(st.session_state.pop(force_key, False))
    cached = candle_cache.get(key)
    now = datetime.now(timezone.utc)

    if cached and not force_refresh:
        try:
            cached_at = datetime.fromisoformat(cached["fetched_at"])
            if (now - cached_at).total_seconds() < CHART_CACHE_TTL_SECONDS:
                return cached["response"], cached.get("new_candle", False), cached["fetched_at"]
        except Exception:
            pass

    response = market_candles(
        market_type,
        instrument,
        timeframe,
        limit=limit,
        closed_only=True,
    )
    if "error" in response and cached:
        cached["response"]["refresh_warning"] = response["error"]
        return cached["response"], False, cached["fetched_at"]

    candle_rows = response.get("candles", []) if "error" not in response else []
    latest_timestamp = candle_rows[0].get("timestamp", "") if candle_rows else ""
    previous_timestamp = last_timestamps.get(key)
    new_candle = bool(previous_timestamp and latest_timestamp and latest_timestamp != previous_timestamp)
    fetched_at = utc_now_iso()

    if latest_timestamp:
        last_timestamps[key] = latest_timestamp
    refresh_times[key] = fetched_at
    candle_cache[key] = {
        "response": response,
        "fetched_at": fetched_at,
        "new_candle": new_candle,
    }
    return response, new_candle, fetched_at


def request_chart_refresh(market_type, instrument, timeframe):
    key = chart_cache_key(market_type, instrument, timeframe)
    st.session_state[f"force_chart_refresh_{key}"] = True


def chart_zoom_state_key(market_type, instrument, timeframe):
    return f"chart_visible_candles_{chart_cache_key(market_type, instrument, timeframe)}"


def chart_visible_candles(market_type, instrument, timeframe):
    state_key = chart_zoom_state_key(market_type, instrument, timeframe)
    current = int(st.session_state.get(state_key, CHART_DEFAULT_VISIBLE_CANDLES) or CHART_DEFAULT_VISIBLE_CANDLES)
    current = max(CHART_MIN_VISIBLE_CANDLES, min(CHART_DEFAULT_VISIBLE_CANDLES, current))
    st.session_state[state_key] = current
    return current


def zoom_chart(market_type, instrument, timeframe, direction):
    state_key = chart_zoom_state_key(market_type, instrument, timeframe)
    current = chart_visible_candles(market_type, instrument, timeframe)
    if direction == "in":
        next_value = max(CHART_MIN_VISIBLE_CANDLES, current - CHART_ZOOM_STEP)
    else:
        next_value = min(CHART_DEFAULT_VISIBLE_CANDLES, current + CHART_ZOOM_STEP)
    st.session_state[state_key] = next_value


def cached_smc_labels(market_type, instrument, timeframe, limit=20):
    key = chart_cache_key(market_type, instrument, timeframe)
    label_cache = st.session_state.setdefault("chart_labels_by_market_timeframe", {})
    cached = label_cache.get(key)
    now = datetime.now(timezone.utc)

    if cached:
        try:
            cached_at = datetime.fromisoformat(cached["fetched_at"])
            if (now - cached_at).total_seconds() < LABEL_CACHE_TTL_SECONDS:
                return cached["response"]
        except Exception:
            pass

    response = smc_labels(market_type, instrument, timeframe, limit=limit)
    if "error" in response and cached:
        cached["response"]["refresh_warning"] = response["error"]
        return cached["response"]

    label_cache[key] = {
        "response": response,
        "fetched_at": utc_now_iso(),
    }
    return response


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


@st.fragment(run_every=CHART_REFRESH_SECONDS)
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
        st.caption(
            "Chart timeframe controls visual context only. Specialist review uses multi-timeframe intelligence. Charts show closed candles only."
        )
        refresh_col, zoom_out_col, zoom_in_col, refresh_meta_col = st.columns([1.2, 0.35, 0.35, 3])
        with refresh_col:
            st.button(
                "Refresh chart",
                key=f"refresh_chart_{market_type.lower()}_{instrument.lower()}_{timeframe}",
                on_click=request_chart_refresh,
                args=(market_type, instrument, timeframe),
                use_container_width=True,
            )
        with zoom_out_col:
            st.button(
                "-",
                key=f"zoom_out_{market_type.lower()}_{instrument.lower()}_{timeframe}",
                on_click=zoom_chart,
                args=(market_type, instrument, timeframe, "out"),
                use_container_width=True,
            )
        with zoom_in_col:
            st.button(
                "+",
                key=f"zoom_in_{market_type.lower()}_{instrument.lower()}_{timeframe}",
                on_click=zoom_chart,
                args=(market_type, instrument, timeframe, "in"),
                use_container_width=True,
            )

        candles, new_candle, chart_updated_at = cached_chart_candles(
            market_type,
            instrument,
            timeframe,
            limit=100,
        )
        labels = cached_smc_labels(market_type, instrument, timeframe, limit=20)

        if "error" in candles:
            st.error(candles["error"])
            return

        candle_rows = candles.get("candles", [])
        if not candle_rows:
            st.info("No candle history available for this timeframe.")
            return

        latest = candle_rows[0]
        feed_state = feed_state_for_market(market_type)
        visible_candles = min(
            chart_visible_candles(market_type, instrument, timeframe),
            len(candle_rows),
        )
        latest_formed_timestamp = candle_formed_timestamp(latest["timestamp"], timeframe)
        updated_at = format_short_timestamp(latest_formed_timestamp, timezone_name)
        chart_updated_text = format_short_timestamp(chart_updated_at, timezone_name)
        data_age = format_freshness(latest["timestamp"], timezone_name)
        session_text = card_session_text(market_type, latest_formed_timestamp, feed_state)
        feed_status_text = card_feed_status(candles.get("status"), latest["source"], feed_state)
        worker_text = card_worker_badge(feed_state)
        with refresh_meta_col:
            st.caption(
                f"Auto-refresh: {CHART_REFRESH_SECONDS}s | "
                f"Last candle: {updated_at} | "
                f"Last chart update: {chart_updated_text}"
            )
            if new_candle:
                st.caption("New candle received")
        st.markdown(
            (
                '<div class="market-meta">'
                f'<div class="market-instrument">{html.escape(latest["instrument"])}</div>'
                '<div class="market-feed">'
                f'{html.escape(feed_status_text)}'
                f' &bull; Source: {html.escape(readable_source(latest["source"], timeframe))}'
                "</div>"
                '<div class="meta-badges">'
                f'<span class="meta-badge">Updated {html.escape(updated_at)}</span>'
                f'<span class="meta-badge">Data Age {html.escape(data_age)}</span>'
                f'<span class="meta-badge">{html.escape(worker_text)}</span>'
                f'<span class="meta-badge">{html.escape(session_text)}</span>'
                "</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        if candles.get("refresh_warning"):
            st.caption(f"Using cached candles. Latest refresh failed: {candles['refresh_warning']}")
        validation = candles.get("validation") if isinstance(candles, dict) else {}
        if isinstance(validation, dict) and (
            validation.get("duplicate_timestamp_count", 0)
            or validation.get("misaligned_timestamp_count", 0)
        ):
            st.caption(
                "Chart data validation warning: duplicate or misaligned candle timestamps were detected."
            )
        render_candlestick_chart(
            candle_rows,
            market_type,
            instrument,
            timeframe,
            timezone_name,
            visible_candles,
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
