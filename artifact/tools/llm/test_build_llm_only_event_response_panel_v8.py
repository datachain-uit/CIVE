import unittest
from datetime import datetime, timezone

from build_llm_only_event_response_panel_v8 import (
    ELIGIBLE_EVENT_TYPES,
    llm_features,
    next_4h_open_ms,
)
from evaluate_llm_only_event_conditioned_v7 import assert_llm_only_feature_names


class EventResponsePanelV8Tests(unittest.TestCase):
    def test_next_open_is_strict_and_utc(self):
        exact = datetime(2026, 1, 1, 4, 0, tzinfo=timezone.utc)
        before = datetime(2026, 1, 1, 3, 59, tzinfo=timezone.utc)
        self.assertEqual(next_4h_open_ms(exact), int(datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc).timestamp() * 1000))
        self.assertEqual(next_4h_open_ms(before), int(exact.timestamp() * 1000))

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            next_4h_open_ms(datetime(2026, 1, 1, 4, 0))

    def test_feature_contract_is_llm_only(self):
        item = {
            "btc_relevance": "direct",
            "event_type": "regulation",
            "direction": "negative",
            "severity": 0.8,
            "reported_surprise": 0.7,
            "confidence": 0.9,
        }
        sentiment, event = llm_features([item])
        assert_llm_only_feature_names(list(sentiment))
        assert_llm_only_feature_names(list(event))
        self.assertGreater(len(event), len(sentiment))
        self.assertAlmostEqual(event["llm_event_impact::regulation"], -0.8 * 0.7 * 0.9)

    def test_commentary_is_not_an_eligible_event_type(self):
        self.assertNotIn("market_commentary", ELIGIBLE_EVENT_TYPES)
        self.assertNotIn("other", ELIGIBLE_EVENT_TYPES)


if __name__ == "__main__":
    unittest.main()
