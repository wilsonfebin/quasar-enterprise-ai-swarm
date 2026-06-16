from __future__ import annotations

from typing import Any


HIERARCHY_SEQUENCE = ["4H", "1H", "15m", "5m", "1m"]

TIMEFRAME_ROLES = {
    "4H": "Primary regime anchor",
    "1H": "Structural context",
    "15m": "Tactical transition",
    "5m": "Micro confirmation",
    "1m": "Noise / execution-context only",
}

INFLUENCE = {
    "4H": "Dominant",
    "1H": "High",
    "15m": "Medium",
    "5m": "Low",
    "1m": "Minimal",
}


def generate_timeframe_hierarchy(market_intelligence: dict[str, Any]) -> dict[str, Any]:
    timeframes = market_intelligence.get("timeframes") or {}
    hierarchy: dict[str, dict[str, Any]] = {}
    previous_state = ""
    previous_side = "NEUTRAL"

    for timeframe in HIERARCHY_SEQUENCE:
        payload = timeframes.get(timeframe, {})
        state = _state(payload)
        side = _side(state)
        node = {
            "role": TIMEFRAME_ROLES[timeframe],
            "state": _display_state(state),
            "raw_state": state or "INSUFFICIENT",
            "side": side,
            "influence": INFLUENCE[timeframe],
            "confidence": _confidence(payload),
            "primary_signal": _primary_signal(payload),
        }
        if timeframe != "4H":
            node["relationship_to_parent"] = _relationship_to_parent(
                parent_state=previous_state,
                parent_side=previous_side,
                child_state=state,
                child_side=side,
            )
        hierarchy[timeframe] = node
        previous_state = state
        previous_side = side

    higher_side = _dominant_side(hierarchy, ("4H", "1H"))
    lower_side = _dominant_side(hierarchy, ("15m", "5m", "1m"))
    hierarchy_conflict = _hierarchy_conflict(higher_side, lower_side, hierarchy)

    return {
        "hierarchy": hierarchy,
        "dominant_context": _dominant_context(higher_side, lower_side),
        "hierarchy_conflict": hierarchy_conflict,
        "scenario_bias": _scenario_bias(higher_side, lower_side, hierarchy_conflict, hierarchy),
        "parent_child_sequence": _parent_child_sequence(hierarchy),
    }


def _state(payload: dict[str, Any]) -> str:
    return str(
        payload.get("structure_state")
        or payload.get("state")
        or payload.get("structure")
        or "INSUFFICIENT"
    ).upper().replace(" ", "_")


def _side(state: str) -> str:
    if "BULLISH" in state:
        return "BULLISH"
    if "BEARISH" in state:
        return "BEARISH"
    if state in {"RANGING", "RANGE", "NEUTRAL"}:
        return "NEUTRAL"
    return "NEUTRAL"


def _display_state(state: str) -> str:
    if not state or state == "INSUFFICIENT":
        return "Insufficient Structure"
    return state.replace("_", " ").title()


def _confidence(payload: dict[str, Any]) -> float:
    try:
        return round(float(payload.get("confidence") or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _primary_signal(payload: dict[str, Any]) -> str:
    signal = payload.get("primary_signal")
    if signal:
        return str(signal)
    top_signal = payload.get("top_signal") or {}
    return str(top_signal.get("label") or top_signal.get("label_type") or "")


def _relationship_to_parent(
    parent_state: str,
    parent_side: str,
    child_state: str,
    child_side: str,
) -> str:
    if not parent_state or parent_state == "INSUFFICIENT" or child_state == "INSUFFICIENT":
        return "Insufficient parent-child evidence"
    if parent_side == "NEUTRAL" or child_side == "NEUTRAL":
        return "Neutral / range relationship"
    if parent_side == child_side:
        if "TRANSITION" in child_state and "CONTINUATION" in parent_state:
            return "Aligned pullback"
        return "Aligned"
    if "TRANSITION" in child_state:
        return "Counter-trend correction"
    return "Conflicting"


def _dominant_side(hierarchy: dict[str, dict[str, Any]], selected: tuple[str, ...]) -> str:
    score = {"BULLISH": 0.0, "BEARISH": 0.0}
    weights = {"4H": 5, "1H": 4, "15m": 3, "5m": 2, "1m": 1}
    for timeframe in selected:
        node = hierarchy.get(timeframe, {})
        side = str(node.get("side", "NEUTRAL"))
        if side in score:
            score[side] += weights.get(timeframe, 1) * float(node.get("confidence") or 0.5)
    if score["BULLISH"] > score["BEARISH"]:
        return "BULLISH"
    if score["BEARISH"] > score["BULLISH"]:
        return "BEARISH"
    return "NEUTRAL"


def _hierarchy_conflict(
    higher_side: str,
    lower_side: str,
    hierarchy: dict[str, dict[str, Any]],
) -> str:
    conflict_count = sum(
        1
        for node in hierarchy.values()
        if str(node.get("relationship_to_parent", "")).lower()
        in {"counter-trend correction", "conflicting"}
    )
    if higher_side != "NEUTRAL" and lower_side != "NEUTRAL" and higher_side != lower_side:
        return "High"
    if conflict_count >= 2:
        return "Medium"
    if conflict_count == 1:
        return "Low"
    return "Low"


def _dominant_context(higher_side: str, lower_side: str) -> str:
    if higher_side == "BULLISH" and lower_side == "BEARISH":
        return "Higher timeframe bullish, lower timeframe corrective"
    if higher_side == "BEARISH" and lower_side == "BULLISH":
        return "Higher timeframe bearish, lower timeframe corrective"
    if higher_side == "BULLISH" and lower_side == "BULLISH":
        return "Bullish structure aligned across hierarchy"
    if higher_side == "BEARISH" and lower_side == "BEARISH":
        return "Bearish structure aligned across hierarchy"
    if higher_side == "NEUTRAL":
        return "Higher timeframe context is neutral or insufficient"
    return "Mixed hierarchy context"


def _scenario_bias(
    higher_side: str,
    lower_side: str,
    hierarchy_conflict: str,
    hierarchy: dict[str, dict[str, Any]],
) -> str:
    tactical = hierarchy.get("15m", {})
    tactical_side = str(tactical.get("side", "NEUTRAL"))
    if higher_side == "BULLISH" and lower_side == "BEARISH":
        if tactical_side == "BULLISH":
            return "Bullish Continuation if 15m realigns"
        return "Bullish Continuation only if tactical structure realigns"
    if higher_side == "BEARISH" and lower_side == "BULLISH":
        if tactical_side == "BEARISH":
            return "Bearish Continuation if 15m realigns"
        return "Bearish Continuation only if tactical structure realigns"
    if hierarchy_conflict == "High":
        return "Wait for hierarchy conflict to reduce"
    if higher_side == "BULLISH" and lower_side == "BULLISH":
        return "Bullish Continuation favored while hierarchy remains aligned"
    if higher_side == "BEARISH" and lower_side == "BEARISH":
        return "Bearish Continuation favored while hierarchy remains aligned"
    return "No clear hierarchy scenario bias"


def _parent_child_sequence(hierarchy: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "timeframe": timeframe,
            "role": str(hierarchy.get(timeframe, {}).get("role", "")),
            "state": str(hierarchy.get(timeframe, {}).get("state", "")),
            "relationship_to_parent": str(
                hierarchy.get(timeframe, {}).get("relationship_to_parent", "")
            ),
        }
        for timeframe in HIERARCHY_SEQUENCE
    ]
