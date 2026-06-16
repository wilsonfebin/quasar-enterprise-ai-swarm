from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


FINAL_REVIEW_AGENT = "Final Review Agent"

SECRET_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "authorization",
    "x-api-key",
    "x-kite-version",
    "token",
    "secret",
    "password",
    "auth",
    "headers",
}


def ensure_specialist_response_table() -> None:
    from app.db import get_connection

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS specialist_responses (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    workflow_run_id TEXT NOT NULL,
                    market TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    specialist_name TEXT NOT NULL,
                    finding TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    confidence NUMERIC NOT NULL DEFAULT 0,
                    evidence_payload JSONB NOT NULL DEFAULT '[]'::jsonb,
                    warnings_payload JSONB NOT NULL DEFAULT '[]'::jsonb,
                    sanitized_response_payload JSONB NOT NULL DEFAULT '{}'::jsonb
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_specialist_responses_latest
                ON specialist_responses (market, instrument, specialist_name, created_at DESC)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_specialist_responses_workflow
                ON specialist_responses (workflow_run_id, created_at ASC)
                """
            )
        connection.commit()


def save_specialist_response(
    *,
    workflow_run_id: str,
    market: str,
    instrument: str,
    specialist_name: str,
    finding: str = "",
    summary: str = "",
    confidence: int | float = 0,
    evidence: list[dict[str, Any]] | dict[str, Any] | None = None,
    warnings: list[str] | list[dict[str, Any]] | None = None,
    raw_response_payload: dict[str, Any] | list[Any] | None = None,
) -> dict[str, Any]:
    ensure_specialist_response_table()
    record = _build_record(
        workflow_run_id=workflow_run_id,
        market=market,
        instrument=instrument,
        specialist_name=specialist_name,
        finding=finding,
        summary=summary,
        confidence=confidence,
        evidence=evidence,
        warnings=warnings,
        raw_response_payload=raw_response_payload,
    )
    return _insert_specialist_response(record)


def save_final_review_response(
    *,
    workflow_run_id: str,
    market: str,
    instrument: str,
    finding: str = "Final Specialist Review",
    summary: str = "",
    confidence: int | float = 0,
    evidence: list[dict[str, Any]] | dict[str, Any] | None = None,
    warnings: list[str] | list[dict[str, Any]] | None = None,
    raw_response_payload: dict[str, Any] | list[Any] | None = None,
) -> dict[str, Any]:
    return save_specialist_response(
        workflow_run_id=workflow_run_id,
        market=market,
        instrument=instrument,
        specialist_name=FINAL_REVIEW_AGENT,
        finding=finding,
        summary=summary,
        confidence=confidence,
        evidence=evidence,
        warnings=warnings,
        raw_response_payload=raw_response_payload,
    )


def get_latest_specialist_responses(
    market: str | None = None,
    instrument: str | None = None,
) -> dict[str, Any]:
    ensure_specialist_response_table()
    rows = _fetch_response_rows(market=market, instrument=instrument)
    return latest_specialist_response_payload(rows, market=market, instrument=instrument)


def get_latest_final_review(
    market: str | None = None,
    instrument: str | None = None,
) -> dict[str, Any]:
    latest = get_latest_specialist_responses(market=market, instrument=instrument)
    return latest.get("final_review") or {}


def get_responses_by_workflow_run_id(
    workflow_run_id: str | None = None,
    market: str | None = None,
    instrument: str | None = None,
) -> dict[str, Any]:
    ensure_specialist_response_table()
    rows = _fetch_response_rows(
        workflow_run_id=workflow_run_id,
        market=market,
        instrument=instrument,
        chronological=True,
    )
    return specialist_response_history_payload(
        rows,
        workflow_run_id=workflow_run_id,
        market=market,
        instrument=instrument,
    )


def sanitize_specialist_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if str(key).lower() in SECRET_KEYS:
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_specialist_payload(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_specialist_payload(item) for item in value]
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def latest_specialist_response_payload(
    rows: list[dict[str, Any]],
    market: str | None = None,
    instrument: str | None = None,
) -> dict[str, Any]:
    latest_by_specialist: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: _parse_time(item.get("created_at")), reverse=True):
        specialist_name = str(row.get("specialist_name") or "")
        if specialist_name and specialist_name not in latest_by_specialist:
            latest_by_specialist[specialist_name] = _public_record(row)

    specialists = [
        record
        for name, record in latest_by_specialist.items()
        if name != FINAL_REVIEW_AGENT
    ]
    specialists.sort(key=lambda item: str(item.get("specialist_name") or ""))
    final_review = latest_by_specialist.get(FINAL_REVIEW_AGENT) or {}
    reference = final_review or (specialists[0] if specialists else {})
    return {
        "market": str(market or reference.get("market") or ""),
        "instrument": str(instrument or reference.get("instrument") or ""),
        "workflow_run_id": str(reference.get("workflow_run_id") or ""),
        "specialists": specialists,
        "final_review": final_review,
    }


def specialist_response_history_payload(
    rows: list[dict[str, Any]],
    workflow_run_id: str | None = None,
    market: str | None = None,
    instrument: str | None = None,
) -> dict[str, Any]:
    records = [_public_record(row, include_payload=True) for row in rows]
    return {
        "workflow_run_id": str(workflow_run_id or (records[0].get("workflow_run_id") if records else "") or ""),
        "market": str(market or (records[0].get("market") if records else "") or ""),
        "instrument": str(instrument or (records[0].get("instrument") if records else "") or ""),
        "count": len(records),
        "responses": records,
    }


def _build_record(
    *,
    workflow_run_id: str,
    market: str,
    instrument: str,
    specialist_name: str,
    finding: str,
    summary: str,
    confidence: int | float,
    evidence: list[dict[str, Any]] | dict[str, Any] | None,
    warnings: list[str] | list[dict[str, Any]] | None,
    raw_response_payload: dict[str, Any] | list[Any] | None,
) -> dict[str, Any]:
    return {
        "workflow_run_id": str(workflow_run_id or ""),
        "market": str(market or "").upper(),
        "instrument": str(instrument or "").upper(),
        "specialist_name": str(specialist_name or ""),
        "finding": str(finding or ""),
        "summary": str(summary or ""),
        "confidence": _numeric_confidence(confidence),
        "evidence_payload": sanitize_specialist_payload(evidence or []),
        "warnings_payload": sanitize_specialist_payload(warnings or []),
        "sanitized_response_payload": sanitize_specialist_payload(raw_response_payload or {}),
    }


def _insert_specialist_response(record: dict[str, Any]) -> dict[str, Any]:
    from psycopg2.extras import Json, RealDictCursor
    from app.db import get_connection

    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO specialist_responses (
                    workflow_run_id, market, instrument, specialist_name, finding,
                    summary, confidence, evidence_payload, warnings_payload,
                    sanitized_response_payload
                )
                VALUES (
                    %(workflow_run_id)s, %(market)s, %(instrument)s,
                    %(specialist_name)s, %(finding)s, %(summary)s,
                    %(confidence)s, %(evidence_payload)s, %(warnings_payload)s,
                    %(sanitized_response_payload)s
                )
                RETURNING id, created_at
                """,
                {
                    **record,
                    "evidence_payload": Json(record["evidence_payload"]),
                    "warnings_payload": Json(record["warnings_payload"]),
                    "sanitized_response_payload": Json(record["sanitized_response_payload"]),
                },
            )
            inserted = cursor.fetchone()
        connection.commit()
    return {**record, "id": inserted["id"], "created_at": _iso(inserted["created_at"])}


