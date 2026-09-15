import unittest

from evaluate_llm_challenger_fail_fast import evaluate


class ChallengerFailFastTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "experiment_id": "candidate-v1",
            "candidate": {"digest": "digest"},
            "frozen_input_contract": {"prompt_version": "v1", "prompt_hash": "hash"},
            "stage1_operational_gate": {
                "expected_information_sets": 108,
                "required": {"schema_success_each_run": 108},
            },
        }

    def payload(self, statuses):
        return {
            "model_digest": "digest",
            "prompt_version": "v1",
            "prompt_hash": "hash",
            "records": [{"status": status} for status in statuses],
        }

    def test_one_error_makes_perfect_schema_gate_unreachable(self):
        result = evaluate(self.config, self.payload(["success", "error"]))
        self.assertFalse(result["passed"])
        self.assertEqual(result["stage1_partial_run"]["maximum_possible_schema_success_if_completed"], 107)
        self.assertEqual(result["status"], "stage1-fail-fast-stop-before-completing-run1")

    def test_rejects_partial_run_without_error(self):
        with self.assertRaises(ValueError):
            evaluate(self.config, self.payload(["success", "success"]))

    def test_rejects_digest_mismatch(self):
        payload = self.payload(["error"])
        payload["model_digest"] = "other"
        with self.assertRaises(ValueError):
            evaluate(self.config, payload)


if __name__ == "__main__":
    unittest.main()
