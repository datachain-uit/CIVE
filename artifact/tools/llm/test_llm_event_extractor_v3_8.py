import json
import unittest

from score_llm_event_extractor_v3_8 import canonicalize_btc_asset, normalize_assets, parse_batch


def batch_items():
    return [
        {
            "item_id": "1",
            "btc_relevance": "direct",
            "event_type": "liquidation_leverage",
            "affected_assets": ["wrapped BTC", "MakerDAO", "BTC"],
            "direction": "negative",
            "severity": 0.9,
            "reported_surprise": 0.8,
            "expected_horizon": "unknown",
            "confidence": 1.0,
            "evidence_span": "Nexo-labeled address withdraws $153M in Wrapped BTC from MakerDAO",
        },
        {
            "item_id": "2",
            "btc_relevance": "none",
            "event_type": "exchange_security",
            "affected_assets": ["wrapped Ethereum", "wETH"],
            "direction": "negative",
            "severity": 0.1,
            "reported_surprise": 0.0,
            "expected_horizon": "unknown",
            "confidence": 0.3,
            "evidence_span": "wrapped Ethereum",
        },
        {
            "item_id": "3",
            "btc_relevance": "indirect",
            "event_type": "market_commentary",
            "affected_assets": ["Bitcoin", "Ethereum"],
            "direction": "positive",
            "severity": 0.3,
            "reported_surprise": 0.0,
            "expected_horizon": "unknown",
            "confidence": 0.8,
            "evidence_span": "Bitcoin, Ethereum Escape Broader Market Slide",
        },
        {
            "item_id": "4",
            "btc_relevance": "none",
            "event_type": "liquidation_leverage",
            "affected_assets": ["crypto banking platform", "Juno"],
            "direction": "positive",
            "severity": 0.2,
            "reported_surprise": 0.0,
            "expected_horizon": "unknown",
            "confidence": 0.4,
            "evidence_span": "Crypto Banking Platform Juno Raises",
        },
    ]


class AssetCanonicalizationAndDedupeTests(unittest.TestCase):
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

    def test_dedupe_preserves_first_canonical_occurrence_order(self):
        self.assertEqual(
            normalize_assets(["wrapped BTC", "MakerDAO", "BTC", "Bitcoin", "MakerDAO"]),
            ["BTC", "MakerDAO", "Bitcoin"],
        )

    def test_failed_v3_7_full_batch_now_parses(self):
        headlines = [
            "Nexo-labeled address withdraws $153M in Wrapped BTC from MakerDAO",
            "Wrapped Ethereum-based DeFi protocol suffers exploit",
            "Bitcoin, Ethereum Escape Broader Market Slide",
            "Crypto Banking Platform Juno Raises Fresh Capital",
        ]
        expected = [
            {"item_id": str(index + 1), "headline_id": chr(97 + index) * 64, "headline": headline}
            for index, headline in enumerate(headlines)
        ]
        parsed = parse_batch(
            json.dumps({"results": batch_items()}),
            expected,
            "ordinal_item_id",
        )
        self.assertEqual(parsed[0]["affected_assets"], ["BTC", "MakerDAO"])
        self.assertEqual(parsed[0]["btc_relevance"], "direct")
        self.assertEqual(parsed[1]["affected_assets"], ["wrapped Ethereum", "wETH"])
        self.assertTrue(all(item["evidence_span"] in headline for item, headline in zip(parsed, headlines)))

    def test_unlisted_wrapped_asset_still_fails_direct_btc_contract(self):
        raw = {
            "results": [{
                "item_id": "1",
                "btc_relevance": "direct",
                "event_type": "market_commentary",
                "affected_assets": ["Wrapped Ether"],
                "direction": "negative",
                "severity": 0.1,
                "reported_surprise": 0.0,
                "expected_horizon": "unknown",
                "confidence": 0.5,
                "evidence_span": "Synthetic Wrapped Ether volumes jump",
            }]
        }
        expected = [{"item_id": "1", "headline_id": "z" * 64, "headline": "Synthetic Wrapped Ether volumes jump"}]
        with self.assertRaisesRegex(ValueError, "direct BTC relevance"):
            parse_batch(json.dumps(raw), expected, "ordinal_item_id")


if __name__ == "__main__":
    unittest.main()
