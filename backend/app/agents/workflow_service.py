import time
from typing import Any

from app.agents.band_client import BandClient, record_band_debug_response, utc_now_iso
from app.data.ingestion_service import append_log


WORKFLOW_AGENT_SEQUENCE = [
    "Requirement Agent",
    "Market Intelligence Agent",
    "Architecture Agent",
    "Risk Governance Agent",
    "Delivery Planning Agent",
    "Final Review Agent",
]


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

    def _extract_data_list(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        data = response.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        return []

    def _latest_message_text(self, messages: list[dict[str, Any]]) -> str:
        if not messages:
            return ""
        latest = messages[-1]
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


class BandWorkflowService(WorkflowService):
    pass
