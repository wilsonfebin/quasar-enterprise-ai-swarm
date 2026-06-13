import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.data.ingestion_service import append_log

# Band Agent API endpoints discovered from https://docs.band.ai/api/agent-api.
# BAND_BASE_URL should point to the Agent API base, for example the documented
# /api/v1/agent base path. The app does not hardcode that host or base URL.
BAND_AGENT_DETAILS_ENDPOINT = "/me"  # GET /agent/me: current agent profile
BAND_PEERS_ENDPOINT = "/peers"  # GET /agent/peers: recruitable peers
BAND_CONVERSATIONS_ENDPOINT = "/chats"  # GET /agent/chats: agent chat rooms
BAND_CHAT_DETAILS_ENDPOINT = "/chats/{chat_id}"  # GET /agent/chats/{id}
BAND_MESSAGES_ENDPOINT = "/chats/{chat_id}/messages"  # GET/POST messages
BAND_NEXT_MESSAGE_ENDPOINT = (
    "/chats/{chat_id}/messages/next"  # GET startup-sync backlog item
)
BAND_MESSAGE_PROCESSING_ENDPOINT = (
    "/chats/{chat_id}/messages/{message_id}/processing"  # POST processing ack
)
BAND_MESSAGE_PROCESSED_ENDPOINT = (
    "/chats/{chat_id}/messages/{message_id}/processed"  # POST processed ack
)
BAND_MESSAGE_FAILED_ENDPOINT = (
    "/chats/{chat_id}/messages/{message_id}/failed"  # POST failed ack
)
BAND_EVENTS_ENDPOINT = "/chats/{chat_id}/events"  # POST tool/thought events
BAND_CONTEXT_ENDPOINT = "/chats/{chat_id}/context"  # GET rehydration context
BAND_PARTICIPANTS_ENDPOINT = (
    "/chats/{chat_id}/participants"  # GET/POST chat participants
)

SECRET_KEYS = {
    "api_key",
    "apikey",
    "x-api-key",
    "token",
    "access_token",
    "authorization",
    "secret",
    "password",
}

LAST_BAND_RESPONSE: dict[str, Any] = {
    "chat_count": 0,
    "chat_ids": [],
    "message_count": 0,
    "latest_message": "",
    "errors": [],
    "raw": {},
    "last_check": None,
}


def record_band_debug_response(payload: dict[str, Any]) -> dict[str, Any]:
    global LAST_BAND_RESPONSE
    LAST_BAND_RESPONSE = sanitize_value(payload)
    return LAST_BAND_RESPONSE


def get_last_band_debug_response() -> dict[str, Any]:
    return LAST_BAND_RESPONSE


def sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: sanitize_value(nested)
            for key, nested in value.items()
            if key.lower() not in SECRET_KEYS
        }
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    return value


