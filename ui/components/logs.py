from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import streamlit as st

from api_client import (
    decision_trace_latest,
    governance_evidence,
    log_lines,
    specialist_history,
    specialist_latest,
    submission_readiness,
)
from config import TIMEZONE_OPTIONS


SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|authorization|password|secret|token)[\"']?\s*[:=]\s*[\"']?[^,\s\"']+"
)
LOG_PREFIX_PATTERN = re.compile(r"^\[(?P<timestamp>[^\]]+)\]\s*(?P<message>.*)$")
INLINE_ISO_PATTERN = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))"
)

SPECIALIST_ORDER = [
    "Requirement",
    "Market Intelligence",
    "System Readiness",
    "Risk Governance",
    "Delivery Planning",
    "Final Review",
]

SPECIALIST_NAMES = {
    "Requirement Agent": "Requirement",
    "Requirement Specialist": "Requirement",
    "Market Intelligence Agent": "Market Intelligence",
    "Market Intelligence Specialist": "Market Intelligence",
    "Architecture Agent": "System Readiness",
    "System Readiness Specialist": "System Readiness",
    "Risk Governance Agent": "Risk Governance",
    "Risk Governance Specialist": "Risk Governance",
    "Delivery Planning Agent": "Delivery Planning",
    "Delivery Planning Specialist": "Delivery Planning",
    "Final Review Agent": "Final Review",
    "Final Review Specialist": "Final Review",
}

EVIDENCE_SOURCE_GROUPS = {
    "Multi-Timeframe Intelligence": "Multi-Timeframe Intelligence",
    "Multi-Timeframe Intelligence Engine": "Multi-Timeframe Intelligence",
    "Multi-Timeframe Engine": "Multi-Timeframe Intelligence",
    "Scenario Engine": "Scenario Engine",
    "Timeframe Hierarchy": "Timeframe Hierarchy",
    "Timeframe Hierarchy Engine": "Timeframe Hierarchy",
    "Structure Evolution": "Structure Evolution",
    "Structure Evolution Engine": "Structure Evolution",
    "Market Memory": "Market Memory",
    "Market Memory Engine": "Market Memory",
    "Specialist Brief Builder": "Specialist Response Persistence",
    "Specialist Response Persistence": "Specialist Response Persistence",
}

AUDIT_STAGE_ORDER = [
    "Market Data Snapshot",
    "SMC Labels",
    "Multi-Timeframe Intelligence",
    "Structure Evolution",
    "Scenario Engine",
    "Timeframe Hierarchy",
    "Market Memory",
    "Governance Evidence",
    "Band Specialist Reviews",
    "Final Specialist Review",
]

READINESS_COMPONENT_LABELS = {
    "data_layer": "Live Market Data",
    "feed_lifecycle": "Feed Lifecycle",
    "smc_engine": "SMC Structure Labels",
    "multi_timeframe_intelligence": "Multi-Timeframe Intelligence",
    "scenario_engine": "Scenario Engine",
    "timeframe_hierarchy": "Timeframe Hierarchy",
    "market_memory": "Market Memory",
    "band_specialists": "Band Specialist Reviews",
    "governance_evidence": "Governance Evidence",
    "decision_audit_trail": "Decision Audit Trail",
    "specialist_persistence": "Specialist Persistence",
}

READINESS_VERIFY_LOCATIONS = {
    "data_layer": "Live Intelligence panels and Raw System Logs",
    "feed_lifecycle": "Sidebar feed controls and Raw System Logs",
    "smc_engine": "Decision Audit Trail",
    "multi_timeframe_intelligence": "Decision Audit Trail",
    "scenario_engine": "Decision Audit Trail",
    "timeframe_hierarchy": "Decision Audit Trail",
    "market_memory": "Decision Audit Trail",
    "band_specialists": "Agent Workflow Timeline",
    "governance_evidence": "Governance Evidence Summary",
    "decision_audit_trail": "Decision Audit Trail",
    "specialist_persistence": "Agent Workflow Timeline",
}


def safe_text(value: Any, limit: int = 180) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip()
    text = SECRET_PATTERN.sub(r"\1=[redacted]", text)
    text = text.replace("duplicate_skipped", "No material structure change detected")
    text = text.replace("Latest bullish CHOCH BULLISH overrides earlier FVG BEARISH", "Recent bullish structure partially offsets earlier bearish pressure")
    text = text.replace("Latest bearish CHOCH BEARISH overrides earlier FVG BULLISH", "Recent bearish structure partially offsets earlier bullish pressure")
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def safe_log_text(value: Any, limit: int = 500) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip()
    text = SECRET_PATTERN.sub(r"\1=[redacted]", text)
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def format_log_timestamp(value: str, timezone_name: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TIMEZONE_OPTIONS["UTC"])
        target_timezone = TIMEZONE_OPTIONS.get(timezone_name, TIMEZONE_OPTIONS["IST"])
        return parsed.astimezone(target_timezone).strftime(f"%d %b %H:%M:%S {timezone_name}")
    except ValueError:
        return str(value)


