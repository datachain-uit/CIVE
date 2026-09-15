import unittest

from build_llm_multisource_information_sets import (
    BarSeries, feature_distance, market_features, retrieve_cases,
)


class MultisourceInformationSetsTest(unittest.TestCase):
    def test_market_features_ignore_unfinished_bar(self):
        step = 4 * 60 * 60 * 1000
        rows = [[index * step, 100, 100, 100, 100 + index, 1, 1000 + index]
                for index in range(182)]
        cutoff = 181 * step
        baseline = market_features(BarSeries(rows), cutoff)
        rows[181][4] = 1_000_000
        changed = market_features(BarSeries(rows), cutoff)
        self.assertEqual(baseline, changed)

    def test_retrieval_only_uses_outcomes_known_by_cutoff(self):
        current = {"btc_return_24h": 0.01}
        history = [
            {"information_date": "2020-01-01", "features": {"btc_return_24h": 0.011},
             "outcome_at_ms": 99, "forward_return": 0.02, "headline_excerpt": "known"},
            {"information_date": "2020-01-02", "features": {"btc_return_24h": 0.0101},
             "outcome_at_ms": 101, "forward_return": -0.50, "headline_excerpt": "future"},
        ]
        cases = retrieve_cases(current, history, cutoff_ms=100, maximum=3)
        self.assertEqual([item["information_date"] for item in cases], ["2020-01-01"])

    def test_distance_uses_fixed_scales(self):
        left = {"btc_return_24h": 0.00, "cross_asset_breadth_24h": 0.5}
        right = {"btc_return_24h": 0.05, "cross_asset_breadth_24h": 0.5}
        self.assertAlmostEqual(feature_distance(left, right), 2 ** -0.5)


if __name__ == "__main__":
    unittest.main()
