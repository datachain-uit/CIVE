import json
import unittest

from score_llm_event_extractor_v3_6 import canonicalize_btc_asset, parse_batch


def item(assets):
    return {
        "item_id": "1",
        "btc_relevance": "direct",
        "event_type": "market_commentary",
        "affected_assets": assets,
        "direction": "positive",
        "severity": 0.4,
        "reported_surprise": 0.0,
        "expected_horizon": "unknown",
        "confidence": 0.9,
        "evidence_span": "Traditional Investors Can Gain Crypto Exposure",
    }


class BtcAliasCanonicalizationTests(unittest.TestCase):
    def test_closed_alias_allowlist(self):
        expected = {
            "BTC": "BTC",
            "Bitcoin": "Bitcoin",
            "Bitcoin (BTC)": "Bitcoin",
            "  bitcoin   (BTC) ": "Bitcoin",
            "BTC (Bitcoin)": "BTC",
            "Bitcoin/BTC": "Bitcoin",
            "BTC/Bitcoin": "BTC",
        }
        for source, canonical in expected.items():
            with self.subTest(source=source):
                self.assertEqual(canonicalize_btc_asset(source), canonical)

    def test_unlisted_bitcoin_derivative_is_not_canonicalized(self):
        self.assertEqual(canonicalize_btc_asset("Wrapped Bitcoin (WBTC)"), "Wrapped Bitcoin (WBTC)")

    def test_failed_v3_5_alias_batch_now_parses_without_changing_classification(self):
        headline = "3 Ways Traditional Investors Can Gain Crypto Exposure"
        expected = [{"item_id": "1", "headline_id": "a" * 64, "headline": headline}]
        parsed = parse_batch(
            json.dumps({"results": [item(["Bitcoin (BTC)"])]}),
            expected,
            "ordinal_item_id",
        )
        self.assertEqual(parsed[0]["btc_relevance"], "direct")
        self.assertEqual(parsed[0]["affected_assets"], ["Bitcoin"])
        self.assertEqual(parsed[0]["direction"], "positive")
        self.assertFalse(parsed[0]["evidence_fallback"])

    def test_unlisted_derivative_still_fails_direct_btc_contract(self):
        headline = "3 Ways Traditional Investors Can Gain Crypto Exposure"
        expected = [{"item_id": "1", "headline_id": "b" * 64, "headline": headline}]
        with self.assertRaisesRegex(ValueError, "direct BTC relevance"):
            parse_batch(
                json.dumps({"results": [item(["Wrapped Bitcoin (WBTC)"])]}),
                expected,
                "ordinal_item_id",
            )


if __name__ == "__main__":
    unittest.main()
