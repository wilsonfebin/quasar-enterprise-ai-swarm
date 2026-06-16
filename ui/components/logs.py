import html

import streamlit as st

from api_client import log_lines


def render_log_card(title, log_name):
    st.write(title)
    log_data = log_lines(log_name)
    lines = log_data.get("lines", [])[-18:]
    padded_lines = lines + [""] * max(0, 18 - len(lines))
    escaped_log = html.escape("\n".join(padded_lines))
    st.markdown(
        f'<div class="log-card">{escaped_log}</div>',
        unsafe_allow_html=True,
    )


def render_logs_page():
    st.subheader("System Logs")

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
