import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from technical_cross_asset_execution import (
    _amihud_shock_ratios,
    _point_in_time_liquid_universe,
    _tiered_maintenance_margin,
)
from technical_bybit_lifecycle_universe import _membership
from technical_bybit_lifecycle_execution import _targets


class TechnicalExecutionHelpersTest(unittest.TestCase):
    def test_liquidity_selection_does_not_see_future_volume(self):
        volumes = {
            "A": [10, 10, 10, 0],
            "B": [5, 5, 5, 1_000_000],
            "C": [1, 1, 1, 0],
        }
        self.assertEqual(
            _point_in_time_liquid_universe(volumes, index=2, lookback_days=3, universe_size=1),
            {"A"},
        )

    def test_tiered_margin_uses_rate_and_deduction(self):
        tiers = [
            {"risk_limit_value": 100_000, "maintenance_margin_rate": 0.005, "maintenance_margin_deduction": 0},
            {"risk_limit_value": 200_000, "maintenance_margin_rate": 0.01, "maintenance_margin_deduction": 500},
        ]
        self.assertEqual(_tiered_maintenance_margin(50_000, tiers), 250)
        self.assertEqual(_tiered_maintenance_margin(150_000, tiers), 1_000)
        with self.assertRaises(ValueError):
            _tiered_maintenance_margin(250_000, tiers)

    def test_amihud_shock_uses_only_current_and_prior_closed_days(self):
        closes = {"A": [100, 101, 102, 103, 120, 121]}
        volumes = {"A": [1000, 1000, 1000, 1000, 1000, 1]}
        ratios = _amihud_shock_ratios(closes, volumes, {"A"}, index=4, lookback_days=3)
        self.assertGreater(ratios["A"], 10)
        # The future low-volume observation at index 5 must not affect index 4.
        volumes["A"][5] = 1_000_000_000
        self.assertEqual(
            ratios,
            _amihud_shock_ratios(closes, volumes, {"A"}, index=4, lookback_days=3),
        )

    def test_lifecycle_membership_requires_consecutive_history(self):
        day = 86_400_000
        data = {
            "OLD": [[i * day, 1, 1, 1, 1, 1, 100] for i in range(4)],
            "NEW": [
                [day, 1, 1, 1, 1, 1, 10_000],
                [2 * day, 1, 1, 1, 1, 1, 10_000],
                [3 * day, 1, 1, 1, 1, 1, 10_000],
            ],
        }
        schedule, _ = _membership(data, 0, 3 * day, lookback_days=3, universe_size=1)
        self.assertEqual(schedule[2 * day], ["OLD"])
        self.assertEqual(schedule[3 * day], ["NEW"])

    def test_lifecycle_target_exclusion_does_not_remove_btc_regime_reference(self):
        day = 86_400_000
        rows = [[i * day, 1, 2, 0.5, 100 + i, 1, 1000] for i in range(30)]
        manifest = {"daily_membership": {str(20 * day): ["BTCUSDT"]}}
        targets = _targets(manifest, {"BTCUSDT": rows}, 1, 5, {"BTCUSDT"})
        self.assertEqual(targets[21 * day], set())


if __name__ == "__main__":
    unittest.main()
