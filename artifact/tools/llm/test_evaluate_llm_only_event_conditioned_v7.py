import unittest

import numpy as np

from evaluate_llm_only_event_conditioned_v7 import (
    assert_llm_only_feature_names,
    block_bootstrap,
    llm_feature_sets,
    ridge_predict,
    unique_ids_by_date,
)


class LlmOnlyEventConditionedV7Tests(unittest.TestCase):
    def test_feature_guard_rejects_market_or_technical_features(self):
        with self.assertRaises(ValueError):
            assert_llm_only_feature_names(["llm_sentiment", "btc_return_24h"])
        with self.assertRaises(ValueError):
            assert_llm_only_feature_names(["llm_price_direction"])
        assert_llm_only_feature_names(["llm_event_type_fraction::regulation"])
        assert_llm_only_feature_names(["llm_event_impact::etf_institutional_flow"])

    def test_global_duplicate_is_kept_only_once(self):
        inputs = [
            {"information_date": "2026-01-01", "available_at": "2026-01-01T00:00:00+00:00", "position_in_day": 0, "headline": "BTC rises", "headline_id": "a"},
            {"information_date": "2026-01-02", "available_at": "2026-01-02T00:00:00+00:00", "position_in_day": 0, "headline": "  btc RISES ", "headline_id": "b"},
            {"information_date": "2026-01-02", "available_at": "2026-01-02T01:00:00+00:00", "position_in_day": 1, "headline": "ETF filing", "headline_id": "c"},
        ]
        kept, duplicates = unique_ids_by_date(inputs, ["2026-01-01", "2026-01-02"])
        self.assertEqual(duplicates, 1)
        self.assertEqual(kept["2026-01-02"], {"c"})

    def test_event_conditioning_distinguishes_event_types(self):
        inputs = {
            "a": {"headline_id": "a", "information_date": "2026-01-01"},
            "b": {"headline_id": "b", "information_date": "2026-01-02"},
        }
        base = {
            "status": "success", "error": None, "btc_relevance": "direct", "direction": "positive",
            "severity": 0.8, "reported_surprise": 0.5, "expected_horizon": "24h", "confidence": 0.9,
        }
        events = [
            {**base, "headline_id": "a", "information_date": "2026-01-01", "event_type": "regulation"},
            {**base, "headline_id": "b", "information_date": "2026-01-02", "event_type": "other"},
        ]
        sentiment, conditioned = llm_feature_sets(
            inputs, events, ["2026-01-01", "2026-01-02"], {"2026-01-01": {"a"}, "2026-01-02": {"b"}},
            ["direct"], ["regulation", "other"], ["positive", "negative", "mixed", "unclear"], ["24h"],
        )
        self.assertEqual(sentiment["2026-01-01"], sentiment["2026-01-02"])
        self.assertNotEqual(conditioned["2026-01-01"], conditioned["2026-01-02"])

    def test_ridge_standardization_is_train_only(self):
        x_train = np.asarray([[0.0], [1.0], [2.0]])
        y_train = np.asarray([0.0, 1.0, 2.0])
        first = ridge_predict(x_train, y_train, np.asarray([[3.0]]), 1.0)
        second = ridge_predict(x_train, y_train, np.asarray([[3.0], [3000.0]]), 1.0)
        self.assertAlmostEqual(first[0], second[0])

    def test_block_bootstrap_is_seeded_and_paired(self):
        fold = {
            "y": np.asarray([0.0, 1.0, 2.0, 3.0]),
            "sentiment": np.asarray([1.0, 2.0, 3.0, 4.0]),
            "event": np.asarray([0.0, 1.0, 2.0, 3.0]),
        }
        left = block_bootstrap([fold], 100, 2, 7)
        right = block_bootstrap([fold], 100, 2, 7)
        self.assertEqual(left, right)
        self.assertGreater(left["paired_delta_mse_95_ci"][0], 0)


if __name__ == "__main__":
    unittest.main()
