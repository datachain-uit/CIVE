import copy
import unittest

from evaluate_finbert_operational_gate import evaluate


def fixtures():
    config = {
        "experiment_id": "finbert-test",
        "candidate": {"digest": "revision"},
        "frozen_input_contract": {
            "contract_version": "contract-v1",
            "contract_hash": "contract-hash",
        },
        "stage1_operational_gate": {
            "expected_information_sets": 2,
            "required": {
                "schema_success_each_run": 2,
                "headline_count_matches_each_run": 2,
                "exact_score_agreement_min": 2,
                "mean_absolute_score_difference_max": 0.0,
                "max_absolute_score_difference_max": 0.0,
            },
        },
    }
    run = {
        "model_digest": "revision",
        "prompt_version": "contract-v1",
        "prompt_hash": "contract-hash",
        "summary": {"success": 2, "errors": 0, "headline_count_matches": 2},
    }
    audit = {
        "model_digest": "revision",
        "prompt_version": "contract-v1",
        "prompt_hash": "contract-hash",
        "information_sets": 2,
        "exact_score_agreement": 2,
        "mean_absolute_score_difference": 0.0,
        "max_absolute_score_difference": 0.0,
    }
    return config, audit, run, copy.deepcopy(run)


class FinBertOperationalGateTest(unittest.TestCase):
    def test_passes_exact_repeated_run(self):
        config, audit, left, right = fixtures()
        result = evaluate(config, audit, left, right)
        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], "stage1-pass-full-calibration-authorized")

    def test_fails_headline_count_mismatch(self):
        config, audit, left, right = fixtures()
        right["summary"]["headline_count_matches"] = 1
        result = evaluate(config, audit, left, right)
        self.assertFalse(result["passed"])

    def test_rejects_revision_drift(self):
        config, audit, left, right = fixtures()
        right["model_digest"] = "different"
        with self.assertRaises(ValueError):
            evaluate(config, audit, left, right)


if __name__ == "__main__":
    unittest.main()
