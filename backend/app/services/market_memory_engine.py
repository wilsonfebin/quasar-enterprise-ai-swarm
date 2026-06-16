from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


SUPPORTED_MEMORY_STATES = [
    "Bullish Trend",
    "Bearish Trend",
    "Bullish Pullback",
    "Bearish Pullback",
    "Bullish Transition",
    "Bearish Transition",
    "Neutral",
    "Conflicted",
]


def ensure_market_memory_table() -> None:
    from app.db import get_connection

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS market_memory (
                    id BIGSERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    market TEXT NOT NULL,
                    market_regime TEXT NOT NULL,
                    alignment TEXT NOT NULL,
                    conflict_level TEXT NOT NULL,
                    confidence NUMERIC NOT NULL DEFAULT 0,
                    decision_state TEXT NOT NULL,
                    scenario_name TEXT NOT NULL,
                    snapshot_payload JSONB NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_market_memory_market_timestamp
                ON market_memory (market, timestamp DESC)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_market_memory_regime
                ON market_memory (market_regime)
                """
            )
        connection.commit()


def record_snapshot(market_intelligence: dict[str, Any]) -> dict[str, Any]:
    from psycopg2.extras import Json, RealDictCursor
    from app.db import get_connection

    ensure_market_memory_table()
    snapshot = _memory_snapshot_from_intelligence(market_intelligence)
    latest = _fetch_latest_memory_snapshot(snapshot["market"])
    if latest and not _should_record_snapshot(latest, snapshot):
        return {"status": "duplicate_skipped", "snapshot": snapshot}

    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO market_memory (
                    timestamp, market, market_regime, alignment, conflict_level,
                    confidence, decision_state, scenario_name, snapshot_payload
                )
                VALUES (
                    %(timestamp)s, %(market)s, %(market_regime)s, %(alignment)s,
                    %(conflict_level)s, %(confidence)s, %(decision_state)s,
                    %(scenario_name)s, %(snapshot_payload)s
                )
                RETURNING id
                """,
                {
                    **snapshot,
                    "snapshot_payload": Json(snapshot["snapshot_payload"]),
                },
            )
            inserted = cursor.fetchone()
        connection.commit()
    return {"status": "recorded", "id": inserted["id"], "snapshot": snapshot}


def record_regime_transition(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_regime = _memory_state(previous.get("market_regime") or previous.get("regime"))
    current_regime = _memory_state(current.get("market_regime") or current.get("regime"))
    return {
        "from": previous_regime,
        "to": current_regime,
        "changed": previous_regime != current_regime,
    }


def calculate_regime_duration_statistics(
    snapshots: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, dict[str, float | int]]:
    snapshots = _sorted_snapshots(snapshots if snapshots is not None else _fetch_memory_snapshots())
    stats = {
        state: {
            "sample_count": 0,
            "average_duration_hours": 0,
            "max_duration_hours": 0,
            "min_duration_hours": 0,
        }
        for state in SUPPORTED_MEMORY_STATES
    }
    durations: dict[str, list[float]] = defaultdict(list)
    if not snapshots:
        return stats

    reference_now = now or datetime.now(timezone.utc)
    for market_snapshots in _group_by_market(snapshots).values():
        for index, snapshot in enumerate(market_snapshots):
            current_time = _parse_time(snapshot.get("timestamp")) or reference_now
            next_time = (
                _parse_time(market_snapshots[index + 1].get("timestamp"))
                if index + 1 < len(market_snapshots)
                else reference_now
            )
            if not next_time or next_time <= current_time:
                continue
            regime = _memory_state(snapshot.get("market_regime"))
            durations[regime].append((next_time - current_time).total_seconds() / 3600)

    for regime, values in durations.items():
        if not values:
            continue
        stats[regime] = {
            "sample_count": len(values),
            "average_duration_hours": round(sum(values) / len(values), 2),
            "max_duration_hours": round(max(values), 2),
            "min_duration_hours": round(min(values), 2),
        }
    return stats


def calculate_transition_statistics(
    snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, int]]:
    snapshots = _sorted_snapshots(snapshots if snapshots is not None else _fetch_memory_snapshots())
    matrix = {state: {} for state in SUPPORTED_MEMORY_STATES}
    for market_snapshots in _group_by_market(snapshots).values():
        for previous, current in zip(market_snapshots, market_snapshots[1:]):
            previous_regime = _memory_state(previous.get("market_regime"))
            current_regime = _memory_state(current.get("market_regime"))
            matrix.setdefault(previous_regime, {})
            matrix[previous_regime][current_regime] = matrix[previous_regime].get(current_regime, 0) + 1
    return matrix


