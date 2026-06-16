import streamlit as st


def initialize_session_state():
    st.session_state.setdefault("quasar_workflow_running", False)
    st.session_state.setdefault("quasar_band_workflow", {})