def _fetch_response_rows(
    workflow_run_id: str | None = None,
    market: str | None = None,
    instrument: str | None = None,
    chronological: bool = False,
) -> list[dict[str, Any]]:
    from psycopg2.extras import RealDictCursor
    from app.db import get_connection

    filters = []
    params: dict[str, Any] = {}
    if workflow_run_id:
        filters.append("workflow_run_id = %(workflow_run_id)s")
        params["workflow_run_id"] = workflow_run_id
    if market:
        filters.append("market = %(market)s")
        params["market"] = str(market).upper()
    if instrument:
        filters.append("instrument = %(instrument)s")
        params["instrument"] = str(instrument).upper()
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    sort_direction = "ASC" if chronological else "DESC"
    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"""
                SELECT *
                FROM specialist_responses
                {where_clause}
                ORDER BY created_at {sort_direction}, id {sort_direction}
                LIMIT 500
                """,
                params,
            )
            return [dict(row) for row in cursor.fetchall()]


def _public_record(row: dict[str, Any], include_payload: bool = False) -> dict[str, Any]:
    sanitized_payload = sanitize_specialist_payload(
        row.get("sanitized_response_payload") or {}
    )
    specialist_brief = (
        sanitized_payload.get("specialist_brief")
        if isinstance(sanitized_payload, dict)
        else {}
    )
    if not isinstance(specialist_brief, dict):
        specialist_brief = {}
    record = {
        "id": row.get("id"),
        "created_at": _iso(row.get("created_at")),
        "workflow_run_id": str(row.get("workflow_run_id") or ""),
        "market": str(row.get("market") or ""),
        "instrument": str(row.get("instrument") or ""),
        "specialist_name": str(row.get("specialist_name") or ""),
        "finding": str(row.get("finding") or ""),
        "summary": str(row.get("summary") or ""),
        "confidence": _numeric_confidence(row.get("confidence")),
        "evidence": sanitize_specialist_payload(row.get("evidence_payload") or []),
        "warnings": sanitize_specialist_payload(row.get("warnings_payload") or []),
    }
    for key in (
        "state",
        "dominant_thesis",
        "alternative_thesis",
        "risk_level",
        "validation_conditions",
        "next_validation",
        "response_source",
        "executive_summary",
        "dominant_hypothesis",
        "alternative_hypothesis",
    ):
        if specialist_brief.get(key):
            record[key] = specialist_brief[key]
    if specialist_brief:
        record["specialist_brief"] = specialist_brief
    if include_payload:
        record["sanitized_response_payload"] = sanitized_payload
    return record


def _numeric_confidence(value: Any) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if number <= 1:
        number *= 100
    return max(0, min(100, int(round(number))))


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.replace(tzinfo=timezone.utc).isoformat()
    return str(value or "")