def calculate_persistence_scores(
    snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, int]]:
    transitions = calculate_transition_statistics(snapshots)
    scores = {}
    for regime in SUPPORTED_MEMORY_STATES:
        row = transitions.get(regime, {})
        total = sum(row.values())
        continued = row.get(regime, 0)
        scores[regime] = {
            "persistence_score": int(round((continued / total) * 100)) if total else 0
        }
    return scores


def calculate_recovery_scores(
    snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, int]]:
    transitions = calculate_transition_statistics(snapshots)
    return {
        "Bullish Pullback": {
            "recovery_to_bullish_trend": _transition_percent(
                transitions, "Bullish Pullback", "Bullish Trend"
            )
        },
        "Bearish Pullback": {
            "recovery_to_bearish_trend": _transition_percent(
                transitions, "Bearish Pullback", "Bearish Trend"
            )
        },
        "Bullish Transition": {
            "recovery_to_bullish_trend": _transition_percent(
                transitions, "Bullish Transition", "Bullish Trend"
            )
        },
        "Bearish Transition": {
            "recovery_to_bearish_trend": _transition_percent(
                transitions, "Bearish Transition", "Bearish Trend"
            )
        },
    }


def calculate_failure_scores(
    snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, int]]:
    transitions = calculate_transition_statistics(snapshots)
    return {
        "Bullish Pullback": {
            "failure_to_bearish_transition": _transition_percent(
                transitions, "Bullish Pullback", "Bearish Transition"
            )
        },
        "Bearish Pullback": {
            "failure_to_bullish_transition": _transition_percent(
                transitions, "Bearish Pullback", "Bullish Transition"
            )
        },
        "Bullish Transition": {
            "failure_to_bearish_transition": _transition_percent(
                transitions, "Bullish Transition", "Bearish Transition"
            )
        },
        "Bearish Transition": {
            "failure_to_bullish_transition": _transition_percent(
                transitions, "Bearish Transition", "Bullish Transition"
            )
        },
    }


def get_memory_summary(market: str | None = None) -> dict[str, Any]:
    ensure_market_memory_table()
    snapshots = _fetch_memory_snapshots(market=market)
    return {
        "regime_statistics": calculate_regime_duration_statistics(snapshots),
        "transition_statistics": calculate_transition_statistics(snapshots),
        "persistence_scores": calculate_persistence_scores(snapshots),
        "recovery_scores": calculate_recovery_scores(snapshots),
        "failure_scores": calculate_failure_scores(snapshots),
        "sample_count": len(snapshots),
    }


def get_transition_matrix(market: str | None = None) -> dict[str, dict[str, int]]:
    ensure_market_memory_table()
    return calculate_transition_statistics(_fetch_memory_snapshots(market=market))


def _memory_snapshot_from_intelligence(market_intelligence: dict[str, Any]) -> dict[str, Any]:
    market_type = str(market_intelligence.get("market_type", "")).upper()
    instrument = str(market_intelligence.get("instrument", "")).upper()
    market = f"{market_type}:{instrument}".strip(":") or "UNKNOWN"
    scenario = (market_intelligence.get("scenarios") or {}).get("primary_scenario") or {}
    alignment = market_intelligence.get("alignment") or {}
    decision = market_intelligence.get("decision") or {}
    timeframe_context = _timeframe_context(market_intelligence)
    timestamp = datetime.now(timezone.utc)

    return {
        "timestamp": timestamp,
        "market": market,
        "market_regime": _memory_state(market_intelligence.get("regime")),
        "alignment": _alignment_label(alignment),
        "conflict_level": str(alignment.get("conflict_level") or "Unknown").title(),
        "confidence": int(round(float(market_intelligence.get("structure_confidence") or 0) * 100)),
        "decision_state": str(decision.get("state") or "WAIT").upper(),
        "scenario_name": str(scenario.get("name") or "Wait / No Clear Scenario"),
        "snapshot_payload": {
            "timestamp": timestamp.isoformat(),
            "market": market,
            "timeframe_context": timeframe_context,
            "market_regime": _memory_state(market_intelligence.get("regime")),
            "alignment": _alignment_label(alignment),
            "conflict": str(alignment.get("conflict_level") or "Unknown").title(),
            "confidence": int(round(float(market_intelligence.get("structure_confidence") or 0) * 100)),
            "decision_state": str(decision.get("state") or "WAIT").upper(),
            "scenario_name": str(scenario.get("name") or "Wait / No Clear Scenario"),
        },
    }


