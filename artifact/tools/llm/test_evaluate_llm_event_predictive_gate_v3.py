import unittest

import numpy as np

from evaluate_llm_event_predictive_gate_v3 import (
    block_bootstrap,
    causal_metadata_features,
    event_features,
    normalized_headline,
    ridge_predict,
)


class EventPredictiveGateTests(unittest.TestCase):
    def test_normalized_headline_is_deterministic(self):
        self.assertEqual(normalized_headline("  BTC   Rallies  "), "btc rallies")

    def test_metadata_recurrence_uses_only_prior_days(self):
        records = {
            "2026-01-01": [{
                "headline_id": "a", "headline": "Bitcoin rallies", "source_domain": "source",
                "coin_type": "Bitcoin", "available_at": "2026-01-02T00:00:00+00:00",
                "published_at": "2026-01-01T12:00:00+00:00", "position_in_day": 0,
            }],
            "2026-01-02": [{
                "headline_id": "b", "headline": "Bitcoin rallies", "source_domain": "source",
                "coin_type": "Bitcoin", "available_at": "2026-01-03T00:00:00+00:00",
                "published_at": "2026-01-02T12:00:00+00:00", "position_in_day": 0,
            }, {
                "headline_id": "c", "headline": "Ether falls", "source_domain": "source",
                "coin_type": "Ethereum", "available_at": "2026-01-03T00:00:00+00:00",
                "published_at": "2026-01-02T13:00:00+00:00", "position_in_day": 1,
            }],
        }
        features, kept_ids, deduplicated = causal_metadata_features(
            records, ["2026-01-01", "2026-01-02"], ["source"], ["Bitcoin", "Ethereum"], 30,
        )
        self.assertEqual(features["2026-01-01"]["meta_exact_recurrence_30d_fraction"], 0.0)
        self.assertEqual(deduplicated, 1)
        self.assertEqual(features["2026-01-02"]["meta_article_count"], 1.0)

    def test_event_features_use_only_kept_semantic_records(self):
        inputs = {
            "a": {"headline_id": "a", "information_date": "2026-01-01"},
            "b": {"headline_id": "b", "information_date": "2026-01-01"},
        }
        base = {
            "status": "success", "error": None, "information_date": "2026-01-01",
            "btc_relevance": "direct", "event_type": "other", "direction": "positive",
            "expected_horizon": "24h", "reported_surprise": 0.2, "confidence": 0.8,
            "affected_assets": ["BTC"], "evidence_fallback": False,
        }
        events = [
            {**base, "headline_id": "a", "severity": 0.2},
            {**base, "headline_id": "b", "severity": 1.0},
        ]
        features = event_features(
            inputs, events, ["2026-01-01"], {"2026-01-01": {"a"}},
            ["direct"], ["other"], ["positive"], ["24h"],
        )
        self.assertAlmostEqual(features["2026-01-01"]["event_severity_mean"], 0.2)
    def test_ridge_standardization_is_train_only(self):
        x_train = np.asarray([[0.0], [1.0], [2.0]])
        y_train = np.asarray([0.0, 1.0, 2.0])
        first = ridge_predict(x_train, y_train, np.asarray([[3.0]]), 1.0)
        second = ridge_predict(x_train, y_train, np.asarray([[3.0], [3000.0]]), 1.0)
        self.assertAlmostEqual(first[0], second[0])

    def test_block_bootstrap_is_seeded_and_paired(self):
        fold = {
            "y": np.asarray([0.0, 1.0, 2.0, 3.0]),
            "metadata": np.asarray([1.0, 2.0, 3.0, 4.0]),
            "event": np.asarray([0.0, 1.0, 2.0, 3.0]),
        }
        left = block_bootstrap([fold], 100, 2, 7)
        right = block_bootstrap([fold], 100, 2, 7)
        self.assertEqual(left, right)
        self.assertGreater(left["paired_delta_mse_95_ci"][0], 0)


if __name__ == "__main__":
    unittest.main()
