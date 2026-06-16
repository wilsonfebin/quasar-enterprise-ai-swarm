import unittest
from datetime import datetime, timedelta, timezone

from app.services.scenario_engine import generate_market_scenarios


def snapshot(
    regime,
    states,
    conflict="LOW",
    confidence=0.78,
    alignment=0.74,
    freshness_minutes=10,
):
    now = datetime.now(timezone.utc) - timedelta(minutes=freshness_minutes)
    return {
        "regime": regime,
        "structure_confidence": confidence,
        "alignment_score": alignment,
        "freshness_minutes": freshness_minutes,
        "structure_quality": "Strong",
        "decision": {"state": "WATCH"},
        "alignment": {
            "conflict_level": conflict,
            "dominant_bias": "BULLISH" if "BULLISH" in regime else "BEARISH",
            "alignment_score": alignment,
        },
        "timeframes": {
            timeframe: {
                "structure_state": state,
                "latest_candle": {"timestamp": now.isoformat()},
            }
            for timeframe, state in states.items()
        },
    }


class ScenarioEngineTests(unittest.TestCase):
    def assert_probability_total(self, scenarios):
        total = sum(
            scenarios[key]["probability"]
            for key in ("primary_scenario", "secondary_scenario", "neutral_scenario")
        )
        self.assertEqual(total, 100)

    def test_bullish_trend_alignment(self):
        scenarios = generate_market_scenarios(
            snapshot(
                "TRENDING_BULLISH",
                {
                    "4H": "BULLISH_CONTINUATION",
                    "1H": "BULLISH_CONTINUATION",
                    "15m": "BULLISH_CONTINUATION",
                    "5m": "BULLISH_CONTINUATION",
                    "1m": "BULLISH_CONTINUATION",
                },
            )
        )
        self.assertEqual(scenarios["primary_scenario"]["name"], "Bullish Continuation")
        self.assert_probability_total(scenarios)

    def test_bearish_trend_alignment(self):
        scenarios = generate_market_scenarios(
            snapshot(
                "TRENDING_BEARISH",
                {
                    "4H": "BEARISH_CONTINUATION",
                    "1H": "BEARISH_CONTINUATION",
                    "15m": "BEARISH_CONTINUATION",
                    "5m": "BEARISH_CONTINUATION",
                    "1m": "BEARISH_CONTINUATION",
                },
            )
        )
        self.assertEqual(scenarios["primary_scenario"]["name"], "Bearish Continuation")
        self.assert_probability_total(scenarios)

    def test_bullish_pullback_with_bullish_higher_timeframe(self):
        scenarios = generate_market_scenarios(
            snapshot(
                "BULLISH_PULLBACK",
                {
                    "4H": "BULLISH_CONTINUATION",
                    "1H": "BULLISH_CONTINUATION",
                    "15m": "BULLISH_TRANSITION",
                    "5m": "BEARISH_TRANSITION",
                    "1m": "BEARISH_TRANSITION",
                },
                conflict="MEDIUM",
            )
        )
        self.assertEqual(scenarios["primary_scenario"]["name"], "Bullish Continuation")
        self.assert_probability_total(scenarios)

    def test_bearish_pullback_with_bearish_higher_timeframe(self):
        scenarios = generate_market_scenarios(
            snapshot(
                "BEARISH_PULLBACK",
                {
                    "4H": "BEARISH_CONTINUATION",
                    "1H": "BEARISH_CONTINUATION",
                    "15m": "BEARISH_TRANSITION",
                    "5m": "BULLISH_TRANSITION",
                    "1m": "BULLISH_TRANSITION",
                },
                conflict="MEDIUM",
            )
        )
        self.assertEqual(scenarios["primary_scenario"]["name"], "Bearish Continuation")
        self.assert_probability_total(scenarios)

    def test_high_conflict_market(self):
        scenarios = generate_market_scenarios(
            snapshot(
                "CONFLICTED",
                {
                    "4H": "BULLISH_TRANSITION",
                    "1H": "BEARISH_TRANSITION",
                    "15m": "BEARISH_TRANSITION",
                    "5m": "BULLISH_TRANSITION",
                    "1m": "CONFLICTED",
                },
                conflict="HIGH",
                confidence=0.42,
                alignment=0.18,
            )
        )
        self.assertIn(
            scenarios["primary_scenario"]["name"],
            {"Wait / No Clear Scenario", "Range Continuation"},
        )
        self.assert_probability_total(scenarios)

    def test_stale_market_data(self):
        scenarios = generate_market_scenarios(
            snapshot(
                "TRENDING_BULLISH",
                {
                    "4H": "BULLISH_CONTINUATION",
                    "1H": "BULLISH_CONTINUATION",
                    "15m": "BULLISH_CONTINUATION",
                    "5m": "BULLISH_CONTINUATION",
                    "1m": "BULLISH_CONTINUATION",
                },
                freshness_minutes=720,
            )
        )
        self.assertGreaterEqual(
            scenarios["neutral_scenario"]["probability"],
            10,
        )
        self.assertLess(scenarios["scenario_confidence"], 0.75)
        self.assert_probability_total(scenarios)


if __name__ == "__main__":
    unittest.main()
