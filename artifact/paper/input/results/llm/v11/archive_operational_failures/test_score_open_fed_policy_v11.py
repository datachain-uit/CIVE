import unittest

from score_open_fed_policy_v11 import validate


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self.expected = {"event_id": "e1", "text": "Rates increased immediately."}
        self.result = {
            "event_id": "e1", "generic_direction": -0.5, "generic_intensity": 0.8,
            "event_type": "rate_or_balance_sheet", "policy_direction": -1,
            "policy_intensity": 0.9, "surprise_language": 0.2, "systemic_scope": 0.8,
            "confidence": 0.9, "evidence_span": "Rates increased",
        }

    def test_valid(self):
        self.assertEqual(validate(self.result, self.expected)["event_id"], "e1")

    def test_rejects_non_verbatim_evidence(self):
        self.result["evidence_span"] = "rates rose"
        with self.assertRaises(ValueError):
            validate(self.result, self.expected)

    def test_rejects_out_of_range(self):
        self.result["policy_direction"] = 2
        with self.assertRaises(ValueError):
            validate(self.result, self.expected)


if __name__ == "__main__":
    unittest.main()
