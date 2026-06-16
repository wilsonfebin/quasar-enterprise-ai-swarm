from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from typing import Any


SECRET_MARKERS = [
    "X-API-Key",
    "Authorization",
    "access_token",
    "api_key",
    "api-key",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify durable Band specialist response persistence."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--market", default="MCX")
    parser.add_argument("--instrument", default="NATURALGAS")
    parser.add_argument(
        "--run-workflow",
        action="store_true",
        help="Call /agents/band/run-quasar-workflow before verification.",
    )
    parser.add_argument(
        "--reset-runtime",
        action="store_true",
        help="Call /agents/workflow/reset before fallback checks.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    market = args.market.upper()
    instrument = args.instrument.upper()
    analysis_scope = "FOREX" if market == "FOREX" or instrument == "XAUUSD" else "MCX"

    print(f"Verifying specialist persistence for {market} {instrument}")
    health = request_json("GET", f"{base_url}/health")
    assert_equal(health.get("status"), "healthy", "backend health")

    if args.run_workflow:
        workflow = request_json(
            "POST",
            f"{base_url}/agents/band/run-quasar-workflow?analysis_scope={analysis_scope}",
            timeout=180,
        )
        assert_true(workflow.get("success"), f"workflow success: {workflow}")
        assert_equal(workflow.get("status"), "completed", "workflow completion")
        time.sleep(1)

    latest = request_json(
        "GET",
        endpoint(
            base_url,
            "/agents/specialists/latest",
            market=market,
            instrument=instrument,
        ),
    )
    assert_no_secret_leak(latest, "latest specialist responses")
    specialists = latest.get("specialists") or []
    final_review = latest.get("final_review") or {}
    workflow_run_id = latest.get("workflow_run_id") or ""
    assert_true(specialists, "latest specialist list is non-empty")
    assert_true(final_review, "latest final review exists")
    assert_true(workflow_run_id, "workflow_run_id is present")
    assert_equal(latest.get("market"), market, "latest market")
    assert_equal(latest.get("instrument"), instrument, "latest instrument")
    for item in specialists + [final_review]:
        assert_true(item.get("created_at"), f"{item.get('specialist_name')} created_at")

    history = request_json(
        "GET",
        endpoint(
            base_url,
            "/agents/specialists/history",
            workflow_run_id=workflow_run_id,
            market=market,
            instrument=instrument,
        ),
    )
    assert_no_secret_leak(history, "specialist history")
    assert_true(history.get("count", 0) >= len(specialists), "history response count")
    response_names = {
        str(item.get("specialist_name") or "")
        for item in history.get("responses", [])
    }
    assert_true("Final Review Agent" in response_names, "final review included in history")

    if args.reset_runtime:
        request_json("POST", f"{base_url}/agents/workflow/reset")

    governance = request_json("GET", f"{base_url}/agents/governance/evidence")
    assert_no_secret_leak(governance, "governance evidence")
    findings = governance.get("specialist_findings") or []
    assert_true(findings, "governance specialist findings")
    assert_true(
        any(item.get("response_source") == "persisted" for item in findings),
        "governance uses persisted fallback",
    )
    warnings_text = " ".join(governance.get("missing_evidence_warnings") or [])
    assert_true(
        "no captured response text" not in warnings_text.lower(),
        "governance has no false missing-response warning",
    )
    assert_true(governance.get("evidence_count", 0) > 0, "governance evidence count")

    audit = request_json(
        "GET",
        endpoint(
            base_url,
            "/agents/audit/decision-trace/latest",
            market=market,
            instrument=instrument,
        ),
    )
    assert_no_secret_leak(audit, "decision audit trace")
    assert_equal(audit.get("safety_status"), "ADVISORY_ONLY", "audit safety status")
    stages = {item.get("stage"): item for item in audit.get("stages", [])}
    assert_equal(
        stages.get("Band Specialist Reviews", {}).get("status"),
        "available",
        "specialist review stage",
    )
    assert_equal(
        stages.get("Final Specialist Review", {}).get("status"),
        "available",
        "final review stage",
    )
    audit_summary = stages.get("Band Specialist Reviews", {}).get("summary", "")
    assert_true(
        "persisted Band specialist responses" in audit_summary,
        "audit mentions persisted fallback",
    )
    audit_warnings = " ".join(audit.get("warnings") or [])
    assert_true(
        "No captured Band specialist responses are available yet." not in audit_warnings,
        "audit has no false missing-response warning",
    )

    print("Specialist persistence verification passed.")
    print(
        json.dumps(
            {
                "workflow_run_id": workflow_run_id,
                "specialists": len(specialists),
                "history_count": history.get("count", 0),
                "governance_response_sources": sorted(
                    {item.get("response_source") for item in findings}
                ),
                "audit_specialist_stage": stages.get("Band Specialist Reviews", {}).get("status"),
            },
            indent=2,
        )
    )
    return 0


def endpoint(base_url: str, path: str, **query: str) -> str:
    clean_query = {key: value for key, value in query.items() if value}
    return f"{base_url}{path}?{urllib.parse.urlencode(clean_query)}"


def request_json(method: str, url: str, timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def assert_true(condition: Any, label: str) -> None:
    if not condition:
        raise AssertionError(f"Verification failed: {label}")


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"Verification failed: {label}; expected {expected!r}, got {actual!r}"
        )


def assert_no_secret_leak(payload: Any, label: str) -> None:
    text = json.dumps(payload, sort_keys=True)
    for marker in SECRET_MARKERS:
        if marker in text and "[REDACTED]" not in text:
            raise AssertionError(f"Verification failed: possible secret marker in {label}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
