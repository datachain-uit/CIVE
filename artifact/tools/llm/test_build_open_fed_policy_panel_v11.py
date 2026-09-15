import unittest
from build_open_fed_policy_panel_v11 import features, next_4h_open_ms


class PanelTest(unittest.TestCase):
    def test_strict_next_boundary(self):
        self.assertEqual(next_4h_open_ms("2024-01-01T04:00:00+00:00"), next_4h_open_ms("2024-01-01T04:00:01+00:00"))

    def test_features_are_llm_named(self):
        row = {"generic_direction": -1, "generic_intensity": .5, "policy_direction": 1, "policy_intensity": .4, "surprise_language": .2, "systemic_scope": .3, "confidence": .8, "event_type": "other"}
        generic, event = features(row)
        self.assertTrue(all(key.startswith("llm_") for key in generic | event))
        self.assertEqual(event["llm_policy_signed_intensity"], .4)


if __name__ == "__main__": unittest.main()
