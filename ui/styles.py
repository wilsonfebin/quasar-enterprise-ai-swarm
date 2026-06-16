import streamlit as st

CSS = r"""
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
    min-height: 250px;
    padding: 0.5rem 0.42rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
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
.agent-band-badge {
    border: 1px solid rgba(46, 160, 67, 0.45);
    border-radius: 999px;
    padding: 0.05rem 0.32rem;
    font-size: 10px;
    margin-top: 0.2rem;
    opacity: 0.9;
}
.agent-card-detail {
    width: 100%;
    margin-top: 0.35rem;
    text-align: left;
}
.agent-card-label {
    margin-top: 0.28rem;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0;
    text-transform: uppercase;
    opacity: 0.65;
}
.agent-card-value {
    font-size: 10px;
    line-height: 1.25;
    font-weight: 700;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.agent-card-text {
    font-size: 10px;
    line-height: 1.25;
    opacity: 0.88;
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
.executive-strip {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 0.35rem;
    margin: 0.35rem 0 0.5rem 0;
}
.executive-strip div {
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 7px;
    background: rgba(255, 255, 255, 0.035);
    padding: 0.35rem 0.4rem;
    min-width: 0;
}
.executive-strip span {
    display: block;
    font-size: 9px;
    font-weight: 700;
    opacity: 0.62;
}
.executive-strip strong {
    display: block;
    font-size: 11px;
    line-height: 1.2;
    margin-top: 0.12rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
.mtf-row {
    display: grid;
    grid-template-columns: 0.7fr 1.8fr 1.6fr 0.8fr;
    gap: 0.45rem;
    align-items: center;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 7px;
    background: rgba(255, 255, 255, 0.028);
    padding: 0.24rem 0.38rem;
    margin-bottom: 0.22rem;
    font-size: 11px;
}
.mtf-header {
    font-weight: 700;
    opacity: 0.82;
    background: rgba(255, 255, 255, 0.045);
}
.mtf-row.bullish, .chain-state.bullish, .validation-block.bullish {
    border-color: rgba(46, 160, 67, 0.55);
    box-shadow: inset 3px 0 0 rgba(46, 160, 67, 0.5);
}
.mtf-row.bearish, .chain-state.bearish, .validation-block.bearish {
    border-color: rgba(248, 81, 73, 0.55);
    box-shadow: inset 3px 0 0 rgba(248, 81, 73, 0.5);
}
.mtf-row.neutral, .chain-state.neutral, .validation-block.neutral {
    border-color: rgba(187, 128, 9, 0.55);
    box-shadow: inset 3px 0 0 rgba(187, 128, 9, 0.5);
}
.mtf-row.conflicted, .chain-state.conflicted {
    border-color: rgba(248, 81, 73, 0.55);
    box-shadow: inset 3px 0 0 rgba(187, 128, 9, 0.65);
}
.mtf-row.insufficient, .chain-state.insufficient {
    border-color: rgba(139, 148, 158, 0.45);
    box-shadow: inset 3px 0 0 rgba(139, 148, 158, 0.45);
}
.mtf-signal.bullish {
    color: #7ee787;
}
.mtf-signal.bearish {
    color: #ff7b72;
}
.mtf-signal.neutral {
    color: #d29922;
}
.structure-chain {
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.025);
    padding: 0.42rem;
    margin: 0.3rem 0 0.45rem 0;
}
.chain-node {
    display: flex;
    align-items: center;
    gap: 0.45rem;
}
.chain-tf {
    width: 2rem;
    font-weight: 700;
}
.chain-state {
    flex: 1;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 999px;
    padding: 0.16rem 0.45rem;
    background: rgba(255, 255, 255, 0.03);
}
.chain-arrow {
    margin-left: 0.65rem;
    opacity: 0.75;
    line-height: 1;
}
.validation-block {
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.025);
    padding: 0.34rem 0.48rem;
    margin: 0.28rem 0;
}
.validation-block ul {
    margin: 0.18rem 0 0 1rem;
    padding: 0;
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
.feed-state-card, .quality-result-card {
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.025);
    padding: 0.42rem 0.5rem;
    margin: 0.32rem 0 0.45rem 0;
    font-size: 11px;
    line-height: 1.35;
}
.feed-state-card.running {
    border-color: rgba(46, 160, 67, 0.55);
    box-shadow: inset 3px 0 0 rgba(46, 160, 67, 0.55);
}
.feed-state-card.stopped {
    border-color: rgba(248, 81, 73, 0.55);
    box-shadow: inset 3px 0 0 rgba(248, 81, 73, 0.55);
}
.quality-result-card.ok {
    border-color: rgba(46, 160, 67, 0.55);
    box-shadow: inset 3px 0 0 rgba(46, 160, 67, 0.55);
}
.quality-result-card.warning {
    border-color: rgba(187, 128, 9, 0.55);
    box-shadow: inset 3px 0 0 rgba(187, 128, 9, 0.55);
}
.quality-result-card.critical {
    border-color: rgba(248, 81, 73, 0.55);
    box-shadow: inset 3px 0 0 rgba(248, 81, 73, 0.55);
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
"""


def load_styles():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
