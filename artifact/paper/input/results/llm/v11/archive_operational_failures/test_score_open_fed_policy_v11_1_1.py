import unittest
from score_open_fed_policy_v11_1_1 import validate

class FullValidatorTest(unittest.TestCase):
    def test_delegates_once_and_adds_flag(self):
        text = "The policy statement explicitly increased rates immediately for all banks."
        expected = {"event_id":"e", "text":text}
        result = {"event_id":"e","generic_direction":-1,"generic_intensity":.8,"event_type":"rate_or_balance_sheet","policy_direction":-1,"policy_intensity":.9,"surprise_language":0,"systemic_scope":.8,"confidence":.9,"evidence_span":text}
        self.assertFalse(validate(result, expected)["evidence_alignment_fallback"])

if __name__ == "__main__": unittest.main()
