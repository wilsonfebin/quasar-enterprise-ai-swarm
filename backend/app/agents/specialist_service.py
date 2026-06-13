from typing import Any, Callable

from app.agents.band_client import BandClient, utc_now_iso
from app.agents.band_registry import (
    SpecialistAgentConfig,
    specialist_config_for_agent,
    specialist_configs,
)
from app.data.ingestion_service import append_log


ProcessorFn = Callable[[str], str]


def process_requirement_agent(chat_id: str | None = None) -> dict[str, Any]:
    return SpecialistProcessorService().process_agent("Requirement Agent", chat_id=chat_id)


def process_market_intel_agent(chat_id: str | None = None) -> dict[str, Any]:
    return SpecialistProcessorService().process_agent(
        "Market Intelligence Agent", chat_id=chat_id
    )


def process_architecture_agent(chat_id: str | None = None) -> dict[str, Any]:
    return SpecialistProcessorService().process_agent("Architecture Agent", chat_id=chat_id)


def process_risk_agent(chat_id: str | None = None) -> dict[str, Any]:
    return SpecialistProcessorService().process_agent("Risk Governance Agent", chat_id=chat_id)


def process_delivery_agent(chat_id: str | None = None) -> dict[str, Any]:
    return SpecialistProcessorService().process_agent("Delivery Planning Agent", chat_id=chat_id)


def process_review_agent(chat_id: str | None = None) -> dict[str, Any]:
    return SpecialistProcessorService().process_agent("Final Review Agent", chat_id=chat_id)


