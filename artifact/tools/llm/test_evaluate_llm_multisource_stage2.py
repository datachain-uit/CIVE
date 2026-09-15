import unittest

from evaluate_llm_multisource_stage2 import evaluate


class MultisourceStage2GateTest(unittest.TestCase):
    def test_uses_predeclared_expected_record_count(self):
        config = {
            "experiment_id": "test",
            "candidate": {"digest": "d"},
            "frozen_input_contract": {"prompt_version": "p", "prompt_hash": "h", "sha256": "i"},
            "stage2_only_if_stage1_passes": {
                "expected_full_records": 2, "minimum_observations": 2,
                "minimum_long_rule_observations": 1,
                "required": {"schema_errors": 0,
                             "pearson_score_forward_return_95_ci_lower_bound_gt": 0,
                             "long_minus_flat_mean_bps_95_ci_lower_bound_gt": 0},
            },
        }
        full = {"model_digest": "d", "prompt_version": "p", "prompt_hash": "h",
                "input_sha256": "i", "records": [{}, {}], "summary": {"errors": 0}}
        calibration = {"overall": {"observations": 2, "long_rule": {"observations": 1}},
                       "uncertainty": {"pearson_score_forward_return_95_ci": [0.1, 0.2],
                                       "long_minus_flat_mean_bps_95_ci": [1, 2]}}
        result = evaluate(config, {"passed": True}, full, calibration)
        self.assertTrue(result["passed"])
        self.assertEqual(result["checks"]["full_records"]["required"], 2)


if __name__ == "__main__":
    unittest.main()
