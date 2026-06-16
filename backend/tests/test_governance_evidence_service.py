import unittest
from unittest.mock import patch

from app.services.governance_evidence_service import (
    build_governance_evidence,
    governance_evidence_references_text,
)


def workflow_details(response_text="Market structure reviewed."):
    return {
        "workflow_id": "wf-test",
        "analysis_scope": "MCX",
        "steps": [
            {
                "agent": "Market Intelligence Agent",
                "summary": "Bullish Pullback",
                "response_text": response_text,
            },
            {
                "agent": "Final Review Agent",
                "summary": "WAIT",
                "response_text": response_text,
            },
        ],
    }


def context():
    return {
        "analysis_scope": "MCX",
        "multi_timeframe": {
            "regime": "BULLISH_PULLBACK",
            "structure_confidence": 0.67,
            "structure_quality": "Moderate",
            "decision": {"state": "WAIT"},
            "alignment": {"conflict_level": "Medium"},
            "timeframes": {
                "4H": {"structure_state": "BULLISH_CONTINUATION"},
                "1H": {"structure_state": "BULLISH_TRANSITION"},
                "15m": {"structure_state": "BEARISH_TRANSITION"},
            },
            "timeframe_hierarchy": {
                "dominant_context": "Higher timeframe bullish, lower timeframe corrective",
                "hierarchy_conflict": "Medium",
            },
            "scenarios": {
                "primary_scenario": {
                    "name": "Bullish Continuation",
                    "probability": 63,
                }
            },
            "evolution": {
                "has_previous": True,
                "summary": "15m shifted bearish while 4H remains bullish.",
            },
            "memory": {"status": "recorded"},
        },
    }


class GovernanceEvidenceServiceTests(unittest.TestCase):
    def test_builds_specialist_evidence(self):
        with patch(
            "app.services.governance_evidence_service.get_latest_specialist_responses"
        ) as latest:
            payload = build_governance_evidence(workflow_details(), context())
        latest.assert_not_called()
        self.assertEqual(payload["workflow_id"], "wf-test")
        self.assertGreaterEqual(payload["evidence_count"], 4)
        market = payload["specialist_findings"][0]
        self.assertEqual(market["specialist"], "Market Intelligence Specialist")
        self.assertEqual(market["finding"], "Bullish Pullback")
        self.assertEqual(market["confidence"], 67)
        self.assertIn("4H", market["supporting_timeframes"])
        self.assertEqual(market["response_source"], "runtime")

    def test_missing_response_warning(self):
        with patch(
            "app.services.governance_evidence_service.get_latest_specialist_responses",
            return_value={"specialists": [], "final_review": {}},
        ):
            payload = build_governance_evidence(workflow_details(response_text=""), context())
        self.assertTrue(payload["missing_evidence_warnings"])

    def test_persisted_response_fallback_removes_missing_response_warning(self):
        payload = build_governance_evidence(
            workflow_details(response_text=""),
            context(),
            persisted_responses={
                "specialists": [
                    {
                        "specialist_name": "Market Intelligence Agent",
                        "finding": "Persisted market finding",
                        "summary": "Persisted market response.",
                    }
                ],
                "final_review": {
                    "specialist_name": "Final Review Agent",
                    "finding": "WAIT",
                    "summary": "Persisted final response.",
                },
            },
        )
        joined = " ".join(payload["missing_evidence_warnings"])
        self.assertNotIn("no captured response text", joined)
        self.assertEqual(payload["specialist_findings"][0]["response_source"], "persisted")

    def test_governance_loads_persisted_fallback_when_runtime_missing(self):
        with patch(
            "app.services.governance_evidence_service.get_latest_specialist_responses",
            return_value={
                "specialists": [
                    {
                        "specialist_name": "Market Intelligence Agent",
                        "finding": "Persisted market finding",
                        "summary": "Persisted market response.",
                    }
                ],
                "final_review": {
                    "specialist_name": "Final Review Agent",
                    "finding": "WAIT",
                    "summary": "Persisted final response.",
                },
            },
        ) as latest:
            payload = build_governance_evidence(workflow_details(response_text=""), context())
        latest.assert_called_once()
        market = payload["specialist_findings"][0]
        self.assertEqual(market["response_source"], "persisted")
        self.assertFalse(payload["missing_evidence_warnings"])

    def test_references_text_includes_sources(self):
        payload = build_governance_evidence(workflow_details(), context())
        text = governance_evidence_references_text(payload)
        self.assertIn("Evidence References:", text)
        self.assertIn("Market Intelligence Specialist", text)
        self.assertIn("Bullish Continuation 63%", text)


if __name__ == "__main__":
    unittest.main()
