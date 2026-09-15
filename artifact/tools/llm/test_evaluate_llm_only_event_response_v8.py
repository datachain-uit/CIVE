import unittest

from evaluate_llm_only_event_response_v8 import fold_indices
from evaluate_llm_only_event_conditioned_v7 import assert_llm_only_feature_names


class EventResponseGateV8Tests(unittest.TestCase):
    def test_fold_indices_are_temporal_and_purged(self):
        records = [
            {"decision_at": "2023-12-31T20:00:00+00:00"},
            {"decision_at": "2024-01-01T00:00:00+00:00"},
            {"decision_at": "2024-01-01T04:00:00+00:00"},
            {"decision_at": "2024-01-01T08:00:00+00:00"},
        ]
        fold = {
            "train_end": "2023-12-31T20:00:00+00:00",
            "valid_start": "2024-01-01T04:00:00+00:00",
            "valid_end": "2024-01-01T08:00:00+00:00",
        }
        train, valid = fold_indices(records, fold)
        self.assertEqual(train, [0])
        self.assertEqual(valid, [2, 3])

    def test_feature_guard_accepts_v8_names(self):
        assert_llm_only_feature_names([
            "llm_sentiment_signed_mean",
            "llm_event_impact::liquidation_leverage",
            "llm_event_impact::etf_institutional_flow",
        ])

    def test_feature_guard_rejects_technical_input(self):
        with self.assertRaises(ValueError):
            assert_llm_only_feature_names(["llm_sentiment_signed_mean", "llm_volume_zscore"])


if __name__ == "__main__":
    unittest.main()
