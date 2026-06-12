import os
import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

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


if page == "Live Market Intelligence":
    data = get_json("/market/latest")

    if "error" in data:
        st.error(data["error"])
    else:
        mcx = data["mcx"]
        forex = data["forex"]

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("MCX Live Intelligence")
            st.caption(f"Source: {mcx['source']} | Status: {mcx['status']}")
            st.metric("Instrument", mcx["instrument"])
            st.write("Latest Candle")
            st.json(mcx["candle"])

            st.write("Latest SMC Labels")
            for label in mcx["smc_labels"]:
                st.success(
                    f"{label['label']} | {label['direction']} | confidence {label['confidence']}"
                )

            st.caption(f"Last updated: {mcx['timestamp']}")

        with col2:
            st.subheader("Forex Live Intelligence")
            st.caption(f"Source: {forex['source']} | Status: {forex['status']}")
            st.metric("Instrument", forex["instrument"])
            st.write("Latest Candle")
            st.json(forex["candle"])

            st.write("Latest SMC Labels")
            for label in forex["smc_labels"]:
                st.warning(
                    f"{label['label']} | {label['direction']} | confidence {label['confidence']}"
                )

            st.caption(f"Last updated: {forex['timestamp']}")

    st.divider()

    st.subheader("Agent Swarm Monitor")

    workflow = get_json("/agents/workflow-status")

    if "error" in workflow:
        st.error(workflow["error"])
    else:
        st.progress(workflow["progress"] / 100)
        st.caption(f"Current Agent: {workflow['current_agent']}")

        agent_cols = st.columns(3)

        for idx, step in enumerate(workflow["steps"]):
            with agent_cols[idx % 3]:
                status = step["status"]

                if status == "completed":
                    st.success(f"✅ {step['agent']}")
                elif status == "running":
                    st.info(f"🔄 {step['agent']}")
                elif status == "failed":
                    st.error(f"⚠ {step['agent']}")
                else:
                    st.container(border=True).write(f"⏳ {step['agent']}")

                st.caption(step["summary"])

        st.write("Live Handoff Feed")
        for handoff in workflow["handoffs"]:
            st.code(handoff)

else:
    st.subheader("System Logs")

    log_col1, log_col2 = st.columns(2)

    with log_col1:
        st.write("MCX Logs")
        mcx_logs = get_json("/logs/mcx")
        st.code("\n".join(mcx_logs.get("lines", [])))

        st.write("Backend Logs")
        backend_logs = get_json("/logs/backend")
        st.code("\n".join(backend_logs.get("lines", [])))

    with log_col2:
        st.write("Forex Logs")
        forex_logs = get_json("/logs/forex")
        st.code("\n".join(forex_logs.get("lines", [])))

        st.write("Agent Workflow Logs")
        agent_logs = get_json("/logs/agent")
        st.code("\n".join(agent_logs.get("lines", [])))

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
