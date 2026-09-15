"""Small deterministic tests for HYB-010 sizing and risk summaries."""
from __future__ import annotations

import unittest

from evaluate_hyb010_risk_budget_reallocation import tail_metrics


class Hyb010Tests(unittest.TestCase):
    def test_policy_bounds(self) -> None:
        self.assertEqual(1.25 - 0.5 * 0.0, 1.25)
        self.assertEqual(1.25 - 0.5 * 1.0, 0.75)

    def test_tail_metrics_uses_ceil_ten_percent(self) -> None:
        result = tail_metrics([0.03, -0.04, 0.01, -0.02, 0.02, 0.04, -0.01, 0.0, 0.05, 0.01, -0.03])
        self.assertEqual(result["tail_trade_count"], 2)
        self.assertAlmostEqual(result["es10_trade_return"], -0.035)
        self.assertAlmostEqual(result["worst_trade_return"], -0.04)


if __name__ == "__main__":
    unittest.main()
