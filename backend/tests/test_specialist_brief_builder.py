import unittest

from app.services.specialist_brief_builder import (
    FORBIDDEN_EXECUTION_TERMS,
    build_delivery_planning_brief,
    build_final_review_brief,
    build_market_intelligence_brief,
    build_requirement_brief,
    build_risk_governance_brief,
    build_system_readiness_brief,
    format_specialist_brief_text,
    is_raw_label_repetition,
)


def context():
    return {
        "analysis_scope": "MCX",
        "mcx": {
            "instrument": "NATURALGAS",
            "source": "TWELVEDATA",
            "data_age": "8m",
            "session": "London Session",
            "labels": [
                {"label": "CHOCH_BULLISH", "confidence": 0.78},
                {"label": "BOS_BULLISH", "confidence": 0.62},
                {"label": "BOS_BEARISH", "confidence": 0.60},
            ],
        },
        "multi_timeframe": {
            "regime": "BULLISH_PULLBACK",
            "structure_confidence": 0.64,
            "decision": {
                "state": "WATCH",
                "next_validation": "15m and 1H must either realign or confirm deterioration.",
            },
            "alignment": {
                "alignment_score": 0.52,
                "conflict_level": "Medium",
            },
            "scenarios": {
                "primary_scenario": {"name": "Bullish Continuation", "probability": 63},
                "secondary_scenario": {"name": "Bearish Transition", "probability": 24},
            },
            "timeframe_hierarchy": {
                "dominant_context": "Higher timeframe bullish, lower timeframe corrective",
                "hierarchy_conflict": "Medium",
                "scenario_bias": "15m and 1H alignment",
            },
            "evolution": {
                "has_previous": True,
                "summary": "15m shifted corrective while 4H remains stable.",
            },
            "memory": {"status": "recorded"},
            "validation_triggers": {
                "bullish_validation": [
                    "15m structure realigns with 1H",
                    "higher timeframe regime remains stable",
                ],
                "bearish_validation": [
                    "1H shifts bearish",
                    "4H support weakens",
                ],
                "wait_conditions": [
                    "timeframes remain conflicted",
                    "freshness degrades",
                ],
            },
        },
    }


class SpecialistBriefBuilderTests(unittest.TestCase):
    def test_each_specialist_returns_different_content(self):
        payloads = [
            build_requirement_brief(context()),
            build_market_intelligence_brief(context()),
            build_system_readiness_brief(context()),
            build_risk_governance_brief(context()),
            build_delivery_planning_brief(context()),
            build_final_review_brief(context()),
        ]
        rendered = [format_specialist_brief_text(item) for item in payloads]
        self.assertEqual(len(set(rendered)), 6)

    def test_raw_smc_labels_are_supporting_not_primary(self):
        brief = build_market_intelligence_brief(context())
        rendered = format_specialist_brief_text(brief)
        first_lines = "\n".join(rendered.splitlines()[:5])
        self.assertNotIn("CHOCH_BULLISH", first_lines)
        self.assertLessEqual(len(brief["supporting_signals"]), 3)
        self.assertTrue(is_raw_label_repetition("CHOCH_BULLISH confidence 78%\nBOS_BULLISH confidence 62%\nBOS_BEARISH confidence 60%"))

    def test_final_review_contains_hypotheses(self):
        brief = build_final_review_brief(context())
        self.assertIn("dominant_hypothesis", brief)
        self.assertIn("alternative_hypothesis", brief)
        self.assertIn("why_not_confirmed", brief)

    def test_delivery_contains_validation_roadmap(self):
        brief = build_delivery_planning_brief(context())
        self.assertEqual(brief["state"], "Validation Plan")
        self.assertTrue(brief["bullish_continuation_conditions"])
        self.assertTrue(brief["bearish_continuation_conditions"])
        self.assertTrue(brief["wait_conditions"])

    def test_risk_and_readiness_are_distinct(self):
        risk = build_risk_governance_brief(context())
        readiness = build_system_readiness_brief(context())
        self.assertIn("risk_reason", risk)
        self.assertEqual(readiness["freshness"], "8m")
        self.assertEqual(readiness["session"], "London Session")
        self.assertEqual(readiness["data_source"], "TWELVEDATA")

    def test_advisory_only_and_forbidden_terms(self):
        briefs = [
            build_requirement_brief(context()),
            build_market_intelligence_brief(context()),
            build_system_readiness_brief(context()),
            build_risk_governance_brief(context()),
            build_delivery_planning_brief(context()),
            build_final_review_brief(context()),
        ]
        for brief in briefs:
            rendered = format_specialist_brief_text(brief).lower()
            self.assertIn("advisory_only", rendered)
            for term in FORBIDDEN_EXECUTION_TERMS:
                self.assertNotRegex(rendered, rf"\b{term}\b")


if __name__ == "__main__":
    unittest.main()
