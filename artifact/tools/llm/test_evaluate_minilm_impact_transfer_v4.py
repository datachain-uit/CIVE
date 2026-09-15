import unittest

from evaluate_minilm_impact_transfer_v4 import daily_impact_features


class ImpactTransferV4Tests(unittest.TestCase):
    def test_daily_features_use_kept_ids_and_validate_all_ids(self):
        inputs = {
            "a": {"headline_id": "a", "information_date": "2023-01-01"},
            "b": {"headline_id": "b", "information_date": "2023-01-01"},
        }
        scores = [
            {"headline_id": "a", "information_date": "2023-01-01", "impact_score": -0.25},
            {"headline_id": "b", "information_date": "2023-01-01", "impact_score": 0.75},
        ]
        result = daily_impact_features(
            scores, inputs, ["2023-01-01"], {"2023-01-01": {"a"}},
        )["2023-01-01"]
        self.assertEqual(result["impact_score_mean"], -0.25)
        self.assertEqual(result["impact_score_abs_mean"], 0.25)
        self.assertEqual(result["impact_score_std"], 0.0)


if __name__ == "__main__":
    unittest.main()