class SpecialistProcessorService:
    def process_all(self, chat_id: str | None = None) -> dict[str, Any]:
        results = [self.process_config(config, chat_id=chat_id) for config in specialist_configs()]
        return {
            "success": True,
            "processed_count": sum(1 for result in results if result.get("status") == "processed"),
            "results": results,
            "processed_at": utc_now_iso(),
        }

    def process_agent(self, agent_name: str, chat_id: str | None = None) -> dict[str, Any]:
        config = specialist_config_for_agent(agent_name)
        if not config:
            return {
                "success": False,
                "agent": agent_name,
                "status": "unknown_agent",
                "message": "Specialist agent is not registered",
            }
        return self.process_config(config, chat_id=chat_id)

    def process_config(
        self, config: SpecialistAgentConfig, chat_id: str | None = None
    ) -> dict[str, Any]:
        if not config.enabled:
            return self._result(config, "disabled", success=False)
        if not config.is_configured():
            append_log(
                "band.log",
                f"{config.agent_name} specialist processing skipped: missing credentials",
            )
            return self._result(config, "missing_credentials", success=False)

        client = self._client(config)
        chat_ids = [chat_id] if chat_id else self._chat_ids(client)
        if not chat_ids:
            return self._result(config, "no_chats", success=False)

        for selected_chat_id in chat_ids:
            result = self._process_next_for_chat(client, config, selected_chat_id)
            if result.get("status") == "processed":
                return result
            if result.get("status") not in {"no_messages", "no_message"}:
                return result

        return self._result(config, "no_messages", chat_id=chat_ids[0] if chat_ids else "")

    def _process_next_for_chat(
        self, client: BandClient, config: SpecialistAgentConfig, chat_id: str
    ) -> dict[str, Any]:
        append_log("band.log", f"{config.agent_name} specialist next message check")
        next_response = client.get_next_message(chat_id)
        if next_response.get("status") == "error":
            return self._result(
                config,
                "failed",
                chat_id=chat_id,
                success=False,
                error=next_response.get("message", "Unable to fetch specialist message"),
            )

        message = self._extract_message(next_response)
        if not message:
            return self._result(config, "no_messages", chat_id=chat_id)

        message_id = self._message_id(message)
        if not message_id:
            return self._result(
                config,
                "failed",
                chat_id=chat_id,
                success=False,
                error="Specialist message did not include an id",
            )

        try:
            processing_response = client.mark_message_processing(chat_id, message_id)
            if processing_response.get("status") == "error":
                return self._result(
                    config,
                    "failed",
                    chat_id=chat_id,
                    message_id=message_id,
                    success=False,
                    error=processing_response.get(
                        "message", "Unable to mark specialist message processing"
                    ),
                )

            incoming_content = self._message_text(message)
            response_text = self._generate_response(config, incoming_content)
            mentions = self._response_mentions(client, chat_id, message)
            if not mentions:
                raise RuntimeError("No coordinator participant found for specialist reply")

            send_response = client.send_chat_message(
                chat_id=chat_id,
                content=f"{self._mention_prefix(mentions[0])} {response_text}",
                mentions=mentions,
            )
            if send_response.get("status") == "error":
                raise RuntimeError(
                    send_response.get("message", "Specialist Band response failed")
                )

            processed_response = client.mark_message_processed(chat_id, message_id)
            if processed_response.get("status") == "error":
                raise RuntimeError(
                    processed_response.get(
                        "message", "Unable to mark specialist message processed"
                    )
                )

            append_log("band.log", f"{config.agent_name} specialist response processed")
            return self._result(
                config,
                "processed",
                chat_id=chat_id,
                message_id=message_id,
                response_text=response_text,
            )
        except Exception as exc:
            error = str(exc)
            client.mark_message_failed(chat_id, message_id, error)
            append_log("band.log", f"{config.agent_name} specialist processing failed: {error}")
            return self._result(
                config,
                "failed",
                chat_id=chat_id,
                message_id=message_id,
                success=False,
                error=error,
            )

    def _client(self, config: SpecialistAgentConfig) -> BandClient:
        return BandClient(
            agent_id=config.agent_id,
            api_key=config.api_key,
            base_url=config.base_url,
            enabled=config.enabled,
        )

    def _chat_ids(self, client: BandClient) -> list[str]:
        chats_response = client.list_chats()
        chats = self._extract_data_list(chats_response)
        return [str(chat.get("id", "")) for chat in chats if chat.get("id")]

    def _generate_response(self, config: SpecialistAgentConfig, content: str) -> str:
        processors: dict[str, ProcessorFn] = {
            "Requirement Agent": self._requirement_response,
            "Market Intelligence Agent": self._market_intel_response,
            "Architecture Agent": self._architecture_response,
            "Risk Governance Agent": self._risk_response,
            "Delivery Planning Agent": self._delivery_response,
            "Final Review Agent": self._review_response,
        }
        processor = processors.get(config.agent_name, self._generic_response)
        return processor(content)

    def _requirement_response(self, content: str) -> str:
        timeframe = self._field(content, "Timeframe")
        scope = self._selected_scope(content)
        return (
            "Requirement Agent response: decision-support scope confirmed for "
            f"{scope} on {timeframe}. Objective is structure interpretation, "
            "confidence review, and next validation planning within advisory-only boundaries."
        )

    def _market_intel_response(self, content: str) -> str:
        market = self._selected_market_summary(content)
        decision = self._decision_state(content)
        return (
            "Market Intelligence Agent response: "
            f"{market} Decision state is {decision}; structure should be watched "
            "and validated against the next candle and higher timeframe context."
        )

    def _architecture_response(self, content: str) -> str:
        readiness = self._selected_readiness_summary(content)
        return (
            "System Readiness Agent response: current feed is usable for decision support "
            f"with these caveats: {readiness} Validate freshness, session state, and "
            "top-label confidence before relying on the structure."
        )

    def _risk_response(self, content: str) -> str:
        decision = self._decision_state(content)
        return (
            "Risk Governance Agent response: guardrails set to advisory-only. "
            f"Decision state {decision} requires patience, confirmation, and no automated "
            "execution. Off-session or stale data should force wait/validate behavior."
        )

    def _delivery_response(self, content: str) -> str:
        decision = self._decision_state(content)
        return (
            "Delivery Planning Agent response: next-step decision plan is "
            f"{decision}. Monitor the next candle close, compare higher timeframe structure, "
            "and re-check liquidity-sweep or BOS confirmation before updating the state."
        )

    def _review_response(self, content: str) -> str:
        decision = self._decision_state(content)
        market = self._selected_market_summary(content)
        return (
            "Final Review Agent response: "
            f"Decision State: {decision}. Evidence: {market} Next validation is "
            "higher timeframe agreement plus next candle confirmation. Safety remains "
            "advisory-only with no execution."
        )

    def _generic_response(self, content: str) -> str:
        return "Specialist response: request received and processed by Quasar."

    def _field(self, content: str, name: str) -> str:
        prefix = f"{name}:"
        for line in content.splitlines():
            if line.strip().startswith(prefix):
                return line.split(":", 1)[1].strip()
        return "current timeframe"

    def _market_name(self, content: str, market: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith(f"{market} "):
                return stripped.rstrip(":")
        return market

    def _selected_scope(self, content: str) -> str:
        scope = self._field(content, "Scope")
        return scope if scope != "current timeframe" else self._market_name(content, "MCX")

    def _selected_market_key(self, content: str) -> str:
        scope = self._selected_scope(content).lower()
        return "Forex" if "forex" in scope or "xauusd" in scope else "MCX"

    def _selected_market_summary(self, content: str) -> str:
        return self._market_summary(content, self._selected_market_key(content))

    def _selected_readiness_summary(self, content: str) -> str:
        return self._readiness_summary(content, self._selected_market_key(content))

    def _market_summary(self, content: str, market: str) -> str:
        name = self._market_name(content, market)
        if name == market:
            selected_scope = self._selected_scope(content)
            if market.lower() in selected_scope.lower() or (
                market == "Forex" and "xauusd" in selected_scope.lower()
            ):
                name = selected_scope
        labels = self._top_labels(content, market)
        bias = self._market_line_value(content, market, "Dominant Bias")
        session = self._market_line_value(content, market, "Session")
        data_age = self._market_line_value(content, market, "Data Age")
        return (
            f"{name}: {bias}; {labels}; session {session}; data age {data_age}."
        )

    def _readiness_summary(self, content: str, market: str) -> str:
        name = self._market_name(content, market)
        if name == market:
            selected_scope = self._selected_scope(content)
            if market.lower() in selected_scope.lower() or (
                market == "Forex" and "xauusd" in selected_scope.lower()
            ):
                name = selected_scope
        source = self._market_line_value(content, market, "Source")
        session = self._market_line_value(content, market, "Session")
        data_age = self._market_line_value(content, market, "Data Age")
        return f"{name} source {source}, {session}, age {data_age}."

    def _top_labels(self, content: str, market: str) -> str:
        lines = self._market_section(content, market)
        labels = [
            line.strip()[2:]
            for line in lines
            if line.strip().startswith("- ") and "confidence" in line
        ]
        return ", ".join(labels[:3]) if labels else "no labels"

    def _market_line_value(self, content: str, market: str, prefix: str) -> str:
        for line in self._market_section(content, market):
            stripped = line.strip()
            normalized = stripped.lower().lstrip("- ").replace("data age", "data age")
            normalized_prefix = prefix.lower().lstrip("- ")
            if normalized.startswith(normalized_prefix):
                return stripped.split(":", 1)[1].strip()
        return "unknown"

    def _market_section(self, content: str, market: str) -> list[str]:
        lines = content.splitlines()
        start = None
        for index, line in enumerate(lines):
            if line.strip().startswith(f"{market} "):
                start = index + 1
                break
            if line.strip().startswith("Scope:"):
                scope = line.split(":", 1)[1].strip().lower()
                if market.lower() in scope or (market == "Forex" and "xauusd" in scope):
                    start = index + 1
                    break
        if start is None:
            return []
        section = []
        for line in lines[start:]:
            stripped = line.strip()
            if stripped.startswith(("MCX ", "Forex ", "Safety:")):
                break
            section.append(line)
        return section

    def _decision_state(self, content: str) -> str:
        lowered = content.lower()
        if "mixed conflicted" in lowered:
            return "CONFLICTED"
        if "mixed bullish" in lowered and "mixed bearish" in lowered:
            return "VALIDATE"
        if "mixed bullish" in lowered or "mixed bearish" in lowered:
            return "WATCH"
        if "liquidity_sweep" in lowered or "choch" in lowered:
            return "VALIDATE"
        return "WAIT"

    def _response_mentions(
        self, client: BandClient, chat_id: str, message: dict[str, Any]
    ) -> list[dict[str, Any]]:
        sender_id = str(message.get("sender_id", ""))
        participants = self._extract_data_list(client.get_participants(chat_id))
        if sender_id:
            for participant in participants:
                if str(participant.get("id", "")) == sender_id:
                    return [self._participant_to_mention(participant)]
            return [{"id": sender_id}]
        for participant in participants:
            handle = str(participant.get("handle", "")).lower()
            name = str(participant.get("name", "")).lower()
            if "quasar-remote-agent" in handle or "quasar-remote-agent" in name:
                return [self._participant_to_mention(participant)]
        return []

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

    def _message_id(self, message: dict[str, Any]) -> str:
        return str(message.get("id") or message.get("message", {}).get("id") or "")

    def _message_text(self, message: dict[str, Any]) -> str:
        return str(
            message.get("content")
            or message.get("message", {}).get("content")
            or message.get("message_type")
            or ""
        )

    def _result(
        self,
        config: SpecialistAgentConfig,
        status: str,
        chat_id: str = "",
        message_id: str = "",
        response_text: str = "",
        success: bool = True,
        error: str = "",
    ) -> dict[str, Any]:
        return {
            "success": success,
            "agent": config.agent_name,
            "response_key": config.response_key,
            "handle": config.handle,
            "configured": config.is_configured(),
            "status": status,
            "chat_id": chat_id,
            "message_id": message_id,
            "response_text": response_text,
            "error": error,
            "processed_at": utc_now_iso(),
        }
