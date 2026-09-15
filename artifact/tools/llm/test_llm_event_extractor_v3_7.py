import json
import unittest

from score_llm_event_extractor_v3_7 import canonicalize_btc_asset, parse_batch


def item(assets, evidence="MakerDAO revenue tumbles 86% on Ether and Wrapped BTC woes"):
    return {
        "item_id": "1",
        "btc_relevance": "direct",
        "event_type": "market_commentary",
        "affected_assets": assets,
        "direction": "negative",
        "severity": 0.9,
        "reported_surprise": 0.0,
        "expected_horizon": "unknown",
        "confidence": 0.9,
        "evidence_span": evidence,
    }


class WrappedBtcAliasCanonicalizationTests(unittest.TestCase):
    def test_wrapped_btc_alias_allowlist(self):
        expected = {
            "Wrapped BTC": "BTC",
            "  wrapped   btc ": "BTC",
            "WBTC": "BTC",
            "Wrapped Bitcoin": "Bitcoin",
            "Wrapped Bitcoin (WBTC)": "Bitcoin",
            "WBTC (Wrapped Bitcoin)": "BTC",
            "Wrapped Bitcoin/WBTC": "Bitcoin",
            "WBTC/Wrapped Bitcoin": "BTC",
        }
        for source, canonical in expected.items():
            with self.subTest(source=source):
                self.assertEqual(canonicalize_btc_asset(source), canonical)

    def test_failed_v3_6_full_batch_alias_now_parses(self):
        headline = "MakerDAO revenue tumbles 86% on Ether and Wrapped BTC woes"
        expected = [{"item_id": "1", "headline_id": "a" * 64, "headline": headline}]
        parsed = parse_batch(
            json.dumps({"results": [item(["MakerDAO", "Ether", "Wrapped BTC"])]}),
            expected,
            "ordinal_item_id",
        )
        self.assertEqual(parsed[0]["btc_relevance"], "direct")
        self.assertEqual(parsed[0]["affected_assets"], ["MakerDAO", "Ether", "BTC"])
        self.assertEqual(parsed[0]["direction"], "negative")
        self.assertFalse(parsed[0]["evidence_fallback"])

    def test_unlisted_wrapped_asset_still_fails_direct_btc_contract(self):
        headline = "Synthetic Wrapped Ether volumes jump"
        expected = [{"item_id": "1", "headline_id": "b" * 64, "headline": headline}]
        with self.assertRaisesRegex(ValueError, "direct BTC relevance"):
            parse_batch(
                json.dumps({"results": [item(["Wrapped Ether"], "Synthetic Wrapped Ether volumes jump")]}),
                expected,
                "ordinal_item_id",
            )


if __name__ == "__main__":
    unittest.main()
