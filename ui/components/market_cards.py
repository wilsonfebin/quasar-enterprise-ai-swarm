import html

import streamlit as st

from api_client import market_candles, smc_labels
from config import TIMEFRAMES
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
        candles = market_candles(market_type, instrument, timeframe, limit=20)
        labels = smc_labels(market_type, instrument, timeframe, limit=20)

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
