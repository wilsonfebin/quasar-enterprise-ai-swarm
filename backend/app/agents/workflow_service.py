import re
import time
from datetime import datetime, timezone
from typing import Any

from app.agents.band_client import BandClient, record_band_debug_response, utc_now_iso
from app.agents.band_registry import BandAgentRegistry, BandAgentRegistration
from app.data.ingestion_service import append_log
from app.db import DatabaseUnavailable, fetch_latest_market_snapshot
from app.intelligence.multi_timeframe_engine import (
    build_multi_timeframe_snapshot,
    compact_multi_timeframe_summary,
)
from app.services.governance_evidence_service import (
    build_governance_evidence,
    governance_evidence_references_text,
)
from app.services.specialist_brief_builder import (
    build_specialist_brief,
    format_specialist_brief_text,
    is_raw_label_repetition,
)
from app.services.specialist_response_store import (
    save_final_review_response,
    save_specialist_response,
)


WORKFLOW_STEPS = [
    "Requirement Agent",
    "Market Intelligence Agent",
    "Architecture Agent",
    "Risk Governance Agent",
    "Delivery Planning Agent",
    "Final Review Agent",
]

WORKFLOW_AGENT_SEQUENCE = WORKFLOW_STEPS


def _initial_workflow_steps() -> list[dict[str, Any]]:
    return [
        {
            "agent": agent,
            "status": "waiting",
            "summary": "Waiting for Band analysis.",
            "prompt_sent": "",
            "response_text": "",
            "response_preview": "",
            "response_received": False,
            "specialist_brief": {},
            "response_source": "",
            "started_at": "",
            "completed_at": "",
            "duration_seconds": None,
            "band_event_id": None,
            "updated_at": "",
        }
        for agent in WORKFLOW_STEPS
    ]


WORKFLOW_STATE: dict[str, Any] = {
    "workflow_id": "quasar-delivery-swarm-001",
    "current_agent": "Waiting",
    "progress": 0,
    "steps": _initial_workflow_steps(),
    "final_summary": "",
    "status": "waiting",
    "chat_id": "",
        "message_id": "",
        "analysis_scope": "MCX",
        "orchestration_mode": "internal",
    "updated_at": "",
}

LAST_BAND_PROCESSING_STATE: dict[str, Any] = {
    "last_message_status": "not_run",
    "last_chat_id": "",
    "last_message_id": "",
    "last_error": "",
    "last_response": "",
    "last_processed_at": "",
    "orchestration_mode": "internal",
}


def get_band_processing_state() -> dict[str, Any]:
    return LAST_BAND_PROCESSING_STATE


def update_band_processing_state(**kwargs) -> dict[str, Any]:
    LAST_BAND_PROCESSING_STATE.update(kwargs)
    return LAST_BAND_PROCESSING_STATE


def get_workflow_state() -> dict[str, Any]:
    return WORKFLOW_STATE


def get_workflow_details() -> dict[str, Any]:
    steps = WORKFLOW_STATE["steps"]
    workflow_status = WORKFLOW_STATE.get("status", "waiting")
    completed_specialists = sum(1 for step in steps if step.get("status") == "completed")
    final_review_completed = any(
        step.get("agent") == "Final Review Agent" and step.get("status") == "completed"
        for step in steps
    )
    return {
        "workflow_id": WORKFLOW_STATE["workflow_id"],
        "workflow_run_id": WORKFLOW_STATE["workflow_id"],
        "status": workflow_status,
        "current_state": workflow_status,
        "specialist_workflow_running": workflow_status == "running",
        "completed_specialists": completed_specialists,
        "completed_count": completed_specialists,
        "total_specialists": len(steps) or len(WORKFLOW_STEPS),
        "total_count": len(steps) or len(WORKFLOW_STEPS),
        "final_review_completed": final_review_completed,
        "active_agent": WORKFLOW_STATE.get("current_agent", ""),
        "progress": WORKFLOW_STATE.get("progress", 0),
        "chat_id": WORKFLOW_STATE.get("chat_id", ""),
            "message_id": WORKFLOW_STATE.get("message_id", ""),
            "analysis_scope": WORKFLOW_STATE.get("analysis_scope", "MCX"),
            "orchestration_mode": WORKFLOW_STATE.get("orchestration_mode", "internal"),
        "completed_agents": completed_specialists,
        "execution_time_seconds": _workflow_execution_time(steps),
        "timeline": _workflow_timeline(steps),
        "steps": steps,
        "delivery_pack": _delivery_pack(steps) if workflow_status == "completed" else {},
        "final_summary": WORKFLOW_STATE.get("final_summary", ""),
        "updated_at": WORKFLOW_STATE.get("updated_at", ""),
    }


def reset_workflow_state(status: str = "waiting") -> dict[str, Any]:
    WORKFLOW_STATE.update(
        {
            "current_agent": "Waiting",
            "progress": 0,
            "steps": _initial_workflow_steps(),
            "final_summary": "",
            "status": status,
            "chat_id": "",
            "message_id": "",
            "analysis_scope": "MCX",
            "orchestration_mode": "internal",
            "updated_at": utc_now_iso(),
        }
    )
    return WORKFLOW_STATE


def update_workflow_step(
    agent: str,
    status: str,
    summary: str,
    band_event_id: str | None = None,
    prompt_sent: str | None = None,
    response_text: str | None = None,
    response_received: bool | None = None,
    specialist_brief: dict[str, Any] | None = None,
    response_source: str | None = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    for step in WORKFLOW_STATE["steps"]:
        if step["agent"] == agent:
            updates = {
                "status": status,
                "summary": summary,
                "band_event_id": band_event_id,
                "updated_at": now,
            }
            if status == "running" and not step.get("started_at"):
                updates["started_at"] = now
            if status in {"completed", "failed"}:
                updates["completed_at"] = now
                updates["duration_seconds"] = _duration_seconds(
                    step.get("started_at", ""), now
                )
            if prompt_sent is not None:
                updates["prompt_sent"] = prompt_sent
            if response_text is not None:
                updates["response_text"] = response_text
                updates["response_preview"] = _clean_preview(response_text)
            if response_received is not None:
                updates["response_received"] = response_received
            if specialist_brief is not None:
                updates["specialist_brief"] = specialist_brief
            if response_source is not None:
                updates["response_source"] = response_source
            step.update(updates)
            break

    completed_count = sum(
        1 for step in WORKFLOW_STATE["steps"] if step["status"] == "completed"
    )
    failed_count = sum(
        1 for step in WORKFLOW_STATE["steps"] if step["status"] == "failed"
    )
    terminal_count = completed_count + failed_count
    if status == "running":
        current_agent = agent
        workflow_status = "running"
    elif terminal_count == len(WORKFLOW_STEPS):
        current_agent = "Failed" if failed_count else "Completed"
        workflow_status = "failed" if failed_count else "completed"
    else:
        current_agent = "Failed" if status == "failed" else agent
        workflow_status = "running"

    WORKFLOW_STATE.update(
        {
            "current_agent": current_agent,
            "progress": int(completed_count / len(WORKFLOW_STEPS) * 100),
            "status": workflow_status,
            "updated_at": now,
        }
    )
    return WORKFLOW_STATE


def _duration_seconds(started_at: str, completed_at: str) -> float | None:
    if not started_at or not completed_at:
        return None
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(completed_at)
        return round((end - start).total_seconds(), 1)
    except ValueError:
        return None


def _clean_preview(text: str, max_chars: int = 100) -> str:
    cleaned = _clean_band_text(text)
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[: max_chars - 3]}..."