class BandClient:
    def __init__(self):
        self.enabled = os.getenv("BAND_ENABLED", "false").lower() == "true"
        self.agent_id = os.getenv("BAND_AGENT_ID", "")
        self.api_key = os.getenv("BAND_API_KEY", "")
        self.base_url = os.getenv("BAND_BASE_URL", "").rstrip("/")

    def is_enabled(self) -> bool:
        return self.enabled

    def is_configured(self) -> bool:
        return bool(self.enabled and self.agent_id and self.api_key and self.base_url)

    def health_check(self) -> dict[str, Any]:
        append_log("band.log", "Band connectivity check")
        if not self.enabled:
            return {
                "enabled": False,
                "configured": False,
                "connected": False,
                "status": "disabled",
            }
        if not self.is_configured():
            append_log("band.log", "Band connection skipped: missing credentials")
            return {
                "enabled": True,
                "configured": False,
                "connected": False,
                "status": "missing_credentials",
            }

        agent = self.get_agent_details()
        connected = agent.get("status") != "error"
        append_log(
            "band.log",
            "Band connection success" if connected else "Band connection failure",
        )
        return {
            "enabled": True,
            "configured": True,
            "connected": connected,
            "status": "connected" if connected else "disconnected",
            "agent": agent if connected else None,
            "error": None if connected else agent.get("message", "Band request failed"),
        }

    def get_agent_details(self) -> dict[str, Any]:
        return self._request("GET", BAND_AGENT_DETAILS_ENDPOINT)

    def get_agent_me(self) -> dict[str, Any]:
        return self.get_agent_details()

    def get_peers(self, not_in_chat: str | None = None) -> dict[str, Any]:
        query = {"not_in_chat": not_in_chat} if not_in_chat else None
        return self._request("GET", BAND_PEERS_ENDPOINT, query=query)

    def get_conversations(
        self, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            BAND_CONVERSATIONS_ENDPOINT,
            query={"page": page, "page_size": page_size},
        )

    def list_chats(self, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        append_log("band.log", "Band chat discovery")
        return self.get_conversations(page=page, page_size=page_size)

    def get_chat(self, chat_id: str) -> dict[str, Any]:
        return self._request("GET", BAND_CHAT_DETAILS_ENDPOINT.format(chat_id=chat_id))

    def get_messages(
        self,
        chat_id: str,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {"limit": limit}
        if status:
            query["status"] = status
        if cursor:
            query["cursor"] = cursor
        return self._request(
            "GET", BAND_MESSAGES_ENDPOINT.format(chat_id=chat_id), query=query
        )

    def get_chat_messages(
        self,
        chat_id: str,
        status: str | None = "all",
        limit: int = 20,
    ) -> dict[str, Any]:
        return self.get_messages(chat_id=chat_id, status=status, limit=limit)

    def get_next_message(self, chat_id: str) -> dict[str, Any]:
        append_log("band.log", "Band next message check")
        return self._request("GET", BAND_NEXT_MESSAGE_ENDPOINT.format(chat_id=chat_id))

    def mark_message_processing(self, chat_id: str, message_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            BAND_MESSAGE_PROCESSING_ENDPOINT.format(
                chat_id=chat_id, message_id=message_id
            ),
        )

    def mark_message_processed(self, chat_id: str, message_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            BAND_MESSAGE_PROCESSED_ENDPOINT.format(
                chat_id=chat_id, message_id=message_id
            ),
        )

    def mark_message_failed(
        self, chat_id: str, message_id: str, error: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            BAND_MESSAGE_FAILED_ENDPOINT.format(chat_id=chat_id, message_id=message_id),
            body={"error": error},
        )

    def get_chat_context(self, chat_id: str) -> dict[str, Any]:
        return self._request("GET", BAND_CONTEXT_ENDPOINT.format(chat_id=chat_id))

    def send_message(
        self,
        chat_id: str,
        content: str,
        mentions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body = {"message": {"content": content, "mentions": mentions or []}}
        return self._request(
            "POST", BAND_MESSAGES_ENDPOINT.format(chat_id=chat_id), body=body
        )

    def send_chat_message(
        self,
        chat_id: str,
        content: str,
        mentions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        response = self.send_message(chat_id=chat_id, content=content, mentions=mentions)
        if response.get("status") == "error":
            append_log("band.log", "Band message send failure")
        else:
            append_log("band.log", "Band message sent")
        return response

    def post_event(
        self,
        chat_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = {
            "event": {
                "content": payload.get("content", event_type) if payload else event_type,
                "message_type": event_type,
                "metadata": payload or {},
            }
        }
        return self._request("POST", BAND_EVENTS_ENDPOINT.format(chat_id=chat_id), body)

    def post_chat_event(
        self,
        chat_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.post_event(chat_id=chat_id, event_type=event_type, payload=payload)

    def get_participants(self, chat_id: str) -> dict[str, Any]:
        return self._request(
            "GET", BAND_PARTICIPANTS_ENDPOINT.format(chat_id=chat_id)
        )

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled"}
        if not self.is_configured():
            return {"status": "missing_credentials"}

        url = f"{self.base_url}{path}"
        if query:
            filtered_query = {key: value for key, value in query.items() if value is not None}
            if filtered_query:
                url = f"{url}?{urlencode(filtered_query)}"

        data = None
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "QuasarEnterpriseAISwarm/1.0",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, data=data, headers=headers, method=method)

        try:
            with urlopen(request, timeout=10) as response:
                if response.status == 204:
                    result = {"status": "ok", "data": None}
                    self._log_api_response(method, path, result)
                    return result
                raw = response.read().decode("utf-8")
                if not raw:
                    result = {"status": "ok", "data": None}
                    self._log_api_response(method, path, result)
                    return result
                result = self._sanitize(json.loads(raw))
                self._log_api_response(method, path, result)
                return result
        except HTTPError as exc:
            error_body = ""
            try:
                error_body = exc.read().decode("utf-8")
            except Exception:
                error_body = ""
            error_detail: Any = error_body
            if error_body:
                try:
                    error_detail = self._sanitize(json.loads(error_body))
                except json.JSONDecodeError:
                    error_detail = error_body[:500]
            result = {
                "status": "error",
                "message": f"Band request failed with HTTP {exc.code}",
            }
            if error_detail:
                result["detail"] = error_detail
            self._log_api_response(method, path, result)
            return result
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            result = {"status": "error", "message": f"Band request failed: {exc}"}
            self._log_api_response(method, path, result)
            return result

    def _sanitize(self, value: Any) -> Any:
        return sanitize_value(value)

    def _log_api_response(self, method: str, path: str, payload: dict[str, Any]) -> None:
        safe_payload = self._sanitize(payload)
        append_log(
            "band.log",
            (
                f"Band API response {method} {path} "
                f"{json.dumps(safe_payload, sort_keys=True)}"
            ),
        )


def band_config_status() -> dict[str, Any]:
    client = BandClient()
    return {
        "enabled": client.is_enabled(),
        "configured": client.is_configured(),
        "mode": "band" if client.is_configured() else "mock",
    }


def extract_agent_identity(agent: dict[str, Any], fallback_agent_id: str) -> dict[str, str]:
    data = agent.get("data") if isinstance(agent.get("data"), dict) else agent
    return {
        "agent_id": str(data.get("id") or fallback_agent_id),
        "agent_name": str(data.get("name") or data.get("handle") or "Band Agent"),
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
