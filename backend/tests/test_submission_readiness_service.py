import json
import unittest
from unittest.mock import patch

from app.services.submission_readiness_service import (
    COMPONENT_WEIGHTS,
    build_submission_readiness_snapshot,
    calculate_readiness_score,
    contains_secret_like_value,
    readiness_state,
    sanitize_readiness_payload,
)


def ready_components():
    return {
        name: {"status": "ready", "summary": f"{name} ready"}
        for name in COMPONENT_WEIGHTS
    }


def context_payload():
    return {
        "analysis_scope": "MCX",
        "mcx": {
            "instrument": "NATURALGAS",
            "candle": {"close": 289.5},
            "smc_labels": [{"label": "CHOCH_BEARISH"}],
        },
        "multi_timeframe": {
            "timeframes": {"1m": {}, "4H": {}},
            "scenarios": {"primary_scenario": {"name": "Bearish Transition"}},
            "timeframe_hierarchy": {"hierarchy": {"4H": {}}},
            "memory": {"status": "recorded"},
            "decision": {"state": "WAIT"},
        },
    }


def market_snapshot():
    return {
        "mcx": {
            "candle": {"close": 289.5},
            "smc_labels": [{"label": "CHOCH_BEARISH"}],
        },
        "forex": {
            "candle": {"close": 4215.0},
            "smc_labels": [{"label": "BOS_BULLISH"}],
        },
    }


def governance_payload():
    return {
        "evidence_count": 18,
        "specialist_findings": [{"response_source": "persisted"}],
        "missing_evidence_warnings": [],
    }


def audit_payload():
    return {
        "safety_status": "ADVISORY_ONLY",
        "stages": [{"stage": f"stage-{index}", "status": "available"} for index in range(10)],
        "warnings": [],
    }


def persisted_payload():
    return {
        "market": "MCX",
        "instrument": "NATURALGAS",
        "workflow_run_id": "wf-ready",
        "specialists": [{"specialist_name": "Market Intelligence Agent"}],
        "final_review": {"specialist_name": "Final Review Agent"},
    }


class FakeWorkflowService:
    def build_quasar_context(self, analysis_scope="MCX"):
        return context_payload()


class SubmissionReadinessServiceTests(unittest.TestCase):
    def test_readiness_score_calculation(self):
        self.assertEqual(calculate_readiness_score(ready_components()), 100)
        components = ready_components()
        components["feed_lifecycle"]["status"] = "warning"
        components["band_specialists"]["status"] = "not_ready"
        expected = 100 - COMPONENT_WEIGHTS["band_specialists"] - COMPONENT_WEIGHTS["feed_lifecycle"] / 2
        self.assertEqual(calculate_readiness_score(components), int(expected))

    def test_ready_state(self):
        self.assertEqual(readiness_state(95, []), "READY")

    def test_ready_with_warnings_state(self):
        self.assertEqual(readiness_state(82, ["feed_lifecycle is ready with warnings."]), "READY_WITH_WARNINGS")

    def test_not_ready_state(self):
        self.assertEqual(readiness_state(70, []), "NOT_READY")

    def test_critical_warning_handling(self):
        self.assertEqual(readiness_state(96, ["Critical: audit trace unavailable."]), "READY_WITH_WARNINGS")

    def test_safety_status_enforced_in_snapshot(self):
        payload = self._build_patched_snapshot()
        self.assertEqual(payload["safety_status"], "ADVISORY_ONLY")

    def test_no_secret_leakage(self):
        sanitized = sanitize_readiness_payload(
            {"nested": {"api_key": "secret-value"}, "safe": "visible"}
        )
        self.assertEqual(sanitized["nested"]["api_key"], "[REDACTED]")
        self.assertFalse(contains_secret_like_value({"safe": "visible"}))
        self.assertNotIn("secret-value", json.dumps(sanitized))

    def test_missing_component_handling(self):
        payload = self._build_patched_snapshot(
            latest_market={},
            governance={},
            audit={},
            persisted={"specialists": [], "final_review": {}},
        )
        self.assertEqual(payload["readiness_state"], "NOT_READY")
        self.assertIn("Critical: no market data available.", payload["warnings"])
        self.assertEqual(payload["components"]["data_layer"]["status"], "not_ready")

    def test_evidence_counts_propagated(self):
        payload = self._build_patched_snapshot()
        self.assertEqual(payload["evidence"]["governance_evidence_count"], 18)
        self.assertEqual(payload["evidence"]["audit_stage_count"], 10)
        self.assertEqual(payload["evidence"]["specialist_response_count"], 1)
        self.assertEqual(payload["evidence"]["latest_workflow_run_id"], "wf-ready")

    def _build_patched_snapshot(
        self,
        latest_market=None,
        governance=None,
        audit=None,
        persisted=None,
    ):
        with patch(
            "app.services.submission_readiness_service._fetch_latest_market_snapshot",
            return_value=market_snapshot() if latest_market is None else latest_market,
        ), patch(
            "app.services.submission_readiness_service._workflow_service",
            return_value=FakeWorkflowService(),
        ), patch(
            "app.services.submission_readiness_service._get_workflow_details",
            return_value={"workflow_id": "wf-ready", "steps": []},
        ), patch(
            "app.services.submission_readiness_service._get_latest_specialist_responses",
            return_value=persisted_payload() if persisted is None else persisted,
        ), patch(
            "app.services.submission_readiness_service._build_governance_evidence",
            return_value=governance_payload() if governance is None else governance,
        ), patch(
            "app.services.submission_readiness_service._band_config_status",
            return_value={"configured": True, "mode": "band"},
        ), patch(
            "app.services.submission_readiness_service._build_decision_trace",
            return_value=audit_payload() if audit is None else audit,
        ), patch(
            "app.services.submission_readiness_service._get_twelvedata_ingestion_status",
            return_value={"worker_alive": True},
        ), patch(
            "app.services.submission_readiness_service._get_zerodha_ingestion_status",
            return_value={"worker_alive": True},
        ):
            return build_submission_readiness_snapshot()


if __name__ == "__main__":
    unittest.main()
