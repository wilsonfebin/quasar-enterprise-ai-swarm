import unittest
from datetime import datetime, timedelta, timezone

from app.services.market_memory_engine import (
    _should_record_snapshot,
    calculate_failure_scores,
    calculate_persistence_scores,
    calculate_recovery_scores,
    calculate_regime_duration_statistics,
    calculate_transition_statistics,
    get_memory_summary,
)


BASE_TIME = datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc)


def row(hours, regime, market="MCX:NATURALGAS", decision="WATCH", scenario="Range Continuation"):
    return {
        "timestamp": BASE_TIME + timedelta(hours=hours),
        "market": market,
        "market_regime": regime,
        "alignment": "Bullish",
        "conflict_level": "Medium",
        "confidence": 62,
        "decision_state": decision,
        "scenario_name": scenario,
        "snapshot_payload": {},
    }


class MarketMemoryEngineTests(unittest.TestCase):
    def test_empty_dataset_handling(self):
        summary = {
            "regime_statistics": calculate_regime_duration_statistics([], now=BASE_TIME),
            "transition_statistics": calculate_transition_statistics([]),
            "persistence_scores": calculate_persistence_scores([]),
            "recovery_scores": calculate_recovery_scores([]),
            "failure_scores": calculate_failure_scores([]),
            "sample_count": len([]),
        }
        self.assertEqual(summary["sample_count"], 0)
        self.assertEqual(
            summary["regime_statistics"]["Bullish Trend"]["sample_count"],
            0,
        )
        self.assertEqual(summary["transition_statistics"]["Bullish Trend"], {})
        self.assertEqual(
            summary["persistence_scores"]["Bullish Trend"]["persistence_score"],
            0,
        )

    def test_regime_duration_calculation(self):
        snapshots = [
            row(0, "Bullish Trend"),
            row(2, "Bullish Trend"),
            row(5, "Bullish Pullback"),
        ]
        stats = calculate_regime_duration_statistics(
            snapshots,
            now=BASE_TIME + timedelta(hours=8),
        )
        self.assertEqual(stats["Bullish Trend"]["sample_count"], 2)
        self.assertEqual(stats["Bullish Trend"]["average_duration_hours"], 2.5)
        self.assertEqual(stats["Bullish Pullback"]["sample_count"], 1)
        self.assertEqual(stats["Bullish Pullback"]["max_duration_hours"], 3)

    def test_transition_counting(self):
        transitions = calculate_transition_statistics(
            [
                row(0, "Bullish Pullback"),
                row(1, "Bullish Trend"),
                row(2, "Bullish Pullback"),
                row(3, "Bearish Transition"),
            ]
        )
        self.assertEqual(transitions["Bullish Pullback"]["Bullish Trend"], 1)
        self.assertEqual(transitions["Bullish Pullback"]["Bearish Transition"], 1)

    def test_persistence_calculation(self):
        scores = calculate_persistence_scores(
            [
                row(0, "Bullish Trend"),
                row(1, "Bullish Trend"),
                row(2, "Bullish Pullback"),
            ]
        )
        self.assertEqual(scores["Bullish Trend"]["persistence_score"], 50)

    def test_recovery_and_failure_calculation(self):
        snapshots = [
            row(0, "Bullish Pullback"),
            row(1, "Bullish Trend"),
            row(2, "Bullish Pullback"),
            row(3, "Bearish Transition"),
            row(4, "Bearish Pullback"),
            row(5, "Bearish Trend"),
        ]
        recovery = calculate_recovery_scores(snapshots)
        failure = calculate_failure_scores(snapshots)
        self.assertEqual(recovery["Bullish Pullback"]["recovery_to_bullish_trend"], 50)
        self.assertEqual(failure["Bullish Pullback"]["failure_to_bearish_transition"], 50)
        self.assertEqual(recovery["Bearish Pullback"]["recovery_to_bearish_trend"], 100)

    def test_duplicate_snapshot_prevention(self):
        previous = row(
            0,
            "Bullish Pullback",
            decision="WATCH",
            scenario="Bullish Continuation",
        )
        duplicate = row(
            1,
            "Bullish Pullback",
            decision="WATCH",
            scenario="Bullish Continuation",
        )
        changed = row(
            2,
            "Bullish Pullback",
            decision="WAIT",
            scenario="Bullish Continuation",
        )
        self.assertFalse(_should_record_snapshot(previous, duplicate))
        self.assertTrue(_should_record_snapshot(previous, changed))

    def test_global_transitions_do_not_cross_markets(self):
        transitions = calculate_transition_statistics(
            [
                row(0, "Bullish Trend", market="A"),
                row(1, "Bullish Pullback", market="A"),
                row(0, "Bearish Trend", market="B"),
                row(1, "Bearish Pullback", market="B"),
            ]
        )
        self.assertEqual(transitions["Bullish Pullback"], {})
        self.assertEqual(transitions["Bullish Trend"]["Bullish Pullback"], 1)
        self.assertEqual(transitions["Bearish Trend"]["Bearish Pullback"], 1)


if __name__ == "__main__":
    unittest.main()
