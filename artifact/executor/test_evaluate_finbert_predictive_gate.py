import unittest
from datetime import datetime, timedelta, timezone

from evaluate_finbert_predictive_gate import (
    evaluate,
    join_forward_returns,
    tercile_difference_bps,
)


class FinBertPredictiveGateTest(unittest.TestCase):
    def test_tercile_difference_uses_equal_extreme_groups(self):
        rows = [
            {"information_date": f"2026-01-{index + 1:02d}", "score": float(index),
             "forward_return": float(index) / 100}
            for index in range(9)
        ]
        difference, top_count, bottom_count = tercile_difference_bps(rows)
        self.assertEqual((top_count, bottom_count), (3, 3))
        self.assertAlmostEqual(difference, 600.0)

    def test_join_forward_returns_uses_four_hour_delay_and_24h_horizon(self):
        available = datetime(2026, 1, 1, tzinfo=timezone.utc)
        execution = available + timedelta(hours=4)
        outcome = execution + timedelta(hours=24)
        bars = [
            [int(execution.timestamp() * 1000), 100.0],
            [int(outcome.timestamp() * 1000), 110.0],
        ]
        payload = {"records": [{
            "status": "success", "available_at": available.isoformat(),
            "information_date": "2025-12-31", "score": 0.2, "confidence": 0.8,
        }]}
        rows = join_forward_returns(payload, bars)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["forward_return"], 0.1)

    def test_rejects_model_revision_drift(self):
        config = {
            "candidate": {"digest": "expected"},
            "frozen_input_contract": {"contract_hash": "hash"},
        }
        scores = {
            "model_digest": "different", "contract_hash": "hash",
            "summary": {"errors": 0}, "records": [],
        }
        with self.assertRaises(ValueError):
            evaluate(config, scores, [])


if __name__ == "__main__":
    unittest.main()
