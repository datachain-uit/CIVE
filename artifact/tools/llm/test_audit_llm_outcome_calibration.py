import unittest

from audit_llm_outcome_calibration import audit, block_bootstrap


class LlmOutcomeCalibrationTest(unittest.TestCase):
    def test_uses_delayed_open_and_exact_future_horizon(self):
        scores = {"records": [{
            "information_date": "2020-01-01", "available_at": "2020-01-02T00:00:00+00:00",
            "status": "success", "score": 0.5, "confidence": 0.8,
        }]}
        execution = 1577937600000  # 2020-01-02 04:00 UTC
        bars = [
            [execution, 100, 999, 1, 500, 0, 0],
            [execution + 24 * 60 * 60 * 1000, 110, 110, 110, 110, 0, 0],
        ]
        result = audit(scores, bars)
        self.assertEqual(result["overall"]["observations"], 1)
        self.assertAlmostEqual(result["overall"]["long_rule"]["mean_forward_return_pct"], 10.0)

    def test_block_bootstrap_is_seeded_and_reports_intervals(self):
        rows = [
            {"score": 0.5 if index % 2 else 0.0, "confidence": 0.8,
             "forward_return": 0.01 if index % 2 else -0.01}
            for index in range(20)
        ]
        first = block_bootstrap(rows, 0.3, 0.7, block_days=3, samples=100, seed=7)
        second = block_bootstrap(rows, 0.3, 0.7, block_days=3, samples=100, seed=7)
        self.assertEqual(first, second)
        self.assertEqual(len(first["long_minus_flat_mean_bps_95_ci"]), 2)


if __name__ == "__main__":
    unittest.main()
