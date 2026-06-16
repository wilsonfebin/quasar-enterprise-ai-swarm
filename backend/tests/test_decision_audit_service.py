import json
import unittest
from unittest.mock import patch

from app.services.decision_audit_service import (
    build_audit_stage,
    build_decision_trace,
    summarize_hierarchy,
    summarize_market_snapshot,
    summarize_mtf_intelligence,
    summarize_scenario_engine,
)


def workflow(response_text="Specialist response captured.", final_summary="Final review captured."):
    return {
        "workflow_id": "wf-audit",
        "analysis_scope": "MCX",
        "final_summary": final_summary,
        "steps": [
            {
                "agent": "Market Intelligence Agent",
                "status": "completed",
                "response_text": response_text,
                "summary": "Market review complete",
            },
            {
                "agent": "Final Review Agent",
                "status": "completed",
                "response_text": response_text,
                "summary": "Final review complete",
            },
        ],
    }


def context(include_memory=True):
    mtf = {
        "regime": "BEARISH_PULLBACK",
        "structure_confidence": 0.59,
        "structure_quality": "Moderate",
        "decision": {"state": "WAIT"},
        "evolution": {"has_previous": True, "summary": "15m shifted while 4H remained stable."},
        "scenarios": {
            "primary_scenario": {"name": "Bearish Transition", "probability": 44},
            "safety_status": "ADVISORY_ONLY",
        },
        "timeframe_hierarchy": {
            "dominant_context": "Higher timeframe bullish, lower timeframe corrective",
            "hierarchy_conflict": "High",
            "scenario_bias": "Continuation only if tactical structure realigns",
        },
        "timeframes": {"4H": {}, "1H": {}, "15m": {}, "5m": {}, "1m": {}},
    }
    if include_memory:
        mtf["memory"] = {"status": "recorded", "id": 7}
    return {
        "analysis_scope": "MCX",
        "scope_label": "MCX NATURALGAS",
        "mcx": {
            "instrument": "NATURALGAS",
            "source": "ZERODHA",
            "timestamp": "2026-06-16T05:00:00+00:00",
            "data_age": "2m old",
            "candle": {"close": 297.0},
            "labels": [{"label": "CHOCH_BEARISH", "confidence": 0.78}],
        },
        "multi_timeframe": mtf,
    }


def evidence(count=18):
    return {
        "evidence_count": count,
        "specialist_findings": [
            {
                "specialist": "Market Intelligence Specialist",
                "evidence": [{"source": "Scenario Engine", "fact": "Bearish Transition 44%"}],
            }
        ],
        "missing_evidence_warnings": [],
    }


class DecisionAuditServiceTests(unittest.TestCase):
    def test_full_audit_trace_generation(self):
        with patch(
            "app.services.decision_audit_service.get_latest_specialist_responses"
        ) as latest:
            trace = build_decision_trace(workflow(), context(), evidence())
        latest.assert_not_called()
        self.assertEqual(trace["safety_status"], "ADVISORY_ONLY")
        self.assertEqual(trace["decision_state"], "WAIT")
        self.assertEqual(trace["market_regime"], "Bearish Pullback")
        self.assertEqual(trace["scenario"], "Bearish Transition")
        self.assertEqual(len(trace["stages"]), 10)
        self.assertTrue(trace["audit_id"])

    def test_missing_specialist_responses_warn_not_fail(self):
        with patch(
            "app.services.decision_audit_service.get_latest_specialist_responses",
            return_value={"specialists": [], "final_review": {}},
        ):
            trace = build_decision_trace(workflow(response_text="", final_summary=""), context(), evidence())
        self.assertIn("No captured Band specialist responses are available yet.", trace["warnings"])
        self.assertEqual(trace["safety_status"], "ADVISORY_ONLY")

    def test_persisted_specialist_responses_clear_missing_warning(self):
        trace = build_decision_trace(
            workflow(response_text="", final_summary=""),
            context(),
            evidence(),
            persisted_responses={
                "specialists": [
                    {
                        "specialist_name": "Market Intelligence Agent",
                        "summary": "Persisted response.",
                    }
                ],
                "final_review": {
                    "specialist_name": "Final Review Agent",
                    "summary": "Persisted final review.",
                },
            },
        )
        self.assertNotIn("No captured Band specialist responses are available yet.", trace["warnings"])
        review_stage = next(stage for stage in trace["stages"] if stage["stage"] == "Final Specialist Review")
        self.assertEqual(review_stage["status"], "available")

    def test_decision_trace_loads_persisted_fallback_when_runtime_missing(self):
        persisted = {
            "specialists": [
                {
                    "specialist_name": "Market Intelligence Agent",
                    "summary": "Persisted response.",
                }
            ],
            "final_review": {
                "specialist_name": "Final Review Agent",
                "summary": "Persisted final review.",
            },
        }
        with patch(
            "app.services.decision_audit_service.get_latest_specialist_responses",
            return_value=persisted,
        ) as latest:
            trace = build_decision_trace(workflow(response_text="", final_summary=""), context(), evidence())
        latest.assert_called_once()
        specialist_stage = next(stage for stage in trace["stages"] if stage["stage"] == "Band Specialist Reviews")
        self.assertEqual(specialist_stage["status"], "available")
        self.assertIn("persisted Band specialist responses", specialist_stage["summary"])
        self.assertNotIn("No captured Band specialist responses are available yet.", trace["warnings"])

    def test_missing_memory_data(self):
        trace = build_decision_trace(workflow(), context(include_memory=False), evidence())
        memory_stage = next(stage for stage in trace["stages"] if stage["stage"] == "Market Memory")
        self.assertEqual(memory_stage["status"], "missing")
        self.assertIn("Market Memory data is missing.", trace["warnings"])

    def test_band_disabled_and_config_missing(self):
        trace = build_decision_trace(
            workflow(),
            context(),
            evidence(),
            band_status={"enabled": False, "configured": False},
        )
        joined = " ".join(trace["warnings"])
        self.assertIn("Band integration is disabled", joined)
        self.assertIn("Band configuration is missing", joined)

    def test_json_safe_response(self):
        trace = build_decision_trace(workflow(), context(), evidence())
        encoded = json.dumps(trace)
        self.assertIn("audit_id", encoded)

    def test_evidence_count_propagates(self):
        trace = build_decision_trace(workflow(), context(), evidence(count=21))
        self.assertEqual(trace["evidence_count"], 21)
        governance_stage = next(stage for stage in trace["stages"] if stage["stage"] == "Governance Evidence")
        self.assertIn("21 supporting evidence items", governance_stage["summary"])

    def test_secret_redaction(self):
        trace = build_decision_trace(
            workflow_details={**workflow(), "api_key": "secret"},
            context={**context(), "access_token": "secret"},
            governance_evidence={**evidence(), "Authorization": "secret"},
        )
        text = json.dumps(trace)
        self.assertNotIn("secret", text)

    def test_helper_summaries(self):
        self.assertIn("Latest candle captured", summarize_market_snapshot(context()["mcx"]))
        self.assertIn("Bearish Pullback", summarize_mtf_intelligence(context()["multi_timeframe"]))
        self.assertIn("Bearish Transition", summarize_scenario_engine(context()["multi_timeframe"]))
        self.assertIn("Hierarchy", build_audit_stage("Hierarchy", "now", "test", summarize_hierarchy(context()["multi_timeframe"]))["stage"])


if __name__ == "__main__":
    unittest.main()
