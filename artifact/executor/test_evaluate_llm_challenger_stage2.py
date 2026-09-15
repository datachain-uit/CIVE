import unittest

from evaluate_llm_challenger_stage2 import evaluate


class ChallengerStage2Test(unittest.TestCase):
    def fixtures(self):
        config = {
            "experiment_id": "test",
            "candidate": {"digest": "digest"},
            "frozen_input_contract": {"prompt_version": "v1", "prompt_hash": "hash"},
            "stage2_only_if_stage1_passes": {
                "minimum_observations": 1000,
                "minimum_long_rule_observations": 100,
                "required": {
                    "schema_errors": 0,
                    "pearson_score_forward_return_95_ci_lower_bound_gt": 0.0,
                    "long_minus_flat_mean_bps_95_ci_lower_bound_gt": 0.0,
                },
            },
        }
        full_run = {
            "model_digest": "digest",
            "prompt_version": "v1",
            "prompt_hash": "hash",
            "records": [{}] * 2927,
            "summary": {"errors": 0},
        }
        calibration = {
            "overall": {"observations": 1110, "long_rule": {"observations": 200}},
            "uncertainty": {
                "pearson_score_forward_return_95_ci": [0.01, 0.10],
                "long_minus_flat_mean_bps_95_ci": [1.0, 20.0],
            },
        }
        return config, full_run, calibration

    def test_pass_requires_both_positive_lower_bounds(self):
        config, full_run, calibration = self.fixtures()
        result = evaluate(config, {"passed": True}, full_run, calibration)
        self.assertTrue(result["passed"])
        self.assertFalse(result["trading_backtest_consulted"])

    def test_zero_crossing_stops_before_backtest(self):
        config, full_run, calibration = self.fixtures()
        calibration["uncertainty"]["pearson_score_forward_return_95_ci"][0] = -0.01
        result = evaluate(config, {"passed": True}, full_run, calibration)
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "stage2-fail-stop-before-repeat-or-backtest")


if __name__ == "__main__":
    unittest.main()