def _clean_band_text(text: str) -> str:
    cleaned = re.sub(r"@\[\[[^\]]+\]\]\s*", "", str(text or ""))
    cleaned = re.sub(r"@Quasar[-\s]?Remote[-\s]?Agent\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"@quasar[-\s]?remote[-\s]?agent\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^@[\w./-]+\s+", "", cleaned)
    cleaned = re.sub(
        (
            r"^(Requirement Agent|Market Intelligence Agent|Architecture Agent|"
            r"System Readiness Agent|Risk Governance Agent|Delivery Planning Agent|"
            r"Final Review Agent)"
            r"\s+response:\s*"
        ),
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return " ".join(cleaned.split())


def _workflow_timeline(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "agent": step.get("agent", ""),
            "status": step.get("status", ""),
            "started_at": step.get("started_at", ""),
            "completed_at": step.get("completed_at", ""),
            "duration_seconds": step.get("duration_seconds"),
        }
        for step in steps
        if step.get("started_at") or step.get("completed_at")
    ]


def _workflow_execution_time(steps: list[dict[str, Any]]) -> float | None:
    started = [step.get("started_at", "") for step in steps if step.get("started_at")]
    completed = [step.get("completed_at", "") for step in steps if step.get("completed_at")]
    if not started or not completed:
        return None
    return _duration_seconds(min(started), max(completed))


def _delivery_pack(steps: list[dict[str, Any]]) -> dict[str, Any]:
    titles = {
        "Requirement Agent": "Scope",
        "Market Intelligence Agent": "Market Structure Intelligence",
        "Architecture Agent": "System Readiness",
        "Risk Governance Agent": "Risk Guardrails",
        "Delivery Planning Agent": "Decision Plan",
        "Final Review Agent": "Final Specialist Review",
    }
    sections = []
    for step in steps:
        sections.append(
            {
                "title": titles.get(step.get("agent", ""), step.get("agent", "")),
                "agent": step.get("agent", ""),
                "status": step.get("status", ""),
                "content": step.get("response_text") or step.get("summary", ""),
                "preview": step.get("response_preview")
                or _clean_preview(step.get("summary", "")),
                "duration_seconds": step.get("duration_seconds"),
            }
        )
    return {
        "sections": sections,
        "diagnostics": {
            "workflow_id": WORKFLOW_STATE.get("workflow_id", ""),
            "band_chat_id": WORKFLOW_STATE.get("chat_id", ""),
            "source_message_id": WORKFLOW_STATE.get("message_id", ""),
            "execution_time_seconds": _workflow_execution_time(steps),
            "completed_agents": sum(
                1 for step in steps if step.get("status") == "completed"
            ),
        },
    }


def summarize_market_context_for_band(context: dict[str, Any]) -> str:
    def fmt_price(value: Any, decimals: int) -> str:
        try:
            return f"{float(value):.{decimals}f}"
        except (TypeError, ValueError):
            return "0".ljust(decimals + 2, "0")

    def fmt_volume(value: Any) -> str:
        try:
            return f"{int(float(value)):,}"
        except (TypeError, ValueError):
            return "0"

    def fmt_bias(value: str) -> str:
        return str(value or "NEUTRAL").replace("_", " ").title()

    def fmt_state(value: Any, fallback: str = "Unavailable") -> str:
        return str(value or fallback).replace("_", " ").title()

    def primary_scenario_line(mtf_snapshot: dict[str, Any]) -> str:
        primary = ((mtf_snapshot.get("scenarios") or {}).get("primary_scenario") or {})
        secondary = ((mtf_snapshot.get("scenarios") or {}).get("secondary_scenario") or {})
        if not primary:
            return "Primary scenario unavailable"
        line = f"{primary.get('name', 'Scenario unavailable')} ({primary.get('probability', 0)}%)"
        if secondary:
            line = (
                f"{line}; alternative {secondary.get('name', 'Unavailable')} "
                f"({secondary.get('probability', 0)}%)"
            )
        return line

    def hierarchy_line(mtf_snapshot: dict[str, Any]) -> str:
        hierarchy = mtf_snapshot.get("timeframe_hierarchy") or {}
        if not hierarchy:
            return "Hierarchy unavailable"
        return (
            f"{hierarchy.get('dominant_context', 'Unknown')}; "
            f"conflict {hierarchy.get('hierarchy_conflict', 'Unknown')}; "
            f"bias {hierarchy.get('scenario_bias', 'Unknown')}"
        )

    def memory_line(mtf_snapshot: dict[str, Any]) -> str:
        memory = mtf_snapshot.get("memory") or {}
        evolution = mtf_snapshot.get("evolution") or {}
        parts = []
        if memory:
            parts.append(f"memory status {memory.get('status', 'unknown')}")
        if evolution:
            parts.append(str(evolution.get("summary") or "evolution snapshot available"))
        return "; ".join(parts) if parts else "Memory and persistence unavailable"

    def validation_line(mtf_snapshot: dict[str, Any]) -> str:
        decision = mtf_snapshot.get("decision") or {}
        next_validation = decision.get("next_validation")
        if next_validation:
            return str(next_validation)
        triggers = mtf_snapshot.get("validation_triggers") or {}
        conditions = triggers.get("wait_conditions") or []
        return "; ".join(str(item) for item in conditions[:2]) or "Wait for confirmation."

    def intelligence_artifact_lines(mtf_snapshot: dict[str, Any]) -> list[str]:
        if not mtf_snapshot:
            return ["Quasar Intelligence Artifacts:", "- Multi-timeframe intelligence unavailable."]
        decision = mtf_snapshot.get("decision") or {}
        narrative = mtf_snapshot.get("narrative") or {}
        evidence_text = governance_evidence_references_text(
            build_governance_evidence(get_workflow_details(), context)
        )
        return [
            "Quasar Intelligence Artifacts:",
            f"- Market Regime: {fmt_state(mtf_snapshot.get('regime'))}",
            f"- Decision State: {decision.get('state', 'WAIT')}",
            f"- Scenario Engine: {primary_scenario_line(mtf_snapshot)}",
            f"- Timeframe Hierarchy: {hierarchy_line(mtf_snapshot)}",
            f"- Market Memory / Persistence: {memory_line(mtf_snapshot)}",
            f"- Validation Conditions: {validation_line(mtf_snapshot)}",
            f"- Executive Narrative: {narrative.get('summary', 'Narrative unavailable.')}",
            "- Governance Evidence:",
            *[f"  {line}" for line in evidence_text.splitlines()[1:]],
        ]

    def label_lines(labels: list[dict[str, Any]]) -> list[str]:
        if not labels:
            return ["  - No current structure labels"]
        lines = []
        for label in labels[:3]:
            confidence = int(round(float(label.get("confidence") or 0) * 100))
            lines.append(
                f"  - {label.get('label', 'UNKNOWN')} confidence {confidence}%"
            )
        return lines

    def focused_market_block(market: dict[str, Any], title: str, decimals: int) -> list[str]:
        candle = market.get("candle", {})
        return [
            "Quasar Current Findings",
            f"Scope: {title} {market.get('instrument', '')}",
            f"Timeframe: {context.get('timeframe', '1m')}",
            (
                "Candle: "
                f"O {fmt_price(candle.get('open'), decimals)} "
                f"H {fmt_price(candle.get('high'), decimals)} "
                f"L {fmt_price(candle.get('low'), decimals)} "
                f"C {fmt_price(candle.get('close'), decimals)} "
                f"Vol {fmt_volume(candle.get('volume'))}"
            ),
            "Supporting Signals:",
            *[line.replace("  - ", "- ") for line in label_lines(market.get("labels", []))],
            f"Dominant Bias: {fmt_bias(market.get('dominant_bias', 'NEUTRAL'))}",
            f"Session: {market.get('session', 'Unknown')}",
            f"Data Age: {market.get('data_age', 'unknown')}",
            f"Source: {market.get('source', 'unknown') or 'unknown'}",
            "Safety: Advisory-only. Execution disabled. No directional calls.",
        ]

    scope = str(context.get("analysis_scope", "MCX")).upper()
    if scope == "FOREX":
        lines = focused_market_block(context.get("forex", {}), "Forex", 5)
    else:
        lines = focused_market_block(context.get("mcx", {}), "MCX", 2)

    mtf_snapshot = context.get("multi_timeframe")
    if mtf_snapshot:
        lines.extend(
            [
                "",
                *intelligence_artifact_lines(mtf_snapshot),
                "",
                "Detailed Multi-Timeframe Diagnostics:",
                compact_multi_timeframe_summary(mtf_snapshot),
            ]
        )
    return "\n".join(lines)


class WorkflowService:
    def __init__(self, band_client: BandClient | None = None):
        self.band_client = band_client or BandClient()

    def prepare_workflow(self, requirement: str) -> dict[str, Any]:
        # TODO Phase 4D: map this sequence to Band peers and chat participants.
        return {
            "status": "prepared",
            "requirement": requirement,
            "agents": WORKFLOW_AGENT_SEQUENCE,
            "execution_enabled": False,
        }

    def start_workflow(self, workflow_id: str) -> dict[str, Any]:
        # TODO Phase 4D: dispatch the first real workflow message/event.
        return {
            "status": "not_started",
            "workflow_id": workflow_id,
            "execution_enabled": False,
        }

    def run_band_health_check(self) -> dict[str, Any]:
        client = self.band_client
        if not client.is_enabled():
            append_log("band.log", "Band workflow test skipped: disabled")
            result = {
                "success": False,
                "status": "disabled",
                "message": "Band integration disabled",
                "chat_count": 0,
                "chat_ids": [],
                "message_count": 0,
                "latest_message": "",
                "errors": ["Band integration disabled"],
            }
            record_band_debug_response(result)
            return result

        if not client.is_configured():
            append_log("band.log", "Band workflow test skipped: missing credentials")
            result = {
                "success": False,
                "status": "missing_credentials",
                "message": "Band credentials missing",
                "chat_count": 0,
                "chat_ids": [],
                "message_count": 0,
                "latest_message": "",
                "errors": ["Band credentials missing"],
            }
            record_band_debug_response(result)
            return result

        chats_response = client.list_chats()
        chats = self._extract_data_list(chats_response)
        chat_ids = [str(chat.get("id", "")) for chat in chats if chat.get("id")]
        if chats_response.get("status") == "error":
            append_log("band.log", "Band workflow test failure: chat discovery failed")
            result = {
                "success": False,
                "status": "chat_discovery_failed",
                "message": chats_response.get("message", "Unable to list Band chats"),
                "chat_count": 0,
                "chat_ids": [],
                "message_count": 0,
                "latest_message": "",
                "errors": [chats_response.get("message", "Unable to list Band chats")],
                "raw": {"chats_response": chats_response},
            }
            record_band_debug_response(result)
            return result

        if not chats:
            append_log("band.log", "Band workflow test failure: no chats available")
            result = {
                "success": False,
                "status": "no_chats",
                "message": "No Band chat rooms available",
                "chat_count": 0,
                "chat_ids": [],
                "message_count": 0,
                "latest_message": "",
                "errors": ["No Band chat rooms available"],
                "raw": {"chats_response": chats_response},
            }
            record_band_debug_response(result)
            return result

        chat = chats[0]
        chat_id = str(chat.get("id", ""))
        if not chat_id:
            append_log("band.log", "Band workflow test failure: chat id missing")
            result = {
                "success": False,
                "status": "invalid_chat",
                "message": "Selected Band chat did not include an id",
                "chat_count": len(chats),
                "chat_ids": chat_ids,
                "message_count": 0,
                "latest_message": "",
                "errors": ["Selected Band chat did not include an id"],
                "raw": {"chats_response": chats_response},
            }
            record_band_debug_response(result)
            return result

        participants_response = client.get_participants(chat_id)
        mentions = self._build_mentions(participants_response)
        content = "Quasar workflow health check"
        if mentions and mentions[0].get("handle"):
            content = f"@{mentions[0]['handle']} Quasar workflow health check"

        send_response = client.send_chat_message(
            chat_id=chat_id,
            content=content,
            mentions=mentions,
        )
        message_sent = send_response.get("status") != "error"
        if not message_sent:
            append_log("band.log", "Band workflow test failure: message send failed")
            result = {
                "success": False,
                "status": "message_send_failed",
                "chat_id": chat_id,
                "chat_count": len(chats),
                "chat_ids": chat_ids,
                "message_sent": False,
                "message_count": 0,
                "messages_found": 0,
                "latest_message": "",
                "message": send_response.get("message", "Band message send failed"),
                "errors": [send_response.get("message", "Band message send failed")],
                "raw": {
                    "chats_response": chats_response,
                    "participants_response": participants_response,
                    "send_response": send_response,
                },
            }
            record_band_debug_response(result)
            return result

        time.sleep(2)
        messages_response = client.get_chat_messages(chat_id=chat_id, status="all", limit=20)
        messages = self._extract_data_list(messages_response)
        if messages_response.get("status") == "error":
            append_log("band.log", "Band workflow test failure: message retrieval failed")
            result = {
                "success": False,
                "status": "message_retrieval_failed",
                "chat_id": chat_id,
                "chat_count": len(chats),
                "chat_ids": chat_ids,
                "message_sent": True,
                "message_count": 0,
                "messages_found": 0,
                "latest_message": "",
                "message": messages_response.get(
                    "message", "Unable to retrieve Band messages"
                ),
                "errors": [
                    messages_response.get("message", "Unable to retrieve Band messages")
                ],
                "raw": {
                    "chats_response": chats_response,
                    "participants_response": participants_response,
                    "send_response": send_response,
                    "messages_response": messages_response,
                },
            }
            record_band_debug_response(result)
            return result

        latest_message = self._latest_message_text(messages)
        append_log("band.log", "Band response received")
        append_log("band.log", "Band workflow test success")
        result = {
            "success": True,
            "status": "ok",
            "chat_id": chat_id,
            "chat_title": chat.get("title", ""),
            "chat_count": len(chats),
            "chat_ids": chat_ids,
            "message_sent": True,
            "message_count": len(messages),
            "messages_found": len(messages),
            "latest_message": latest_message,
            "errors": [],
            "response_time": utc_now_iso(),
            "raw": {
                "chats_response": chats_response,
                "participants_response": participants_response,
                "send_response": send_response,
                "messages_response": messages_response,
            },
        }
        record_band_debug_response(result)
        return result

    def get_latest_band_response(self) -> dict[str, Any]:
        client = self.band_client
        chats_response = client.list_chats()
        chats = self._extract_data_list(chats_response)
        if not chats:
            return {"success": False, "latest_message": "", "messages_found": 0}
        chat_id = str(chats[0].get("id", ""))
        messages_response = client.get_chat_messages(chat_id=chat_id, status="all", limit=20)
        messages = self._extract_data_list(messages_response)
        return {
            "success": messages_response.get("status") != "error",
            "chat_id": chat_id,
            "messages_found": len(messages),
            "latest_message": self._latest_message_text(messages),
            "response_time": utc_now_iso(),
        }

    def discover_participants(self, chat_id: str | None = None) -> dict[str, Any]:
        selected_chat_id = chat_id or self._first_chat_id()
        if not selected_chat_id:
            return {"chat_id": "", "participants": [], "registry": BandAgentRegistry([]).as_dict()}
        participants_response = self.band_client.get_participants(selected_chat_id)
        participants = self._extract_data_list(participants_response)
        registry = BandAgentRegistry(participants)
        return {
            "chat_id": selected_chat_id,
            "participants": participants,
            "registry": registry.as_dict(),
        }

    def process_next_band_message(self, chat_id: str | None = None) -> dict[str, Any]:
        client = self.band_client
        if not client.is_enabled():
            return self._record_processing_result(
                success=False,
                status="disabled",
                error="Band integration disabled",
            )
        if not client.is_configured():
            return self._record_processing_result(
                success=False,
                status="missing_credentials",
                error="Band credentials missing",
            )

        selected_chat_id = chat_id or self._first_chat_id()
        if not selected_chat_id:
            append_log("band.log", "Band processing failed: no chat available")
            return self._record_processing_result(
                success=False,
                status="no_chats",
                error="No Band chat rooms available",
            )

        next_response = client.get_next_message(selected_chat_id)
        message = self._extract_message(next_response)
        if next_response.get("status") == "error":
            append_log("band.log", "Band processing failed: next message request failed")
            return self._record_processing_result(
                success=False,
                status="failed",
                chat_id=selected_chat_id,
                error=next_response.get("message", "Unable to fetch next Band message"),
                raw={"next_response": next_response},
            )

        if not message:
            append_log("band.log", "Band no message available")
            return self._record_processing_result(
                success=True,
                status="no_messages",
                chat_id=selected_chat_id,
                raw={"next_response": next_response},
            )

        message_id = str(message.get("id", ""))
        if not message_id:
            append_log("band.log", "Band processing failed: message id missing")
            return self._record_processing_result(
                success=False,
                status="failed",
                chat_id=selected_chat_id,
                error="Band message did not include an id",
                raw={"next_response": next_response},
            )

        processing_started = False
        try:
            processing_response = client.mark_message_processing(
                selected_chat_id, message_id
            )
            if processing_response.get("status") == "error":
                append_log("band.log", "Band message processing start failed")
                return self._record_processing_result(
                    success=False,
                    status="failed",
                    chat_id=selected_chat_id,
                    message_id=message_id,
                    error=processing_response.get(
                        "message", "Unable to mark Band message processing"
                    ),
                    raw={
                        "next_response": next_response,
                        "processing_response": processing_response,
                    },
                )

            processing_started = True
            append_log("band.log", "Band message processing started")
            incoming_content = self._latest_message_text([message])
            response_text = self._build_remote_agent_response(incoming_content)
            mentions = self._build_response_mentions(selected_chat_id, message)
            if not mentions:
                raise RuntimeError("No mentionable Band participant found for response")

            mention_prefix = self._mention_prefix(mentions[0])
            send_response = client.send_chat_message(
                chat_id=selected_chat_id,
                content=f"{mention_prefix} {response_text}",
                mentions=mentions,
            )
            if send_response.get("status") == "error":
                raise RuntimeError(send_response.get("message", "Band response failed"))

            append_log("band.log", "Band response sent")
            processed_response = client.mark_message_processed(
                selected_chat_id, message_id
            )
            if processed_response.get("status") == "error":
                raise RuntimeError(
                    processed_response.get(
                        "message", "Unable to mark Band message processed"
                    )
                )

            append_log("band.log", "Band message processed success")
            return self._record_processing_result(
                success=True,
                status="processed",
                chat_id=selected_chat_id,
                message_id=message_id,
                response_sent=True,
                latest_message=response_text,
                raw={
                    "next_response": next_response,
                    "processing_response": processing_response,
                    "send_response": send_response,
                    "processed_response": processed_response,
                },
            )
        except Exception as exc:
            error = str(exc)
            append_log("band.log", f"Band message processing failed: {error}")
            failed_response = {}
            if processing_started:
                failed_response = client.mark_message_failed(
                    selected_chat_id, message_id, error
                )
                append_log("band.log", "Band message failed acknowledgement sent")
            return self._record_processing_result(
                success=False,
                status="failed",
                chat_id=selected_chat_id,
                message_id=message_id,
                error=error,
                raw={"next_response": next_response, "failed_response": failed_response},
            )

    def build_quasar_context(
        self, timeframe: str = "1m", analysis_scope: str = "MCX"
    ) -> dict[str, Any]:
        try:
            snapshot = fetch_latest_market_snapshot(timeframe=timeframe)
        except DatabaseUnavailable:
            snapshot = {}

        scope = self._normalize_analysis_scope(analysis_scope)
        mcx = snapshot.get("mcx", {})
        forex = snapshot.get("forex", {})
        mcx_labels = self._top_context_labels(mcx.get("smc_labels", []))
        forex_labels = self._top_context_labels(forex.get("smc_labels", []))
        context = {
            "timeframe": timeframe,
            "analysis_scope": scope,
            "scope_label": "Forex XAUUSD" if scope == "FOREX" else "MCX NATURALGAS",
            "safety": {
                "mode": "advisory_only",
                "no_orders": True,
                "no_buy_sell_signals": True,
            },
        }
        if scope == "FOREX":
            context["multi_timeframe"] = self._multi_timeframe_context(
                "FOREX",
                forex.get("instrument", "XAUUSD"),
                timeframe,
            )
            context["forex"] = {
                "instrument": forex.get("instrument", "XAUUSD"),
                "source": forex.get("source", ""),
                "status": forex.get("status", ""),
                "timestamp": forex.get("timestamp", ""),
                "candle": self._clean_candle(forex.get("candle", {})),
                "labels": forex_labels,
                "dominant_bias": self._dominant_bias(forex_labels),
                "data_age": self._data_age(forex.get("timestamp", "")),
                "session": self._market_session("FOREX"),
            }
        else:
            context["multi_timeframe"] = self._multi_timeframe_context(
                "MCX",
                mcx.get("instrument", "NATURALGAS"),
                timeframe,
            )
            context["mcx"] = {
                "instrument": mcx.get("instrument", "NATURALGAS"),
                "source": mcx.get("source", ""),
                "status": mcx.get("status", ""),
                "timestamp": mcx.get("timestamp", ""),
                "candle": self._clean_candle(mcx.get("candle", {})),
                "labels": mcx_labels,
                "dominant_bias": self._dominant_bias(mcx_labels),
                "data_age": self._data_age(mcx.get("timestamp", "")),
                "session": self._market_session("MCX"),
            }
        return context

    def _multi_timeframe_context(
        self,
        market_type: str,
        instrument: str,
        selected_timeframe: str,
    ) -> dict[str, Any]:
        try:
            return build_multi_timeframe_snapshot(
                market_type=market_type,
                instrument=instrument,
                selected_timeframe=selected_timeframe,
            )
        except Exception as exc:
            append_log("backend.log", f"Multi-timeframe context unavailable: {exc}")
            return {}

    def summarize_market_context_for_band(self, context: dict[str, Any]) -> str:
        return summarize_market_context_for_band(context)

    def run_quasar_delivery_workflow(
        self,
        chat_id: str,
        message_id: str,
        incoming_content: str,
        mentions: list[dict[str, Any]],
        registry: BandAgentRegistry | None = None,
        analysis_scope: str = "MCX",
    ) -> dict[str, Any]:
        append_log("band.log", "Quasar Band workflow started")
        reset_workflow_state(status="running")
        WORKFLOW_STATE.update(
            {
                "current_agent": "Waiting",
                "chat_id": chat_id,
                "message_id": message_id,
                "analysis_scope": self._normalize_analysis_scope(analysis_scope),
                "orchestration_mode": "specialist"
                if registry and registry.all_specialists_connected()
                else "internal",
            }
        )

        if registry and registry.all_specialists_connected():
            append_log("band.log", "Quasar specialist orchestration mode active")
            return self._run_specialist_orchestration(
                chat_id=chat_id,
                message_id=message_id,
                incoming_content=incoming_content,
                mentions=mentions,
                registry=registry,
                analysis_scope=analysis_scope,
            )

        append_log("band.log", "Quasar internal workflow fallback active")

        context: dict[str, Any] = {}
        stage_plan = [
            (
                "Requirement Agent",
                "Requirement Agent started requirement analysis",
                "Converted Band request into Quasar delivery workflow scope.",
            ),
            (
                "Market Intelligence Agent",
                "Market Intelligence Agent reviewed latest MCX/Forex structure context",
                "Reviewed latest MCX and Forex candles and market structure labels.",
            ),
            (
                "Architecture Agent",
                "Architecture Agent prepared deployment architecture",
                "Prepared FastAPI, Streamlit, TimescaleDB, Docker, and Band architecture path.",
            ),
            (
                "Risk Governance Agent",
                "Risk Governance Agent validated advisory-only and no-execution controls",
                "Validated advisory-only, execution-disabled, and no directional-call controls.",
            ),
            (
                "Delivery Planning Agent",
                "Delivery Planning Agent prepared implementation roadmap",
                "Prepared phased implementation roadmap for hackathon delivery.",
            ),
            (
                "Final Review Agent",
                "Final Review Agent generated enterprise delivery summary",
                "Generated final enterprise delivery summary.",
            ),
        ]

        event_responses = []
        for agent, event_content, completed_summary in stage_plan:
            update_workflow_step(
                agent,
                "running",
                event_content,
                prompt_sent=event_content,
            )
            append_log("band.log", f"{agent} started")
            if agent == "Market Intelligence Agent":
                context = self.build_quasar_context(analysis_scope=analysis_scope)

            event_response = self.band_client.post_chat_event(
                chat_id=chat_id,
                event_type="task",
                payload={
                    "content": event_content,
                    "agent": agent,
                    "incoming_message_id": message_id,
                    "context": context if agent == "Market Intelligence Agent" else {},
                },
            )
            event_id = self._extract_event_id(event_response)
            event_responses.append(event_response)
            append_log("band.log", f"Band event posted for {agent}")
            update_workflow_step(
                agent,
                "completed",
                completed_summary,
                event_id,
                response_text=completed_summary,
                response_received=True,
            )
            append_log("band.log", f"{agent} completed")

        final_summary = self._build_final_summary()
        mention_prefix = self._mention_prefix(mentions[0]) if mentions else "@participant"
        final_response = self.band_client.send_chat_message(
            chat_id=chat_id,
            content=f"{mention_prefix} {final_summary}",
            mentions=mentions,
        )
        if final_response.get("status") == "error":
            append_log(
                "band.log",
                "Quasar final response send failed; retaining local workflow summary",
            )
            final_response = {
                **final_response,
                "status": "local_fallback",
                "message": final_response.get("message", "Final Band response failed"),
            }
        else:
            append_log("band.log", "Quasar final response sent")

        WORKFLOW_STATE.update(
            {
                "current_agent": "Final Review Agent",
                "progress": 100,
                "final_summary": final_summary,
                "status": "completed",
                "updated_at": utc_now_iso(),
            }
        )
        append_log("band.log", "Quasar Band workflow completed")
        return {
            "status": "completed",
            "workflow_progress": 100,
            "completed_agents": len(WORKFLOW_STEPS),
            "final_summary": final_summary,
            "steps": WORKFLOW_STATE["steps"],
            "context": context,
            "event_responses": event_responses,
            "final_response": final_response,
            "orchestration_mode": "internal",
        }

    def run_quasar_workflow_from_band(
        self,
        chat_id: str | None = None,
        debug: bool = False,
        analysis_scope: str = "MCX",
    ) -> dict[str, Any]:
        client = self.band_client
        if not client.is_enabled():
            result = self._record_processing_result(
                success=False,
                status="disabled",
                error="Band integration disabled",
            )
            return result if debug else self._compact_workflow_response(result)
        if not client.is_configured():
            result = self._record_processing_result(
                success=False,
                status="missing_credentials",
                error="Band credentials missing",
            )
            return result if debug else self._compact_workflow_response(result)

        selected_chat_id = chat_id or self._first_chat_id()
        if not selected_chat_id:
            result = self._record_processing_result(
                success=False,
                status="no_chats",
                error="No Band chat rooms available",
            )
            return result if debug else self._compact_workflow_response(result)

        next_response = client.get_next_message(selected_chat_id)
        message = self._extract_message(next_response)
        if next_response.get("status") == "error":
            result = self._record_processing_result(
                success=False,
                status="failed",
                chat_id=selected_chat_id,
                error=next_response.get("message", "Unable to fetch next Band message"),
                raw={"next_response": next_response},
            )
            return result if debug else self._compact_workflow_response(result)

        if not message:
            return self._run_manual_workflow_trigger(
                selected_chat_id=selected_chat_id,
                debug=debug,
                raw={"next_response": next_response, "source": "manual_trigger"},
                analysis_scope=analysis_scope,
            )

        if str(message.get("sender_type", "")).lower() == "agent":
            stale_message_id = self._message_id(message)
            if stale_message_id:
                self.band_client.mark_message_processing(selected_chat_id, stale_message_id)
                self.band_client.mark_message_processed(selected_chat_id, stale_message_id)
            return self._run_manual_workflow_trigger(
                selected_chat_id=selected_chat_id,
                debug=debug,
                raw={
                    "next_response": next_response,
                    "source": "manual_trigger_after_stale_agent_message",
                },
                analysis_scope=analysis_scope,
            )

        message_id = str(message.get("id", ""))
        if not message_id:
            result = self._record_processing_result(
                success=False,
                status="failed",
                chat_id=selected_chat_id,
                error="Band message did not include an id",
                raw={"next_response": next_response},
            )
            return result if debug else self._compact_workflow_response(result)

        processing_started = False
        try:
            processing_response = client.mark_message_processing(
                selected_chat_id, message_id
            )
            if processing_response.get("status") == "error":
                result = self._record_processing_result(
                    success=False,
                    status="failed",
                    chat_id=selected_chat_id,
                    message_id=message_id,
                    error=processing_response.get(
                        "message", "Unable to mark Band message processing"
                    ),
                    raw={
                        "next_response": next_response,
                        "processing_response": processing_response,
                    },
                )
                return result if debug else self._compact_workflow_response(result)

            processing_started = True
            append_log("band.log", "Band workflow source message marked processing")
            incoming_content = self._latest_message_text([message])
            mentions = self._build_response_mentions(selected_chat_id, message)
            if not mentions:
                raise RuntimeError("No mentionable Band participant found for final response")
            participants = self._extract_data_list(
                self.band_client.get_participants(selected_chat_id)
            )
            registry = BandAgentRegistry(participants)

            workflow_result = self.run_quasar_delivery_workflow(
                chat_id=selected_chat_id,
                message_id=message_id,
                incoming_content=incoming_content,
                mentions=mentions,
                registry=registry,
                analysis_scope=analysis_scope,
            )
            processed_response = client.mark_message_processed(
                selected_chat_id, message_id
            )
            if processed_response.get("status") == "error":
                raise RuntimeError(
                    processed_response.get(
                        "message", "Unable to mark Band message processed"
                    )
                )

            result = {
                "success": workflow_result.get("status", "completed") == "completed",
                "status": workflow_result.get("status", "completed"),
                "chat_id": selected_chat_id,
                "message_id": message_id,
                "workflow_progress": workflow_result["workflow_progress"],
                "completed_agents": workflow_result["completed_agents"],
                "final_summary": workflow_result["final_summary"],
                "steps": WORKFLOW_STATE["steps"],
                "orchestration_mode": workflow_result.get(
                    "orchestration_mode", "internal"
                ),
                "analysis_scope": self._normalize_analysis_scope(analysis_scope),
                "specialist_responses": workflow_result.get("specialist_responses", {}),
                "raw": {
                    "next_response": next_response,
                    "processing_response": processing_response,
                    "processed_response": processed_response,
                    "workflow_result": workflow_result,
                },
            }
            record_band_debug_response(result)
            update_band_processing_state(
                last_message_status=result["status"],
                last_chat_id=selected_chat_id,
                last_message_id=message_id,
                last_error="",
                last_response=workflow_result["final_summary"],
                last_processed_at=utc_now_iso(),
                orchestration_mode=workflow_result.get("orchestration_mode", "internal"),
            )
            return result if debug else self._compact_workflow_response(result)
        except Exception as exc:
            error = str(exc)
            append_log("band.log", f"Quasar Band workflow failed: {error}")
            failed_response = {}
            if processing_started:
                failed_response = client.mark_message_failed(
                    selected_chat_id, message_id, error
                )
            update_workflow_step(
                WORKFLOW_STATE.get("current_agent", "Final Review Agent"),
                "failed",
                error,
            )
            result = self._record_processing_result(
                success=False,
                status="failed",
                chat_id=selected_chat_id,
                message_id=message_id,
                error=error,
                raw={"next_response": next_response, "failed_response": failed_response},
            )
            return result if debug else self._compact_workflow_response(result)

    def _run_manual_workflow_trigger(
        self,
        selected_chat_id: str,
        debug: bool,
        raw: dict[str, Any],
        analysis_scope: str = "MCX",
    ) -> dict[str, Any]:
        participants = self._extract_data_list(
            self.band_client.get_participants(selected_chat_id)
        )
        registry = BandAgentRegistry(participants)
        user = next(
            (participant for participant in participants if participant.get("type") == "User"),
            {},
        )
        mentions = [self._participant_to_mention(user)] if user else []
        workflow_result = self.run_quasar_delivery_workflow(
            chat_id=selected_chat_id,
            message_id="manual-trigger",
            incoming_content=(
                "Run Quasar specialist review for "
                f"{self._scope_label(analysis_scope)}"
            ),
            mentions=mentions,
            registry=registry,
            analysis_scope=analysis_scope,
        )
        result = {
            "success": workflow_result.get("status", "completed") == "completed",
            "status": workflow_result.get("status", "completed"),
            "chat_id": selected_chat_id,
            "message_id": "manual-trigger",
            "workflow_progress": workflow_result["workflow_progress"],
            "completed_agents": workflow_result["completed_agents"],
            "final_summary": workflow_result["final_summary"],
            "steps": WORKFLOW_STATE["steps"],
            "orchestration_mode": workflow_result.get("orchestration_mode", "internal"),
            "analysis_scope": self._normalize_analysis_scope(analysis_scope),
            "specialist_responses": workflow_result.get("specialist_responses", {}),
            "raw": {
                **raw,
                "workflow_result": workflow_result,
            },
        }
        record_band_debug_response(result)
        update_band_processing_state(
            last_message_status=result["status"],
            last_chat_id=selected_chat_id,
            last_message_id="manual-trigger",
            last_error="",
            last_response=workflow_result["final_summary"],
            last_processed_at=utc_now_iso(),
            orchestration_mode=workflow_result.get("orchestration_mode", "internal"),
        )
        return result if debug else self._compact_workflow_response(result)

    def _extract_data_list(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        data = response.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        if isinstance(data, dict):
            for key in ("messages", "participants", "chats", "items", "results"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    def _latest_message_text(self, messages: list[dict[str, Any]]) -> str:
        if not messages:
            return ""
        latest = messages[-1]
        if not isinstance(latest, dict):
            return ""
        return str(
            latest.get("content")
            or latest.get("message", {}).get("content")
            or latest.get("message_type")
            or latest.get("id")
            or ""
        )

    def _build_mentions(self, participants_response: dict[str, Any]) -> list[dict[str, Any]]:
        participants = self._extract_data_list(participants_response)
        agent_id = self.band_client.agent_id
        mentions = []
        for participant in participants:
            participant_id = str(participant.get("id", ""))
            if not participant_id or participant_id == agent_id:
                continue
            mention = {"id": participant_id}
            if participant.get("handle"):
                mention["handle"] = participant["handle"]
            if participant.get("name"):
                mention["name"] = participant["name"]
            mentions.append(mention)
            break
        return mentions

    def _first_chat_id(self) -> str:
        chats_response = self.band_client.list_chats()
        chats = self._extract_data_list(chats_response)
        if not chats:
            return ""
        return str(chats[0].get("id", ""))

    def _extract_message(self, response: dict[str, Any]) -> dict[str, Any] | None:
        data = response.get("data")
        if data is None:
            return None
        if isinstance(data, dict):
            nested = data.get("data")
            if isinstance(nested, dict):
                return nested
            return data
        return None

    def _build_remote_agent_response(self, incoming_content: str) -> str:
        intent = "workflow coordination"
        lowered = incoming_content.lower()
        if "market" in lowered:
            intent = "market intelligence"
        elif "architecture" in lowered:
            intent = "architecture planning"
        elif "risk" in lowered or "governance" in lowered:
            intent = "risk governance"
        elif "delivery" in lowered or "plan" in lowered:
            intent = "delivery planning"

        return (
            "Quasar remote agent received your message. "
            f"Detected intent: {intent}. "
            "Quasar can provide market intelligence, architecture, governance, "
            "and delivery planning context for the workflow."
        )

    def _run_specialist_orchestration(
        self,
        chat_id: str,
        message_id: str,
        incoming_content: str,
        mentions: list[dict[str, Any]],
        registry: BandAgentRegistry,
        analysis_scope: str = "MCX",
    ) -> dict[str, Any]:
        context = self.build_quasar_context(analysis_scope=analysis_scope)
        context_summary = self.summarize_market_context_for_band(context)
        scope_label = context.get("scope_label", self._scope_label(analysis_scope))
        prompts = {
            "Requirement Agent": (
                "Requirement Specialist: define the market question being evaluated "
                "for the selected scope only. Use Quasar intelligence artifacts first: "
                "market regime, scenario engine, timeframe hierarchy, market memory, "
                "persistence, validation conditions, and governance evidence. Avoid "
                "restating raw labels unless they materially change the question.\n"
                f"Selected scope: {scope_label}\n"
                f"User request: {incoming_content}\n\n"
                f"{context_summary}"
            ),
            "Market Intelligence Agent": (
                "Market Intelligence Specialist: produce a dominant market thesis, "
                "an alternative thesis, and the supporting/contradicting evidence. "
                "Use regime, scenario engine, timeframe hierarchy, market memory, "
                "persistence, validation conditions, and governance evidence before "
                "raw labels. Do not discuss other markets.\n"
                f"Selected scope: {scope_label}\n\n"
                f"{context_summary}"
            ),
            "Architecture Agent": (
                "System Readiness Specialist: assess whether Quasar intelligence is "
                "fresh and usable for institutional decision support. Review session "
                "state, feed/source quality, evidence completeness, hierarchy/scenario "
                "availability, and governance evidence. Avoid repeating labels.\n"
                f"Selected scope: {scope_label}\n\n"
                f"{context_summary}"
            ),
            "Risk Governance Agent": (
                "Risk Governance Specialist: assess confidence risk, conflict risk, "
                "and validation risk for the selected instrument only. Tie guardrails "
                "to regime, scenario/hierarchy disagreement, market memory/persistence, "
                "validation conditions, and governance evidence. Do not provide "
                "directional execution instructions.\n"
                f"Selected scope: {scope_label}\n\n"
                f"{context_summary}"
            ),
            "Delivery Planning Agent": (
                "Delivery Planning Specialist: produce a validation roadmap for the "
                "selected instrument only. Explain what evidence is required next, "
                "which scenario must validate or invalidate, and how hierarchy, "
                "persistence, memory, and governance evidence should be refreshed. "
                "No execution guidance.\n"
                f"Selected scope: {scope_label}\n\n"
                f"{context_summary}"
            ),
            "Final Review Agent": (
                "Final Review Specialist: produce an institutional market briefing "
                "for the selected instrument only. Include executive assessment, "
                "dominant hypothesis, alternative hypothesis, and why the current "
                "decision state exists. Prefer regime, scenario, hierarchy, memory, "
                "persistence, validation, and governance evidence over raw label lists.\n\n"
                f"Selected scope: {scope_label}\n"
                f"{context_summary}"
            ),
        }
        specialist_responses: dict[str, str] = {}
        raw_specialist_responses: list[dict[str, Any]] = []
        for agent in WORKFLOW_STEPS:
            registration = registry.by_agent_name(agent)
            if not registration:
                raise RuntimeError(f"Missing specialist Band agent for {agent}")

            update_workflow_step(
                agent,
                "running",
                f"{agent} invoked over Band; waiting for response.",
                prompt_sent=prompts[agent],
            )
            append_log("band.log", f"{agent} specialist orchestration started")
            prompt_sent_at = utc_now_iso()
            specialist_message = self._send_specialist_message(
                chat_id=chat_id,
                registration=registration,
                content=prompts[agent],
            )
            prompt_message_id = self._extract_message_id_from_response(
                specialist_message
            )
            prompt_inserted_at = self._extract_message_timestamp_from_response(
                specialist_message
            )
            if prompt_inserted_at:
                prompt_sent_at = prompt_inserted_at
            append_log(
                "band.log",
                (
                    f"{agent} prompt metadata "
                    f"participant_id={registration.participant_id} "
                    f"handle={registration.handle or registration.expected_handle} "
                    f"prompt_message_id={prompt_message_id or 'unknown'} "
                    f"prompt_sent_at={prompt_sent_at}"
                ),
            )
            if specialist_message.get("status") == "error":
                error = specialist_message.get(
                    "message", f"Unable to message {agent} over Band"
                )
                specialist_brief = {
                    **build_specialist_brief(agent, context),
                    "response_source": "quasar_brief_fallback",
                    "fallback_reason": error,
                }
                response_text = format_specialist_brief_text(specialist_brief)
                response_key = self._specialist_response_key(agent)
                specialist_responses[response_key] = response_text
                raw_specialist_responses.append(
                    {
                        "agent": agent,
                        "request": specialist_message,
                        "response": {},
                        "status": "completed",
                        "specialist_brief": specialist_brief,
                        "response_source": "quasar_brief_fallback",
                        "fallback_reason": error,
                    }
                )
                update_workflow_step(
                    agent,
                    "completed",
                    self._response_preview(response_text),
                    prompt_sent=prompts[agent],
                    response_text=response_text,
                    response_received=True,
                    specialist_brief=specialist_brief,
                    response_source="quasar_brief_fallback",
                )
                self._persist_specialist_response(
                    agent=agent,
                    context=context,
                    finding=str(specialist_brief.get("state") or error),
                    summary=response_text,
                    raw_response_payload=raw_specialist_responses[-1],
                )
                append_log(
                    "band.log",
                    f"{agent} specialist message failed; Quasar brief fallback completed",
                )
                continue

            event_response = self.band_client.post_chat_event(
                chat_id=chat_id,
                event_type="task",
                payload={
                    "content": f"{agent} requested via Band specialist",
                    "agent": agent,
                    "incoming_message_id": message_id,
                    "specialist_message_id": self._extract_event_id(specialist_message),
                    "context": context if agent == "Market Intelligence Agent" else {},
                },
            )
            specialist_response = self._wait_for_specialist_response(
                chat_id=chat_id,
                registration=registration,
                prompt_message_id=prompt_message_id,
                prompt_sent_at=prompt_sent_at,
            )
            response_message = (
                specialist_response.get("message")
                if isinstance(specialist_response, dict)
                else None
            )
            response_text = _clean_band_text(
                self._latest_message_text([response_message])
            )
            response_received = bool(specialist_response and response_text)
            response_key = self._specialist_response_key(agent)
            specialist_brief = build_specialist_brief(agent, context)
            response_source = "band_review"
            original_response_text = response_text
            if is_raw_label_repetition(response_text):
                response_text = format_specialist_brief_text(specialist_brief)
                response_source = "quasar_brief"
                response_received = True
            specialist_brief = {
                **specialist_brief,
                "response_source": response_source,
            }
            specialist_responses[response_key] = response_text
            raw_specialist_responses.append(
                {
                    "agent": agent,
                    "request": {
                        "participant_id": registration.participant_id,
                        "handle": registration.handle or registration.expected_handle,
                        "prompt_message_id": prompt_message_id,
                        "prompt_sent_at": prompt_sent_at,
                    },
                    "response": specialist_response,
                    "original_response_text": original_response_text,
                    "specialist_brief": specialist_brief,
                    "response_source": response_source,
                    "status": "completed" if response_received else "failed",
                }
            )
            if response_received:
                summary = self._response_preview(response_text)
                update_workflow_step(
                    agent,
                    "completed",
                    summary,
                    self._extract_event_id(event_response),
                    prompt_sent=prompts[agent],
                    response_text=response_text,
                    response_received=True,
                    specialist_brief=specialist_brief,
                    response_source=response_source,
                )
                self._persist_specialist_response(
                    agent=agent,
                    context=context,
                    finding=str(specialist_brief.get("state") or summary),
                    summary=response_text,
                    raw_response_payload=raw_specialist_responses[-1],
                )
                append_log("band.log", f"{agent} specialist orchestration completed")
            else:
                scanned_count = (
                    specialist_response.get("scanned_message_count", 0)
                    if isinstance(specialist_response, dict)
                    else 0
                )
                summary = (
                    "No message from expected sender after prompt timestamp "
                    f"(scanned {scanned_count})"
                )
                update_workflow_step(
                    agent,
                    "failed",
                    summary,
                    self._extract_event_id(event_response),
                    prompt_sent=prompts[agent],
                    response_text="",
                    response_received=False,
                )
                append_log("band.log", f"{agent} specialist orchestration timeout")

        completed_agents = sum(
            1 for step in WORKFLOW_STATE["steps"] if step.get("status") == "completed"
        )
        failed_agents = [
            step.get("agent", "")
            for step in WORKFLOW_STATE["steps"]
            if step.get("status") == "failed"
        ]
        final_summary = self._build_specialist_final_summary(
            specialist_responses, context
        )
        mention_prefix = self._mention_prefix(mentions[0]) if mentions else "@participant"
        final_response = self.band_client.send_chat_message(
            chat_id=chat_id,
            content=f"{mention_prefix} {final_summary}",
            mentions=mentions,
        )
        if final_response.get("status") == "error":
            append_log(
                "band.log",
                "Final Band response failed; retaining local final specialist summary",
            )
            final_response = {
                **final_response,
                "status": "local_fallback",
                "message": final_response.get("message", "Final Band response failed"),
            }

        terminal_status = "completed" if not failed_agents else "failed"
        WORKFLOW_STATE.update(
            {
                "current_agent": "Completed" if terminal_status == "completed" else "Failed",
                "progress": int(completed_agents / len(WORKFLOW_STEPS) * 100),
                "final_summary": final_summary,
                "status": terminal_status,
                "updated_at": utc_now_iso(),
            }
        )
        self._persist_final_review_response(
            context=context,
            final_summary=final_summary,
            final_response=final_response,
        )
        append_log("band.log", "Quasar specialist Band workflow completed")
        return {
            "status": terminal_status,
            "workflow_progress": WORKFLOW_STATE["progress"],
            "completed_agents": completed_agents,
            "final_summary": final_summary,
            "steps": WORKFLOW_STATE["steps"],
            "context": context,
            "event_responses": [],
            "final_response": final_response,
            "specialist_responses": specialist_responses,
            "raw_specialist_responses": raw_specialist_responses,
            "failed_agents": failed_agents,
            "orchestration_mode": "specialist",
        }

    def _persist_specialist_response(
        self,
        *,
        agent: str,
        context: dict[str, Any],
        finding: str,
        summary: str,
        raw_response_payload: dict[str, Any],
    ) -> None:
        try:
            market, instrument = self._persistence_market(context)
            evidence_payload = build_governance_evidence(get_workflow_details(), context)
            finding_evidence = next(
                (
                    item
                    for item in evidence_payload.get("specialist_findings", [])
                    if item.get("agent") == agent
                ),
                {},
            )
            save_specialist_response(
                workflow_run_id=WORKFLOW_STATE.get("workflow_id", ""),
                market=market,
                instrument=instrument,
                specialist_name=agent,
                finding=finding,
                summary=summary,
                confidence=self._persistence_confidence(context),
                evidence=finding_evidence.get("evidence", []),
                warnings=finding_evidence.get("missing_evidence_warnings", []),
                raw_response_payload=raw_response_payload,
            )
            append_log("band.log", f"{agent} specialist response persisted")
        except Exception as exc:
            append_log("band.log", f"{agent} specialist response persistence skipped: {exc}")

    def _persist_final_review_response(
        self,
        *,
        context: dict[str, Any],
        final_summary: str,
        final_response: dict[str, Any],
    ) -> None:
        try:
            market, instrument = self._persistence_market(context)
            evidence_payload = build_governance_evidence(get_workflow_details(), context)
            final_finding = next(
                (
                    item
                    for item in evidence_payload.get("specialist_findings", [])
                    if item.get("agent") == "Final Review Agent"
                ),
                {},
            )
            save_final_review_response(
                workflow_run_id=WORKFLOW_STATE.get("workflow_id", ""),
                market=market,
                instrument=instrument,
                finding=str(final_finding.get("finding") or self._decision_state(context)),
                summary=final_summary,
                confidence=self._persistence_confidence(context),
                evidence=evidence_payload,
                warnings=evidence_payload.get("missing_evidence_warnings", []),
                raw_response_payload={
                    **final_response,
                    "specialist_brief": {
                        **build_specialist_brief("Final Review Agent", context),
                        "response_source": "quasar_brief",
                    },
                    "response_source": "quasar_brief",
                },
            )
            append_log("band.log", "Final specialist review response persisted")
        except Exception as exc:
            append_log("band.log", f"Final specialist review persistence skipped: {exc}")

    def _persistence_market(self, context: dict[str, Any]) -> tuple[str, str]:
        scope = self._normalize_analysis_scope(context.get("analysis_scope", "MCX"))
        if scope == "FOREX":
            return "FOREX", str((context.get("forex") or {}).get("instrument") or "XAUUSD")
        return "MCX", str((context.get("mcx") or {}).get("instrument") or "NATURALGAS")

    def _persistence_confidence(self, context: dict[str, Any]) -> int:
        try:
            return int(
                round(
                    float(
                        (context.get("multi_timeframe") or {}).get(
                            "structure_confidence", 0
                        )
                        or 0
                    )
                    * 100
                )
            )
        except (TypeError, ValueError):
            return 0

    def _send_specialist_message(
        self,
        chat_id: str,
        registration: BandAgentRegistration,
        content: str,
    ) -> dict[str, Any]:
        mention = {
            "id": registration.participant_id,
            "handle": registration.handle,
            "name": registration.agent_name,
        }
        prefix = self._mention_prefix(mention)
        append_log("band.log", f"Sending specialist message to {registration.agent_name}")
        return self.band_client.send_chat_message(
            chat_id=chat_id,
            content=f"{prefix} {content}",
            mentions=[mention],
        )

    def _wait_for_specialist_response(
        self,
        chat_id: str,
        registration: BandAgentRegistration,
        prompt_message_id: str,
        prompt_sent_at: str,
        max_wait_seconds: float = 15.0,
        delay_seconds: float = 2.0,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + max_wait_seconds
        last_scanned_count = 0
        while time.monotonic() < deadline:
            time.sleep(delay_seconds)
            self._process_expected_specialist(registration.agent_name, chat_id)
            messages = self._fetch_chat_messages_for_scan(chat_id)
            last_scanned_count = len(messages)
            append_log(
                "band.log",
                (
                    f"Specialist response scan expected={registration.agent_name} "
                    f"expected_sender_id={registration.participant_id} "
                    f"messages_scanned={last_scanned_count}"
                ),
            )
            for message in sorted(
                messages,
                key=lambda item: self._message_sort_timestamp(item),
                reverse=True,
            ):
                message_id = self._message_id(message)
                if not message_id or message_id == prompt_message_id:
                    continue
                content = self._message_text(message)
                if not self._message_is_text(message) or not content.strip():
                    continue
                if not self._message_from_registration(message, registration):
                    continue
                if not self._message_after_prompt(message, prompt_sent_at):
                    continue

                clean_response = _clean_band_text(content)
                if not clean_response:
                    continue

                append_log(
                    "band.log",
                    (
                        f"Specialist response scan matched expected={registration.agent_name} "
                        f"expected_sender_id={registration.participant_id} "
                        f"messages_scanned={last_scanned_count} "
                        f"matched_message_id={message_id} response_captured=true"
                    ),
                )
                return {
                    "message": message,
                    "matched_message_id": message_id,
                    "scanned_message_count": last_scanned_count,
                    "response_captured": True,
                }
        append_log(
            "band.log",
            (
                f"Specialist response scan no match expected={registration.agent_name} "
                f"expected_sender_id={registration.participant_id} "
                f"messages_scanned={last_scanned_count} matched_message_id=none "
                "response_captured=false reason=No message from expected sender after prompt timestamp"
            ),
        )
        return {
            "message": None,
            "matched_message_id": "",
            "scanned_message_count": last_scanned_count,
            "response_captured": False,
            "reason": "No message from expected sender after prompt timestamp",
        }

    def _process_expected_specialist(self, agent_name: str, chat_id: str) -> None:
        try:
            from app.agents.specialist_service import SpecialistProcessorService

            processor = SpecialistProcessorService()
            for _ in range(5):
                result = processor.process_agent(agent_name, chat_id=chat_id)
                if result.get("status") == "processed":
                    append_log(
                        "band.log",
                        f"{agent_name} specialist auto-processed pending message",
                    )
                    continue
                if result.get("status") in {"no_messages", "no_message"}:
                    break
                break
        except Exception as exc:
            append_log("band.log", f"{agent_name} specialist auto-process skipped: {exc}")

    def _fetch_chat_messages_for_scan(
        self, chat_id: str, limit: int = 100, max_pages: int = 5
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        cursor = None
        for _ in range(max_pages):
            response = self.band_client.get_messages(
                chat_id=chat_id, status="all", cursor=cursor, limit=limit
            )
            messages.extend(self._extract_data_list(response))
            metadata = response.get("metadata")
            if not isinstance(metadata, dict) and isinstance(response.get("data"), dict):
                metadata = response["data"].get("metadata")
            if not isinstance(metadata, dict):
                break
            cursor = metadata.get("next_cursor")
            if not cursor or not metadata.get("has_more"):
                break
        return messages

    def _recent_message_ids(self, chat_id: str) -> set[str]:
        messages_response = self.band_client.get_chat_messages(
            chat_id=chat_id, status="all", limit=50
        )
        messages = self._extract_data_list(messages_response)
        return {message_id for message_id in (self._message_id(item) for item in messages) if message_id}

    def _message_id(self, message: dict[str, Any]) -> str:
        return str(message.get("id") or message.get("message", {}).get("id") or "")

    def _clean_candle(self, candle: dict[str, Any]) -> dict[str, float]:
        return {
            "open": float(candle.get("open") or 0),
            "high": float(candle.get("high") or 0),
            "low": float(candle.get("low") or 0),
            "close": float(candle.get("close") or 0),
            "volume": float(candle.get("volume") or 0),
        }

    def _top_context_labels(
        self, labels: list[dict[str, Any]], limit: int = 3
    ) -> list[dict[str, Any]]:
        deduped: dict[tuple[str, str], dict[str, Any]] = {}
        for label in labels:
            label_name = str(label.get("label") or label.get("label_type") or "")
            direction = str(label.get("direction") or "NEUTRAL")
            confidence = float(label.get("confidence") or 0)
            key = (label_name, direction)
            if key not in deduped or confidence > float(deduped[key]["confidence"]):
                deduped[key] = {
                    "label": label_name,
                    "direction": direction,
                    "confidence": confidence,
                }
        return sorted(
            deduped.values(),
            key=lambda item: float(item.get("confidence") or 0),
            reverse=True,
        )[:limit]

    def _dominant_bias(self, labels: list[dict[str, Any]]) -> str:
        bullish = sum(
            float(label.get("confidence") or 0)
            for label in labels
            if str(label.get("direction", "")).upper() == "BULLISH"
        )
        bearish = sum(
            float(label.get("confidence") or 0)
            for label in labels
            if str(label.get("direction", "")).upper() == "BEARISH"
        )
        if bullish and bearish:
            if bullish > bearish * 1.2:
                return "MIXED_BULLISH"
            if bearish > bullish * 1.2:
                return "MIXED_BEARISH"
            return "MIXED_CONFLICTED"
        if bullish:
            return "BULLISH"
        if bearish:
            return "BEARISH"
        return "NEUTRAL"

    def _data_age(self, timestamp: str) -> str:
        ts = self._parse_band_timestamp(str(timestamp or ""))
        if not ts:
            return "unknown"
        seconds = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        return f"{hours}h {minutes % 60}m"

    def _market_session(self, market_type: str) -> str:
        now = datetime.now(timezone.utc)
        minutes = now.hour * 60 + now.minute
        if market_type == "MCX":
            return "MCX Active" if 210 <= minutes <= 1080 else "MCX Closed"
        if now.weekday() >= 5:
            return "Forex Off Hours"
        if 0 <= minutes < 420:
            return "Asia Session"
        if 420 <= minutes < 720:
            return "London Session"
        if 720 <= minutes < 960:
            return "Session Overlap"
        if 960 <= minutes < 1260:
            return "New York Session"
        return "Forex Off Hours"

    def _message_text(self, message: dict[str, Any] | None) -> str:
        if not isinstance(message, dict):
            return ""
        return str(
            message.get("content")
            or message.get("message", {}).get("content")
            or ""
        )

    def _message_is_text(self, message: dict[str, Any]) -> bool:
        message_type = str(
            message.get("message_type")
            or message.get("message", {}).get("message_type")
            or "text"
        ).lower()
        return message_type == "text"

    def _message_sort_timestamp(self, message: dict[str, Any]) -> str:
        return str(
            message.get("inserted_at")
            or message.get("updated_at")
            or message.get("message", {}).get("inserted_at")
            or message.get("message", {}).get("updated_at")
            or ""
        )

    def _message_after_prompt(self, message: dict[str, Any], prompt_sent_at: str) -> bool:
        prompt_dt = self._parse_band_timestamp(prompt_sent_at)
        if not prompt_dt:
            return True

        inserted_dt = self._parse_band_timestamp(
            str(
                message.get("inserted_at")
                or message.get("message", {}).get("inserted_at")
                or ""
            )
        )
        if inserted_dt and inserted_dt >= prompt_dt:
            return True

        # Band can expose specialist replies with an older inserted_at while the
        # coordinator-visible delivery/update timestamp is current.
        fallback_dt = self._parse_band_timestamp(
            str(
                message.get("updated_at")
                or message.get("message", {}).get("updated_at")
                or self._message_delivery_timestamp(message)
                or ""
            )
        )
        return bool(fallback_dt and fallback_dt >= prompt_dt)

    def _message_delivery_timestamp(self, message: dict[str, Any]) -> str:
        delivery_status = (
            message.get("metadata", {}).get("delivery_status", {})
            if isinstance(message.get("metadata"), dict)
            else {}
        )
        timestamps: list[str] = []
        for status in delivery_status.values():
            if not isinstance(status, dict):
                continue
            for key in ("processed_at", "delivered_at"):
                if status.get(key):
                    timestamps.append(str(status[key]))
            for attempt in status.get("attempts", []):
                if not isinstance(attempt, dict):
                    continue
                for key in ("completed_at", "started_at"):
                    if attempt.get(key):
                        timestamps.append(str(attempt[key]))
        return max(timestamps) if timestamps else ""

    def _parse_band_timestamp(self, value: str) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _extract_message_id_from_response(self, response: dict[str, Any]) -> str:
        message = self._extract_message(response)
        if message:
            return self._message_id(message)
        data = response.get("data")
        if isinstance(data, dict):
            return str(data.get("id") or data.get("message", {}).get("id") or "")
        return ""

    def _extract_message_timestamp_from_response(self, response: dict[str, Any]) -> str:
        message = self._extract_message(response)
        if not message:
            data = response.get("data")
            message = data if isinstance(data, dict) else {}
        return str(
            message.get("inserted_at")
            or message.get("updated_at")
            or message.get("message", {}).get("inserted_at")
            or message.get("message", {}).get("updated_at")
            or ""
        )

    def _message_from_registration(
        self, message: dict[str, Any], registration: BandAgentRegistration
    ) -> bool:
        sender_id = str(
            message.get("sender_id")
            or message.get("sender", {}).get("id")
            or message.get("author", {}).get("id")
            or message.get("participant_id")
            or ""
        )
        sender_handle = str(
            message.get("sender_handle")
            or message.get("sender", {}).get("handle")
            or message.get("author", {}).get("handle")
            or message.get("handle")
            or ""
        ).lower()
        sender_name = str(
            message.get("sender_name")
            or message.get("sender", {}).get("name")
            or message.get("author", {}).get("name")
            or message.get("name")
            or ""
        ).lower()
        mention_values = []
        metadata = message.get("metadata", {})
        if isinstance(metadata, dict):
            mentions = metadata.get("mentions", [])
            if isinstance(mentions, list):
                for mention in mentions:
                    if not isinstance(mention, dict):
                        continue
                    mention_values.extend(
                        [
                            str(mention.get("id", "")),
                            str(mention.get("handle", "")),
                            str(mention.get("name", "")),
                        ]
                    )
        expected_handle = registration.expected_handle.lower()
        actual_handle = registration.handle.lower()
        expected_sender_name = registration.agent_name.lower()
        normalized_sender_name = self._normalize_agent_match_text(sender_name)
        normalized_expected_name = self._normalize_agent_match_text(expected_sender_name)
        normalized_expected_handle = self._normalize_agent_match_text(expected_handle)
        normalized_actual_handle = self._normalize_agent_match_text(actual_handle)
        normalized_mentions = " ".join(
            self._normalize_agent_match_text(value) for value in mention_values
        )
        return bool(
            (sender_id and sender_id == registration.participant_id)
            or (actual_handle and actual_handle in sender_handle)
            or (expected_handle and expected_handle in sender_handle)
            or (expected_handle and expected_handle in sender_name)
            or (
                normalized_expected_name
                and normalized_expected_name in normalized_sender_name
            )
            or (
                normalized_expected_handle
                and normalized_expected_handle in normalized_sender_name
            )
            or (
                normalized_actual_handle
                and normalized_actual_handle in normalized_sender_name
            )
            or (
                registration.participant_id
                and registration.participant_id in normalized_mentions
            )
        )

    def _normalize_agent_match_text(self, value: str) -> str:
        text = str(value or "").lower()
        text = text.replace("quasar/", "")
        text = text.replace("agent", "")
        text = re.sub(r"[^a-z0-9]+", "", text)
        return text

    def _specialist_response_key(self, agent: str) -> str:
        return {
            "Requirement Agent": "requirement",
            "Market Intelligence Agent": "market_intel",
            "Architecture Agent": "architecture",
            "Risk Governance Agent": "risk",
            "Delivery Planning Agent": "delivery",
            "Final Review Agent": "review",
        }.get(agent, agent.lower().replace(" ", "_"))

    def _response_preview(self, response_text: str, max_chars: int = 180) -> str:
        return _clean_preview(response_text, max_chars=max_chars)

    def _market_context_summary(self, context: dict[str, Any]) -> str:
        mcx = context.get("mcx", {})
        forex = context.get("forex", {})
        return (
            f"Timeframe {context.get('timeframe', '1m')}; "
            f"MCX {mcx.get('instrument', 'NATURALGAS')} labels "
            f"{len(mcx.get('labels', []))}; "
            f"Forex {forex.get('instrument', 'XAUUSD')} labels "
            f"{len(forex.get('labels', []))}; "
            f"{context.get('safety', '')}"
        )

    def _build_specialist_final_summary(
        self, specialist_responses: dict[str, str], context: dict[str, Any] | None = None
    ) -> str:
        context = context or {}
        decision_state = self._decision_state(context)
        market = self._selected_market_context(context)
        scope_label = context.get("scope_label") or self._scope_label(
            context.get("analysis_scope", "MCX")
        )
        evidence = self._market_evidence_line(market)
        confidence = self._confidence_line(context)
        next_validation = self._next_validation_step(decision_state, context)
        mtf = context.get("multi_timeframe", {})
        mtf_decision = mtf.get("decision", {})
        mtf_reason = mtf_decision.get("reason", "")
        regime = mtf.get("regime", "")
        narrative = mtf.get("narrative", {})
        scenarios = mtf.get("scenarios") or {}
        primary_scenario = scenarios.get("primary_scenario") or {}
        secondary_scenario = scenarios.get("secondary_scenario") or {}
        hierarchy = mtf.get("timeframe_hierarchy") or {}
        memory = mtf.get("memory") or {}
        evolution = mtf.get("evolution") or {}
        dominant_hypothesis = (
            f"{primary_scenario.get('name', 'No clear scenario')} "
            f"({primary_scenario.get('probability', 0)}%)"
        )
        alternative_hypothesis = (
            f"{secondary_scenario.get('name', 'Wait / No Clear Scenario')} "
            f"({secondary_scenario.get('probability', 0)}%)"
        )
        decision_basis = mtf_reason or narrative.get(
            "summary",
            "Decision derived from selected market intelligence artifacts.",
        )
        if narrative.get("summary"):
            evidence = narrative["summary"]
        lines = [
            f"Quasar institutional market briefing for {scope_label}.",
            "",
            f"Market Regime: {str(regime).replace('_', ' ').title() if regime else 'Unavailable'}",
            f"Decision State: {decision_state}",
            "Executive Assessment:",
            str(decision_basis),
            "Dominant Hypothesis:",
            dominant_hypothesis,
            "Alternative Hypothesis:",
            alternative_hypothesis,
            "Intelligence Evidence:",
            f"- {scope_label}: {evidence}",
            f"- Hierarchy: {hierarchy.get('dominant_context', 'Unknown')}; conflict {hierarchy.get('hierarchy_conflict', 'Unknown')}",
            f"- Persistence: {memory.get('status', 'unknown')}; {evolution.get('summary', 'evolution unavailable')}",
            "Confidence:",
            confidence,
            "Next Validation:",
            next_validation,
            "Specialist Notes:",
        ]
        labels = [
            ("requirement", "Requirement"),
            ("market_intel", "Market Intelligence"),
            ("architecture", "System Readiness"),
            ("risk", "Risk Governance"),
            ("delivery", "Delivery Planning"),
            ("review", "Final Review"),
        ]
        for key, label in labels:
            response = specialist_responses.get(key, "")
            lines.append(f"- {label}: {self._response_preview(response, 120) if response else 'No response captured'}")
        lines.extend(
            [
                "",
                governance_evidence_references_text(
                    build_governance_evidence(get_workflow_details(), context)
                ),
                "Safety:",
                "Advisory-only market structure intelligence. Execution disabled. No directional calls.",
            ]
        )
        return "\n".join(lines)

    def _decision_state(self, context: dict[str, Any]) -> str:
        mtf_decision = context.get("multi_timeframe", {}).get("decision", {})
        if mtf_decision.get("state"):
            return str(mtf_decision["state"])
        bias = str(self._selected_market_context(context).get("dominant_bias", ""))
        if "CONFLICTED" in bias:
            return "CONFLICTED"
        if "MIXED" in bias:
            return "WATCH"
        if bias in {"BULLISH", "BEARISH"}:
            return "VALIDATE"
        return "WAIT"

    def _market_evidence_line(self, market: dict[str, Any]) -> str:
        # Prefer the multi-timeframe narrative path when available; this fallback is
        # retained for internal/mock mode.
        labels = market.get("labels", [])
        label_text = ", ".join(
            f"{label.get('label')} {int(round(float(label.get('confidence') or 0) * 100))}%"
            for label in labels[:3]
        )
        if not label_text:
            label_text = "no current labels"
        return (
            f"{market.get('dominant_bias', 'NEUTRAL').replace('_', ' ').title()}; "
            f"{label_text}; {market.get('session', 'Unknown')}; "
            f"data age {market.get('data_age', 'unknown')}"
        )

    def _confidence_line(self, context: dict[str, Any]) -> str:
        mtf = context.get("multi_timeframe", {})
        decision = mtf.get("decision", {})
        alignment = mtf.get("alignment", {})
        metrics = mtf.get("metrics", {})
        if metrics:
            structure_confidence = int(round(float(metrics.get("structure_confidence") or 0) * 100))
            alignment_score = int(round(float(metrics.get("alignment_score") or alignment.get("alignment_score") or 0) * 100))
            decision_strength = int(round(float(metrics.get("decision_strength") or decision.get("decision_strength") or 0) * 100))
            return (
                f"Structure Confidence {structure_confidence}%; "
                f"Directional Alignment {alignment_score}%; "
                f"Decision Strength {decision_strength}%."
            )
        labels = self._selected_market_context(context).get("labels", [])
        if not labels:
            return "No confidence labels available."
        avg_confidence = sum(float(label.get("confidence") or 0) for label in labels) / len(labels)
        return f"Average top-label confidence {int(round(avg_confidence * 100))}% for selected scope."

    def _next_validation_step(self, decision_state: str, context: dict[str, Any]) -> str:
        mtf_next_validation = (
            context.get("multi_timeframe", {})
            .get("decision", {})
            .get("next_validation")
        )
        if mtf_next_validation:
            return str(mtf_next_validation)
        if decision_state == "CONFLICTED":
            return "Wait for clearer structure before changing decision state."
        if decision_state == "VALIDATE":
            return "Validate against higher timeframe structure and next candle close."
        if decision_state == "WATCH":
            return "Watch whether the next candle confirms or rejects the current structure."
        return "Wait for fresh structure labels with stronger confidence."

    def _selected_market_context(self, context: dict[str, Any]) -> dict[str, Any]:
        scope = self._normalize_analysis_scope(context.get("analysis_scope", "MCX"))
        return context.get("forex", {}) if scope == "FOREX" else context.get("mcx", {})

    def _normalize_analysis_scope(self, analysis_scope: Any) -> str:
        scope = str(analysis_scope or "MCX").upper()
        if scope in {"FOREX", "FX", "XAUUSD"}:
            return "FOREX"
        return "MCX"

    def _scope_label(self, analysis_scope: Any) -> str:
        return (
            "Forex XAUUSD"
            if self._normalize_analysis_scope(analysis_scope) == "FOREX"
            else "MCX NATURALGAS"
        )

    def _build_final_summary(self) -> str:
        return (
            "Quasar delivery workflow completed.\n"
            "Summary:\n"
            "- Requirement analyzed\n"
            "- MCX/Forex market intelligence reviewed\n"
            "- Architecture plan prepared\n"
            "- Governance controls validated\n"
            "- Delivery roadmap generated\n"
            "Safety:\n"
            "Advisory-only market structure intelligence. Execution disabled. No directional calls."
        )

    def _extract_event_id(self, response: dict[str, Any]) -> str | None:
        data = response.get("data")
        if isinstance(data, dict) and data.get("id"):
            return str(data["id"])
        return None

    def _build_response_mentions(
        self, chat_id: str, message: dict[str, Any]
    ) -> list[dict[str, Any]]:
        sender_id = str(message.get("sender_id", ""))
        participants_response = self.band_client.get_participants(chat_id)
        participants = self._extract_data_list(participants_response)
        if sender_id and sender_id != self.band_client.agent_id:
            for participant in participants:
                if str(participant.get("id", "")) == sender_id:
                    return [self._participant_to_mention(participant)]
            return [{"id": sender_id}]
        return self._build_mentions(participants_response)

    def _participant_to_mention(self, participant: dict[str, Any]) -> dict[str, Any]:
        mention = {"id": str(participant.get("id", ""))}
        if participant.get("handle"):
            mention["handle"] = participant["handle"]
        if participant.get("name"):
            mention["name"] = participant["name"]
        return mention

    def _mention_prefix(self, mention: dict[str, Any]) -> str:
        if mention.get("handle"):
            return f"@{mention['handle']}"
        if mention.get("name"):
            return f"@{str(mention['name']).replace(' ', '')}"
        return "@participant"

    def _record_processing_result(
        self,
        success: bool,
        status: str,
        chat_id: str = "",
        message_id: str = "",
        response_sent: bool = False,
        latest_message: str = "",
        error: str = "",
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = {
            "success": success,
            "status": status,
            "chat_id": chat_id,
            "message_id": message_id,
            "response_sent": response_sent,
            "latest_message": latest_message,
            "error": error,
            "raw": raw or {},
            "processed_at": utc_now_iso(),
        }
        record_band_debug_response(result)
        update_band_processing_state(
            last_message_status=status,
            last_chat_id=chat_id,
            last_message_id=message_id,
            last_error=error,
            last_response=latest_message,
            last_processed_at=result["processed_at"],
        )
        return result

    def _compact_workflow_response(self, result: dict[str, Any]) -> dict[str, Any]:
        compact = {
            "success": result.get("success", False),
            "status": result.get("status", "unknown"),
            "chat_id": result.get("chat_id", ""),
            "message_id": result.get("message_id", ""),
            "workflow_progress": result.get("workflow_progress", WORKFLOW_STATE["progress"]),
            "completed_agents": result.get(
                "completed_agents",
                sum(
                    1
                    for step in WORKFLOW_STATE["steps"]
                    if step.get("status") == "completed"
                ),
            ),
            "final_summary": result.get("final_summary", ""),
            "steps": self._compact_steps(result.get("steps") or WORKFLOW_STATE["steps"]),
            "orchestration_mode": result.get(
                "orchestration_mode",
                get_band_processing_state().get("orchestration_mode", "internal"),
            ),
            "analysis_scope": result.get(
                "analysis_scope", WORKFLOW_STATE.get("analysis_scope", "MCX")
            ),
        }
        if result.get("specialist_responses"):
            compact["specialist_responses"] = result["specialist_responses"]
        return compact

    def _compact_steps(self, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact_steps = []
        for step in steps:
            compact_step = {
                "agent": step.get("agent", ""),
                "status": step.get("status", ""),
                "summary": step.get("summary", ""),
                "prompt_sent": step.get("prompt_sent", ""),
                "response_text": step.get("response_text", ""),
                "response_preview": step.get("response_preview", ""),
                "response_received": step.get("response_received", False),
                "specialist_brief": step.get("specialist_brief", {}),
                "response_source": step.get("response_source", ""),
                "started_at": step.get("started_at", ""),
                "completed_at": step.get("completed_at", ""),
                "duration_seconds": step.get("duration_seconds"),
                "updated_at": step.get("updated_at", ""),
            }
            if step.get("band_event_id"):
                compact_step["band_event_id"] = step["band_event_id"]
            compact_steps.append(compact_step)
        return compact_steps


class BandWorkflowService(WorkflowService):
    pass
