import json
import unittest

from score_llm_event_extractor_v3_5 import parse_batch


def item(evidence, relevance="none", assets=None):
    return {
        "item_id": "1",
        "btc_relevance": relevance,
        "event_type": "other",
        "affected_assets": [] if assets is None else assets,
        "direction": "unclear",
        "severity": 0.0,
        "reported_surprise": 0.0,
        "expected_horizon": "unknown",
        "confidence": 0.1,
        "evidence_span": evidence,
    }


class EvidenceFallbackTests(unittest.TestCase):
    def test_exact_evidence_is_not_flagged(self):
        expected = [{"item_id": "1", "headline_id": "a" * 64, "headline": "Bitcoin rises"}]
        parsed = parse_batch(json.dumps({"results": [item("Bitcoin")]}), expected, "ordinal_item_id")
        self.assertFalse(parsed[0]["evidence_fallback"])
        self.assertEqual(parsed[0]["evidence_span"], "Bitcoin")

    def test_absent_evidence_uses_full_frozen_headline_and_flag(self):
        headline = "Ripple co-founder Jed McCaleb adds space station building to resume"
        expected = [{"item_id": "1", "headline_id": "b" * 64, "headline": headline}]
        parsed = parse_batch(json.dumps({"results": [item("Bitcoin")]}), expected, "ordinal_item_id")
        self.assertTrue(parsed[0]["evidence_fallback"])
        self.assertEqual(parsed[0]["evidence_span"], headline)

    def test_corrupt_source_quote_uses_full_frozen_headline_and_flag(self):
        headline = "Fidelity will �shift� retail customers into crypto soon � Galaxy CEO"
        expected = [{"item_id": "1", "headline_id": "c" * 64, "headline": headline}]
        parsed = parse_batch(
            json.dumps({"results": [item("shift’ retail customers into crypto")]}),
            expected,
            "ordinal_item_id",
        )
        self.assertTrue(parsed[0]["evidence_fallback"])
        self.assertEqual(parsed[0]["evidence_span"], headline)


if __name__ == "__main__":
    unittest.main()
