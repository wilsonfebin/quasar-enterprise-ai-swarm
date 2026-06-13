from dataclasses import asdict, dataclass
import os
from typing import Any


@dataclass
class BandAgentDefinition:
    key: str
    agent_name: str
    expected_handle: str


@dataclass
class BandAgentRegistration:
    key: str
    agent_name: str
    expected_handle: str
    handle: str
    participant_id: str
    connected: bool


@dataclass
class SpecialistAgentConfig:
    key: str
    agent_name: str
    response_key: str
    handle: str
    agent_id: str
    api_key: str
    base_url: str
    enabled: bool

    def is_configured(self) -> bool:
        return bool(self.enabled and self.agent_id and self.api_key and self.base_url)

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "agent_name": self.agent_name,
            "response_key": self.response_key,
            "handle": self.handle,
            "agent_id": self.agent_id,
            "configured": self.is_configured(),
        }


COORDINATOR_AGENT_DEFINITION = BandAgentDefinition(
    "COORDINATOR_AGENT", "Quasar Coordinator", "quasar-remote-agent"
)

SPECIALIST_AGENT_DEFINITIONS = [
    BandAgentDefinition("REQUIREMENT_AGENT", "Requirement Agent", "quasar-requirement"),
    BandAgentDefinition(
        "MARKET_INTELLIGENCE_AGENT",
        "Market Intelligence Agent",
        "quasar-market-intel",
    ),
    BandAgentDefinition("ARCHITECTURE_AGENT", "Architecture Agent", "quasar-architecture"),
    BandAgentDefinition("RISK_GOVERNANCE_AGENT", "Risk Governance Agent", "quasar-risk"),
    BandAgentDefinition("DELIVERY_PLANNING_AGENT", "Delivery Planning Agent", "quasar-delivery"),
    BandAgentDefinition("FINAL_REVIEW_AGENT", "Final Review Agent", "quasar-review"),
]

SPECIALIST_RESPONSE_KEYS = {
    "REQUIREMENT_AGENT": "requirement",
    "MARKET_INTELLIGENCE_AGENT": "market_intel",
    "ARCHITECTURE_AGENT": "architecture",
    "RISK_GOVERNANCE_AGENT": "risk",
    "DELIVERY_PLANNING_AGENT": "delivery",
    "FINAL_REVIEW_AGENT": "review",
}

SPECIALIST_ENV_PREFIXES = {
    "REQUIREMENT_AGENT": "BAND_REQUIREMENT",
    "MARKET_INTELLIGENCE_AGENT": "BAND_MARKET_INTEL",
    "ARCHITECTURE_AGENT": "BAND_ARCHITECTURE",
    "RISK_GOVERNANCE_AGENT": "BAND_RISK",
    "DELIVERY_PLANNING_AGENT": "BAND_DELIVERY",
    "FINAL_REVIEW_AGENT": "BAND_REVIEW",
}


def specialist_configs() -> list[SpecialistAgentConfig]:
    return [specialist_config_for_definition(definition) for definition in SPECIALIST_AGENT_DEFINITIONS]


def specialist_config_for_agent(agent_name: str) -> SpecialistAgentConfig | None:
    for definition in SPECIALIST_AGENT_DEFINITIONS:
        if definition.agent_name == agent_name:
            return specialist_config_for_definition(definition)
    return None


def specialist_config_for_definition(
    definition: BandAgentDefinition,
) -> SpecialistAgentConfig:
    prefix = SPECIALIST_ENV_PREFIXES[definition.key]
    return SpecialistAgentConfig(
        key=definition.key,
        agent_name=definition.agent_name,
        response_key=SPECIALIST_RESPONSE_KEYS[definition.key],
        handle=os.getenv(f"{prefix}_HANDLE", definition.expected_handle),
        agent_id=os.getenv(f"{prefix}_AGENT_ID", ""),
        api_key=os.getenv(f"{prefix}_API_KEY", ""),
        base_url=os.getenv("BAND_BASE_URL", ""),
        enabled=os.getenv("BAND_ENABLED", "false").lower() == "true",
    )


class BandAgentRegistry:
    def __init__(self, participants: list[dict[str, Any]]):
        self.participants = participants
        self.coordinator = self._discover_one(COORDINATOR_AGENT_DEFINITION)
        self.registrations = self._discover()

    def as_dict(self) -> dict[str, Any]:
        return {
            "coordinator": asdict(self.coordinator),
            "agents": [asdict(registration) for registration in self.registrations],
            "all_specialists_connected": self.all_specialists_connected(),
            "connected_count": sum(1 for agent in self.registrations if agent.connected),
            "expected_count": len(self.registrations),
        }

    def all_specialists_connected(self) -> bool:
        return all(registration.connected for registration in self.registrations)

    def by_agent_name(self, agent_name: str) -> BandAgentRegistration | None:
        for registration in self.registrations:
            if registration.agent_name == agent_name and registration.connected:
                return registration
        return None

    def _discover(self) -> list[BandAgentRegistration]:
        return [self._discover_one(definition) for definition in SPECIALIST_AGENT_DEFINITIONS]

    def _discover_one(self, definition: BandAgentDefinition) -> BandAgentRegistration:
        participant = self._find_participant(definition.expected_handle)
        return BandAgentRegistration(
            key=definition.key,
            agent_name=definition.agent_name,
            expected_handle=definition.expected_handle,
            handle=str(participant.get("handle", "")) if participant else "",
            participant_id=str(participant.get("id", "")) if participant else "",
            connected=participant is not None,
        )

    def _find_participant(self, expected_handle: str) -> dict[str, Any] | None:
        for participant in self.participants:
            handle = str(participant.get("handle", "")).lower()
            name = str(participant.get("name", "")).lower()
            if expected_handle in handle or expected_handle in name:
                return participant
        return None
