import unittest

from app.services.timeframe_hierarchy_engine import generate_timeframe_hierarchy


def snapshot(states):
    return {
        "timeframes": {
            timeframe: {
                "structure_state": state,
                "confidence": confidence,
                "primary_signal": signal,
            }
            for timeframe, state, confidence, signal in states
        }
    }


class TimeframeHierarchyEngineTests(unittest.TestCase):
    def test_bullish_hierarchy_alignment(self):
        result = generate_timeframe_hierarchy(
            snapshot(
                [
                    ("4H", "BULLISH_CONTINUATION", 0.82, "BOS_BULLISH"),
                    ("1H", "BULLISH_CONTINUATION", 0.76, "BOS_BULLISH"),
                    ("15m", "BULLISH_TRANSITION", 0.66, "CHOCH_BULLISH"),
                    ("5m", "BULLISH_TRANSITION", 0.58, "CHOCH_BULLISH"),
                    ("1m", "BULLISH_TRANSITION", 0.51, "FVG_BULLISH"),
                ]
            )
        )
        self.assertEqual(result["hierarchy"]["4H"]["role"], "Primary regime anchor")
        self.assertEqual(result["hierarchy"]["4H"]["influence"], "Dominant")
        self.assertEqual(result["hierarchy_conflict"], "Low")
        self.assertEqual(
            result["dominant_context"],
            "Bullish structure aligned across hierarchy",
        )

    def test_higher_bullish_lower_corrective(self):
        result = generate_timeframe_hierarchy(
            snapshot(
                [
                    ("4H", "BULLISH_CONTINUATION", 0.84, "BOS_BULLISH"),
                    ("1H", "BULLISH_CONTINUATION", 0.74, "BOS_BULLISH"),
                    ("15m", "BEARISH_TRANSITION", 0.68, "CHOCH_BEARISH"),
                    ("5m", "BEARISH_TRANSITION", 0.57, "CHOCH_BEARISH"),
                    ("1m", "BEARISH_TRANSITION", 0.48, "FVG_BEARISH"),
                ]
            )
        )
        self.assertEqual(
            result["dominant_context"],
            "Higher timeframe bullish, lower timeframe corrective",
        )
        self.assertEqual(result["hierarchy_conflict"], "High")
        self.assertEqual(
            result["hierarchy"]["15m"]["relationship_to_parent"],
            "Counter-trend correction",
        )
        self.assertIn("Bullish Continuation", result["scenario_bias"])

    def test_higher_bearish_lower_corrective(self):
        result = generate_timeframe_hierarchy(
            snapshot(
                [
                    ("4H", "BEARISH_CONTINUATION", 0.84, "BOS_BEARISH"),
                    ("1H", "BEARISH_CONTINUATION", 0.74, "BOS_BEARISH"),
                    ("15m", "BULLISH_TRANSITION", 0.68, "CHOCH_BULLISH"),
                    ("5m", "BULLISH_TRANSITION", 0.57, "CHOCH_BULLISH"),
                    ("1m", "BULLISH_TRANSITION", 0.48, "FVG_BULLISH"),
                ]
            )
        )
        self.assertEqual(
            result["dominant_context"],
            "Higher timeframe bearish, lower timeframe corrective",
        )
        self.assertEqual(result["hierarchy_conflict"], "High")
        self.assertIn("Bearish Continuation", result["scenario_bias"])

    def test_insufficient_higher_timeframe(self):
        result = generate_timeframe_hierarchy(
            snapshot(
                [
                    ("4H", "INSUFFICIENT", 0.0, ""),
                    ("1H", "INSUFFICIENT", 0.0, ""),
                    ("15m", "BULLISH_TRANSITION", 0.48, "CHOCH_BULLISH"),
                    ("5m", "BULLISH_TRANSITION", 0.44, "CHOCH_BULLISH"),
                    ("1m", "RANGING", 0.31, ""),
                ]
            )
        )
        self.assertEqual(
            result["dominant_context"],
            "Higher timeframe context is neutral or insufficient",
        )
        self.assertEqual(
            result["hierarchy"]["1H"]["relationship_to_parent"],
            "Insufficient parent-child evidence",
        )
        self.assertEqual(result["scenario_bias"], "No clear hierarchy scenario bias")


if __name__ == "__main__":
    unittest.main()
