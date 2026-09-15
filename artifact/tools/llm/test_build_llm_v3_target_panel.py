import unittest

from build_llm_v3_target_panel import BarSeries, raw_targets


class LlmV3TargetPanelTest(unittest.TestCase):
    def test_targets_use_delayed_entry_and_each_horizon(self):
        step = 4 * 60 * 60 * 1000
        rows = [
            [0, 100, 101, 99, 100, 1, 100],
            [step, 110, 112, 108, 111, 1, 100],
            [2 * step, 120, 125, 107, 121, 1, 100],
            [3 * step, 130, 132, 129, 131, 1, 100],
            [4 * step, 140, 142, 139, 141, 1, 100],
        ]
        result = raw_targets(BarSeries(rows), cutoff_ms=0, delay_hours=4, horizons=(4, 12))
        self.assertAlmostEqual(result["h4_return"], 120 / 110 - 1)
        self.assertAlmostEqual(result["h12_return"], 140 / 110 - 1)
        self.assertAlmostEqual(result["h12_max_adverse_excursion"], 107 / 110 - 1)

    def test_missing_bar_rejects_record(self):
        step = 4 * 60 * 60 * 1000
        rows = [[step, 100, 101, 99, 100, 1, 100], [3 * step, 102, 103, 101, 102, 1, 100]]
        self.assertIsNone(raw_targets(BarSeries(rows), 0, 4, (8,)))


if __name__ == "__main__":
    unittest.main()
