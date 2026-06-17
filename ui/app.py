import streamlit as st

from components.agent_swarm import render_agent_monitor
from components.logs import render_logs_page
from components.market_cards import render_market_card
from components.sidebar import render_live_feed_controls
from config import PAGE_OPTIONS, TIMEZONE_OPTIONS
from styles import apply_theme, load_styles
from utils.state import initialize_session_state


st.set_page_config(
    page_title="Quasar Enterprise AI Delivery Swarm",
    layout="wide",
)

initialize_session_state()
load_styles()

st.title("Quasar Enterprise AI Delivery Swarm")
st.caption("Live Market Intelligence + Band Agent Workflow Monitor")

page = st.sidebar.radio("Navigation", PAGE_OPTIONS)
selected_timezone = st.sidebar.radio(
    "Timezone",
    list(TIMEZONE_OPTIONS.keys()),
    horizontal=True,
    key="global_timezone",
    index=list(TIMEZONE_OPTIONS.keys()).index(
        st.session_state.get("global_timezone", "IST")
    )
    if st.session_state.get("global_timezone", "IST") in TIMEZONE_OPTIONS
    else list(TIMEZONE_OPTIONS.keys()).index("IST"),
)
selected_theme = st.sidebar.selectbox(
    "Theme",
    ["Default Dark", "Black"],
    key="ui_theme",
    index=1 if st.session_state.get("ui_theme") == "Black" else 0,
)
apply_theme(selected_theme)
previous_page = st.session_state.get("active_page")
page_changed = previous_page is not None and previous_page != page
st.session_state["active_page"] = page
if page_changed:
    st.session_state.pop("raw_log_source", None)

if page == "Live Market Intelligence":
    render_live_feed_controls()

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
    render_logs_page()
