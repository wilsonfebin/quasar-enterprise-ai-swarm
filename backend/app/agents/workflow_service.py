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

LAST_BAND_PROCESSING_STATE: dict[str, Any] = {
    "last_message_status": "not_run",
    "last_chat_id": "",
    "last_message_id": "",
    "last_error": "",
    "last_response": "",
    "last_processed_at": "",
}


def get_band_processing_state() -> dict[str, Any]:
    return LAST_BAND_PROCESSING_STATE


def update_band_processing_state(**kwargs) -> dict[str, Any]:
    LAST_BAND_PROCESSING_STATE.update(kwargs)
    return LAST_BAND_PROCESSING_STATE


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


class BandWorkflowService(WorkflowService):
    pass
