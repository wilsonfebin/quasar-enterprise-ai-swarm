import unittest
from unittest.mock import patch

from app.services.specialist_response_store import (
    FINAL_REVIEW_AGENT,
    get_latest_final_review,
    latest_specialist_response_payload,
    sanitize_specialist_payload,
    save_final_review_response,
    save_specialist_response,
    specialist_response_history_payload,
)


def response_row(
    specialist_name="Market Intelligence Agent",
    created_at="2026-06-16T05:00:00+00:00",
    workflow_run_id="wf-1",
):
    return {
        "id": 1,
        "created_at": created_at,
        "workflow_run_id": workflow_run_id,
        "market": "MCX",
        "instrument": "NATURALGAS",
        "specialist_name": specialist_name,
        "finding": "Bullish Pullback",
        "summary": "Market structure review captured.",
        "confidence": 67,
        "evidence_payload": [{"source": "Scenario Engine", "fact": "Bullish Continuation 63%"}],
        "warnings_payload": [],
        "sanitized_response_payload": {
            "message": "captured",
            "specialist_brief": {
                "state": "Validation Plan",
                "dominant_thesis": "Higher timeframe continuation remains the primary thesis.",
                "alternative_thesis": "Transition remains possible if hierarchy weakens.",
                "risk_level": "Medium",
                "validation_conditions": {"wait_conditions": ["timeframes remain conflicted"]},
                "next_validation": "15m and 1H must realign.",
                "response_source": "quasar_brief",
            },
        },
    }


class SpecialistResponseStoreTests(unittest.TestCase):
    def test_save_specialist_response_builds_sanitized_record(self):
        with patch(
            "app.services.specialist_response_store.ensure_specialist_response_table"
        ), patch(
            "app.services.specialist_response_store._insert_specialist_response"
        ) as insert:
            insert.side_effect = lambda record: {**record, "id": 11}
            saved = save_specialist_response(
                workflow_run_id="wf-save",
                market="mcx",
                instrument="naturalgas",
                specialist_name="Market Intelligence Agent",
                finding="Review captured",
                summary="Response text",
                confidence=0.67,
                evidence=[{"source": "Scenario Engine"}],
                warnings=[],
                raw_response_payload={"headers": {"X-API-Key": "secret"}},
            )

        self.assertEqual(saved["market"], "MCX")
        self.assertEqual(saved["instrument"], "NATURALGAS")
        self.assertEqual(saved["confidence"], 67)
        self.assertEqual(saved["sanitized_response_payload"]["headers"], "[REDACTED]")

    def test_save_final_review_response_uses_final_review_agent(self):
        with patch(
            "app.services.specialist_response_store.ensure_specialist_response_table"
        ), patch(
            "app.services.specialist_response_store._insert_specialist_response"
        ) as insert:
            insert.side_effect = lambda record: record
            saved = save_final_review_response(
                workflow_run_id="wf-save",
                market="MCX",
                instrument="NATURALGAS",
                summary="Final review captured.",
            )
        self.assertEqual(saved["specialist_name"], FINAL_REVIEW_AGENT)

    def test_retrieves_latest_responses(self):
        rows = [
            response_row(created_at="2026-06-16T05:00:00+00:00"),
            response_row(created_at="2026-06-16T06:00:00+00:00", workflow_run_id="wf-2"),
            response_row(
                specialist_name=FINAL_REVIEW_AGENT,
                created_at="2026-06-16T06:05:00+00:00",
                workflow_run_id="wf-2",
            ),
        ]
        payload = latest_specialist_response_payload(rows, market="MCX", instrument="NATURALGAS")
        self.assertEqual(payload["workflow_run_id"], "wf-2")
        self.assertEqual(len(payload["specialists"]), 1)
        self.assertEqual(payload["final_review"]["specialist_name"], FINAL_REVIEW_AGENT)
        self.assertEqual(payload["specialists"][0]["state"], "Validation Plan")
        self.assertEqual(payload["specialists"][0]["response_source"], "quasar_brief")
        self.assertIn("specialist_brief", payload["specialists"][0])

    def test_retrieves_by_workflow_run_id(self):
        payload = specialist_response_history_payload(
            [response_row(workflow_run_id="wf-history")],
            workflow_run_id="wf-history",
        )
        self.assertEqual(payload["workflow_run_id"], "wf-history")
        self.assertEqual(payload["count"], 1)
        self.assertIn("sanitized_response_payload", payload["responses"][0])

    def test_sanitizes_nested_secrets(self):
        sanitized = sanitize_specialist_payload(
            {
                "Authorization": "secret",
                "nested": {"api_key": "secret", "safe": "visible"},
                "items": [{"access_token": "secret"}],
            }
        )
        self.assertEqual(sanitized["Authorization"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["api_key"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["safe"], "visible")
        self.assertEqual(sanitized["items"][0]["access_token"], "[REDACTED]")

    def test_empty_dataset_payloads(self):
        latest = latest_specialist_response_payload([], market="MCX", instrument="NATURALGAS")
        history = specialist_response_history_payload([])
        self.assertEqual(latest["specialists"], [])
        self.assertEqual(latest["final_review"], {})
        self.assertEqual(history["count"], 0)

    def test_latest_final_review_delegates(self):
        with patch(
            "app.services.specialist_response_store.get_latest_specialist_responses",
            return_value={"final_review": {"finding": "WAIT"}},
        ):
            self.assertEqual(get_latest_final_review()["finding"], "WAIT")


if __name__ == "__main__":
    unittest.main()
