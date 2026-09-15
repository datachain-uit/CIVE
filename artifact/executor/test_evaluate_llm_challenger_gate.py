import unittest

from evaluate_llm_challenger_gate import evaluate


class ChallengerGateTest(unittest.TestCase):
    def fixtures(self):
        config = {
            "experiment_id": "test",
            "candidate": {"model": "candidate", "digest": "digest"},
            "frozen_input_contract": {"prompt_version": "v1", "prompt_hash": "hash"},
            "stage1_operational_gate": {
                "expected_information_sets": 2,
                "required": {
                    "schema_success_each_run": 2,
                    "exact_score_agreement_min": 2,
                    "long_flat_action_agreements_min": 2,
                    "mean_absolute_score_difference_max": 0.01,
                    "max_absolute_score_difference_max": 0.1,
                },
            },
        }
        run = {
            "model_digest": "digest",
            "prompt_version": "v1",
            "prompt_hash": "hash",
            "summary": {"success": 2, "errors": 0},
        }
        audit = {
            "model_digest": "digest",
            "prompt_version": "v1",
            "prompt_hash": "hash",
            "information_sets": 2,
            "exact_score_agreement": 2,
            "long_flat_action_agreements": 2,
            "mean_absolute_score_difference": 0.0,
            "max_absolute_score_difference": 0.0,
        }
        return config, audit, run

    def test_all_requirements_pass(self):
        config, audit, run = self.fixtures()
        result = evaluate(config, audit, run, run)
        self.assertTrue(result["passed"])
        self.assertFalse(result["market_outcomes_consulted"])
        self.assertEqual(result["status"], "stage1-pass-full-calibration-authorized")

    def test_one_failed_requirement_stops(self):
        config, audit, run = self.fixtures()
        audit["long_flat_action_agreements"] = 1
        result = evaluate(config, audit, run, run)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["long_flat_action_agreements"]["passed"])
        self.assertEqual(result["status"], "stage1-fail-stop-before-full-inference")


if __name__ == "__main__":
    unittest.main()