def _should_record_snapshot(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    return any(
        str(previous.get(key, "")) != str(current.get(key, ""))
        for key in ("market_regime", "decision_state", "scenario_name")
    )


def _fetch_latest_memory_snapshot(market: str) -> dict[str, Any] | None:
    from psycopg2.extras import RealDictCursor
    from app.db import get_connection

    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT timestamp, market, market_regime, alignment, conflict_level,
                    confidence, decision_state, scenario_name, snapshot_payload
                FROM market_memory
                WHERE market = %s
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
                """,
                (market,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None


def _fetch_memory_snapshots(market: str | None = None) -> list[dict[str, Any]]:
    from psycopg2.extras import RealDictCursor
    from app.db import get_connection

    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            if market:
                cursor.execute(
                    """
                    SELECT timestamp, market, market_regime, alignment, conflict_level,
                        confidence, decision_state, scenario_name, snapshot_payload
                    FROM market_memory
                    WHERE market = %s
                    ORDER BY market ASC, timestamp ASC, id ASC
                    """,
                    (market,),
                )
            else:
                cursor.execute(
                    """
                    SELECT timestamp, market, market_regime, alignment, conflict_level,
                        confidence, decision_state, scenario_name, snapshot_payload
                    FROM market_memory
                    ORDER BY market ASC, timestamp ASC, id ASC
                    """
                )
            return [dict(row) for row in cursor.fetchall()]


def _timeframe_context(market_intelligence: dict[str, Any]) -> dict[str, str]:
    hierarchy = (market_intelligence.get("timeframe_hierarchy") or {}).get("hierarchy") or {}
    if hierarchy:
        return {
            timeframe: str(node.get("state") or "Insufficient Structure")
            for timeframe, node in hierarchy.items()
        }
    return {
        timeframe: _memory_state(payload.get("structure_state"))
        for timeframe, payload in (market_intelligence.get("timeframes") or {}).items()
    }


def _memory_state(value: Any) -> str:
    text = str(value or "").upper().replace(" ", "_")
    if text in {"TRENDING_BULLISH", "BULLISH_TREND", "BULLISH_CONTINUATION", "BULLISH_CHAIN_ALIGNED"}:
        return "Bullish Trend"
    if text in {"TRENDING_BEARISH", "BEARISH_TREND", "BEARISH_CONTINUATION", "BEARISH_CHAIN_ALIGNED"}:
        return "Bearish Trend"
    if "BULLISH_PULLBACK" in text:
        return "Bullish Pullback"
    if "BEARISH_PULLBACK" in text:
        return "Bearish Pullback"
    if "BULLISH_TRANSITION" in text:
        return "Bullish Transition"
    if "BEARISH_TRANSITION" in text:
        return "Bearish Transition"
    if "CONFLICT" in text:
        return "Conflicted"
    if "BULLISH" in text and "TRANSITION" in text:
        return "Bullish Transition"
    if "BEARISH" in text and "TRANSITION" in text:
        return "Bearish Transition"
    return "Neutral"


def _alignment_label(alignment: dict[str, Any]) -> str:
    dominant = str(alignment.get("dominant_bias") or "").upper()
    if "BULLISH" in dominant:
        return "Bullish"
    if "BEARISH" in dominant:
        return "Bearish"
    return "Neutral"


def _sorted_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        snapshots,
        key=lambda item: (
            str(item.get("market", "")),
            _parse_time(item.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc),
        ),
    )


def _group_by_market(snapshots: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[str(snapshot.get("market", "UNKNOWN"))].append(snapshot)
    return grouped


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _transition_percent(
    transitions: dict[str, dict[str, int]],
    source: str,
    destination: str,
) -> int:
    row = transitions.get(source, {})
    total = sum(row.values())
    if total <= 0:
        return 0
    return int(round((row.get(destination, 0) / total) * 100))