def format_log_line_timezone(line: Any, timezone_name: str) -> str:
    text = str(line or "")
    match = LOG_PREFIX_PATTERN.match(text)
    if match:
        timestamp = format_log_timestamp(match.group("timestamp"), timezone_name)
        message = match.group("message")
        message = INLINE_ISO_PATTERN.sub(
            lambda item: format_log_timestamp(item.group("timestamp"), timezone_name),
            message,
        )
        return f"[{timestamp}] {message}"
    return INLINE_ISO_PATTERN.sub(
        lambda item: format_log_timestamp(item.group("timestamp"), timezone_name),
        text,
    )


def format_time(value: Any, timezone_name: str = "IST") -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TIMEZONE_OPTIONS["UTC"])
        target_timezone = TIMEZONE_OPTIONS.get(timezone_name, TIMEZONE_OPTIONS["IST"])
        return parsed.astimezone(target_timezone).strftime(f"%d %b %H:%M {timezone_name}")
    except ValueError:
        return safe_text(text, 32)


def first_available(*values: Any, default: str = "-") -> str:
    for value in values:
        if value not in (None, "", [], {}):
            return str(value)
    return default


def render_metric_cards(metrics: list[tuple[str, Any]], columns: int = 4) -> None:
    cols = st.columns(columns)
    for index, (label, value) in enumerate(metrics):
        with cols[index % columns]:
            st.markdown(
                f"""
                <div class="audit-metric-card">
                    <div class="audit-metric-label">{html.escape(str(label))}</div>
                    <div class="audit-metric-value">{html.escape(safe_text(value, 44) or "-")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


@st.cache_data(ttl=10, show_spinner=False)
def cached_log_lines(log_name: str) -> dict[str, Any]:
    return log_lines(log_name)


def render_log_card(title: str, log_name: str, timezone_name: str, line_limit: int = 50) -> None:
    st.write(title)
    log_data = cached_log_lines(log_name)
    lines = log_data.get("lines", []) if isinstance(log_data, dict) else []
    if not lines:
        lines = ["No raw log lines available."]
    lines = [
        safe_log_text(format_log_line_timezone(line, timezone_name), 500)
        for line in lines[-line_limit:]
    ]
    padded_lines = lines + [""] * max(0, min(12, line_limit) - len(lines))
    escaped_log = html.escape("\n".join(padded_lines))
    st.markdown(
        f'<div class="log-card">{escaped_log}</div>',
        unsafe_allow_html=True,
    )


def render_deployment_readiness(readiness: dict[str, Any]) -> None:
    st.subheader("Deployment Readiness")
    if readiness.get("error"):
        st.warning(f"Readiness endpoint unavailable: {safe_text(readiness.get('error'), 160)}")
        return

    evidence = readiness.get("evidence") or {}
    render_metric_cards(
        [
            ("Readiness Score", readiness.get("readiness_score", "-")),
            ("State", readiness.get("readiness_state", "-")),
            ("Safety", readiness.get("safety_status", "-")),
            ("Evidence", evidence.get("governance_evidence_count", "-")),
            ("Audit Stages", evidence.get("audit_stage_count", "-")),
            ("Specialist Responses", evidence.get("specialist_response_count", "-")),
            ("Workflow", evidence.get("latest_workflow_run_id", "-")),
        ],
        columns=4,
    )

    warnings = readiness.get("warnings") or []
    if warnings:
        st.warning("\n".join(f"- {safe_text(item, 220)}" for item in warnings))

    components = readiness.get("components") if isinstance(readiness, dict) else {}
    if isinstance(components, dict) and components:
        with st.expander("Readiness Verification Breakdown", expanded=False):
            rows = []
            for key, component in components.items():
                component_data = component if isinstance(component, dict) else {}
                rows.append(
                    {
                        "Component": READINESS_COMPONENT_LABELS.get(key, key.replace("_", " ").title()),
                        "Status": safe_text(component_data.get("status", "-"), 32).upper(),
                        "Evidence Summary": safe_text(component_data.get("summary", "-"), 150),
                        "Verify In": READINESS_VERIFY_LOCATIONS.get(key, "Audit console sections"),
                    }
                )
            st.dataframe(rows, use_container_width=True, hide_index=True)

            claims = readiness.get("demo_claims_supported") or []
            if claims:
                st.caption("Supported claims: " + "; ".join(safe_text(claim, 120) for claim in claims[:4]))


def latest_specialist_records(latest: dict[str, Any], history: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    if isinstance(latest, dict):
        records.extend(latest.get("specialists") or [])
        final_review = latest.get("final_review") or {}
        if final_review:
            records.append(final_review)

    if len(records) < 6 and isinstance(history, dict):
        by_name = {friendly_specialist_name(item): item for item in records}
        for item in reversed(history.get("responses") or []):
            friendly = friendly_specialist_name(item)
            if friendly and friendly not in by_name:
                by_name[friendly] = item
        records = list(by_name.values())

    return sorted(records, key=lambda item: specialist_sort_key(friendly_specialist_name(item)))


def friendly_specialist_name(item: dict[str, Any]) -> str:
    name = str(
        item.get("specialist")
        or item.get("specialist_name")
        or item.get("agent")
        or ""
    )
    return SPECIALIST_NAMES.get(name, name.replace(" Agent", "").replace(" Specialist", ""))


def specialist_sort_key(name: str) -> int:
    try:
        return SPECIALIST_ORDER.index(name)
    except ValueError:
        return len(SPECIALIST_ORDER)


def specialist_state(item: dict[str, Any]) -> str:
    brief = item.get("specialist_brief") if isinstance(item.get("specialist_brief"), dict) else {}
    payload = item.get("sanitized_response_payload") if isinstance(item.get("sanitized_response_payload"), dict) else {}
    payload_brief = payload.get("specialist_brief") if isinstance(payload.get("specialist_brief"), dict) else {}
    return first_available(
        brief.get("state"),
        brief.get("decision_state"),
        payload_brief.get("state"),
        payload_brief.get("decision_state"),
        item.get("finding"),
    )


@st.cache_data(ttl=20, show_spinner=False)
def fetch_audit_console_data() -> dict[str, Any]:
    calls = {
        "readiness": lambda: submission_readiness("MCX", "NATURALGAS"),
        "governance": governance_evidence,
        "trace": lambda: decision_trace_latest("MCX", "NATURALGAS"),
        "specialist_latest": lambda: specialist_latest("MCX", "NATURALGAS"),
    }
    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        futures = {name: executor.submit(call) for name, call in calls.items()}
        return {
            name: future.result()
            if not future.exception()
            else {"error": str(future.exception())}
            for name, future in futures.items()
        }


def render_agent_workflow_timeline(
    timezone_name: str,
    latest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    st.subheader("Agent Workflow Timeline")
    history = {}
    preliminary = latest_specialist_records(latest, history)
    if len(preliminary) < 6:
        history = specialist_history("MCX", "NATURALGAS")
    records = latest_specialist_records(latest, history)

    if not records:
        st.info("No persisted specialist workflow responses yet. Run Agent Swarm Review once to populate this audit trail.")
        return latest if isinstance(latest, dict) else {}, history if isinstance(history, dict) else {}, []

    rows = []
    for item in records:
        rows.append(
            {
                "Time": format_time(item.get("created_at") or item.get("timestamp"), timezone_name),
                "Specialist": friendly_specialist_name(item),
                "State/Finding": safe_text(specialist_state(item), 90),
                "Confidence": item.get("confidence", "-"),
                "Response Source": safe_text(item.get("response_source") or response_source_from_payload(item), 44),
                "Workflow Run ID": safe_text(item.get("workflow_run_id") or latest.get("workflow_run_id"), 50),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)
    return latest if isinstance(latest, dict) else {}, history if isinstance(history, dict) else {}, records


def response_source_from_payload(item: dict[str, Any]) -> str:
    payload = item.get("sanitized_response_payload")
    if isinstance(payload, dict):
        return str(payload.get("response_source") or payload.get("status") or "")
    return ""


def evidence_items(governance: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for finding in governance.get("specialist_findings") or []:
        for evidence in finding.get("evidence") or []:
            if isinstance(evidence, dict):
                items.append(
                    {
                        **evidence,
                        "specialist": finding.get("specialist") or finding.get("agent") or "",
                    }
                )
    return items


def evidence_group(source: str) -> str:
    return EVIDENCE_SOURCE_GROUPS.get(source, source or "Other Evidence")


def render_governance_evidence_summary(governance: dict[str, Any]) -> None:
    st.subheader("Governance Evidence Summary")
    if governance.get("error"):
        st.warning(f"Governance evidence unavailable: {safe_text(governance.get('error'), 160)}")
        return

    items = evidence_items(governance)
    groups = sorted({evidence_group(str(item.get("source") or "")) for item in items})
    render_metric_cards(
        [
            ("Evidence Count", governance.get("evidence_count", len(items))),
            ("Specialist Findings", len(governance.get("specialist_findings") or [])),
            ("Sources Used", len(groups)),
        ],
        columns=3,
    )

    if groups:
        st.caption("Sources used: " + ", ".join(groups))

    grouped_items: dict[str, dict[str, Any]] = {}
    for item in items:
        group = evidence_group(str(item.get("source") or ""))
        group_row = grouped_items.setdefault(
            group,
            {
                "specialists": set(),
                "evidence": item.get("fact"),
            },
        )
        specialist = friendly_specialist_name({"specialist": item.get("specialist")})
        if specialist:
            group_row["specialists"].add(specialist)

    representatives = []
    for group in sorted(grouped_items):
        group_row = grouped_items[group]
        specialists = sorted(
            group_row["specialists"],
            key=specialist_sort_key,
        )
        representatives.append(
            {
                "Source Engine": group,
                "Used By": safe_text(", ".join(specialists) or "Specialist workflow", 110),
                "Evidence": safe_text(group_row.get("evidence"), 160),
            }
        )
        if len(representatives) >= 5:
            break

    if representatives:
        st.dataframe(representatives, use_container_width=True, hide_index=True)
    else:
        st.info("No governance evidence references are available yet.")


def render_decision_audit_trail(trace: dict[str, Any], timezone_name: str) -> None:
    st.subheader("Decision Audit Trail")
    if trace.get("error"):
        st.warning(f"Decision trace unavailable: {safe_text(trace.get('error'), 160)}")
        return

    stages_by_name = {
        str(stage.get("stage") or ""): stage
        for stage in trace.get("stages") or []
        if isinstance(stage, dict)
    }
    rows = []
    for stage_name in AUDIT_STAGE_ORDER:
        stage = stages_by_name.get(stage_name, {})
        rows.append(
            {
                "Stage": stage_name,
                "Status": safe_text(stage.get("status", "missing"), 32),
                "Summary": safe_text(stage.get("summary") or "Audit stage evidence is not available yet.", 180),
                "Time": format_time(stage.get("timestamp"), timezone_name),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_raw_system_logs(timezone_name: str) -> None:
    st.subheader("Raw System Logs")
    st.caption(
        f"Developer logs are retained for auditability and capped to the latest 50 lines per source. "
        f"Visible timestamps are shown in {timezone_name}."
    )
    with st.expander("MCX Logs", expanded=False):
        render_log_card("MCX Logs", "mcx", timezone_name)
    with st.expander("Forex Logs", expanded=False):
        render_log_card("Forex Logs", "forex", timezone_name)
    with st.expander("Backend Logs", expanded=False):
        render_log_card("Backend Logs", "backend", timezone_name)
    with st.expander("Agent Workflow Raw Logs", expanded=False):
        render_log_card("Agent Workflow Raw Logs", "agent", timezone_name)


def render_enterprise_review_notes(readiness: dict[str, Any]) -> None:
    evidence = readiness.get("evidence") if isinstance(readiness, dict) else {}
    state = readiness.get("readiness_state", "Unavailable") if isinstance(readiness, dict) else "Unavailable"
    safety = readiness.get("safety_status", "ADVISORY_ONLY") if isinstance(readiness, dict) else "ADVISORY_ONLY"
    evidence_count = (evidence or {}).get("governance_evidence_count", "-")
    st.subheader("Enterprise Review Notes")
    st.markdown(
        f"""
        ### Requirement Summary
        Build a regulated financial AI delivery platform with live MCX and Forex intelligence.

        ### System Readiness Summary
        Current readiness state: **{html.escape(safe_text(state, 60))}**.

        ### Governance Summary
        Safety status remains **{html.escape(safe_text(safety, 60))}** with **{html.escape(str(evidence_count))}** governance evidence items attached.

        ### Delivery Roadmap
        Foundation → Live Data → SMC Labels → Multi-Timeframe Intelligence → Band Specialists → Governance Evidence → Audit Trail → AWS Deployment.
        """
    )


def render_logs_page() -> None:
    st.subheader("System Audit & Governance Console")
    cached_log_lines.clear()
    selected_timezone = st.session_state.get("global_timezone", "IST")

    data = fetch_audit_console_data()
    readiness = data.get("readiness") if isinstance(data.get("readiness"), dict) else {}
    governance = data.get("governance") if isinstance(data.get("governance"), dict) else {}
    trace = data.get("trace") if isinstance(data.get("trace"), dict) else {}
    latest = (
        data.get("specialist_latest")
        if isinstance(data.get("specialist_latest"), dict)
        else {}
    )

    render_deployment_readiness(readiness)
    st.divider()
    render_agent_workflow_timeline(selected_timezone, latest)
    st.divider()
    render_governance_evidence_summary(governance)
    st.divider()
    render_decision_audit_trail(trace, selected_timezone)
    st.divider()
    render_raw_system_logs(selected_timezone)
    st.divider()
    render_enterprise_review_notes(readiness)
