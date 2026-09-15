import json
import unittest

from score_llm_event_extractor_v3_9 import normalize_assets, parse_batch


def expected_item(headline: str, item_id: str = "1") -> list[dict]:
    return [{"item_id": item_id, "headline_id": "a" * 64, "headline": headline}]


class RelaxedDirectAssetCouplingTests(unittest.TestCase):
    def test_direct_item_without_btc_asset_is_preserved(self):
        headline = "NYDIG Lays Off a Third of Its Staff"
        raw = {"results": [{
            "item_id": "1",
            "btc_relevance": "direct",
            "event_type": "liquidation_leverage",
            "affected_assets": ["NYDIG"],
            "direction": "negative",
            "severity": 0.8,
            "reported_surprise": 0.5,
            "expected_horizon": "24h",
            "confidence": 0.8,
            "evidence_span": headline,
        }]}
        parsed = parse_batch(json.dumps(raw), expected_item(headline), "ordinal_item_id")
        self.assertEqual(parsed[0]["btc_relevance"], "direct")
        self.assertEqual(parsed[0]["affected_assets"], ["NYDIG"])

    def test_exact_v3_8_failed_batch_now_parses(self):
        headlines = [
            "Uniswap to Deploy on Privacy-Focused zkSync",
            "Bitcoin Firm NYDIG Slashes 110 Jobs Amid Ongoing Crypto Bear Market",
            "NYDIG Lays Off a Third of Its Staff",
            "Bitcoin ‘bear trap’ sees BTC price near $20K as daily gains top 9%",
        ]
        results = [
            ["indirect", "market_commentary", ["Uniswap", "zkSync"], "positive", 0.2, 0.0, "unknown", 0.7],
            ["direct", "liquidation_leverage", ["Bitcoin", "NYDIG"], "negative", 0.7, 0.5, "24h", 0.9],
            ["direct", "liquidation_leverage", ["NYDIG"], "negative", 0.8, 0.5, "24h", 0.8],
            ["direct", "market_commentary", ["Bitcoin"], "positive", 0.6, 0.0, "unknown", 0.9],
        ]
        raw_items = []
        for index, (headline, values) in enumerate(zip(headlines, results), start=1):
            relevance, event_type, assets, direction, severity, surprise, horizon, confidence = values
            raw_items.append({
                "item_id": str(index), "btc_relevance": relevance, "event_type": event_type,
                "affected_assets": assets, "direction": direction, "severity": severity,
                "reported_surprise": surprise, "expected_horizon": horizon,
                "confidence": confidence, "evidence_span": headline,
            })
        expected = [
            {"item_id": str(index), "headline_id": str(index) * 64, "headline": headline}
            for index, headline in enumerate(headlines, start=1)
        ]
        parsed = parse_batch(json.dumps({"results": raw_items}), expected, "ordinal_item_id")
        self.assertEqual(len(parsed), 4)
        self.assertEqual(parsed[2]["affected_assets"], ["NYDIG"])
        self.assertEqual(parsed[2]["btc_relevance"], "direct")

    def test_canonicalization_and_dedupe_are_unchanged(self):
        self.assertEqual(
            normalize_assets(["wrapped BTC", "MakerDAO", "BTC", "Bitcoin", "MakerDAO"]),
            ["BTC", "MakerDAO", "Bitcoin"],
        )

    def test_other_asset_validation_remains_strict(self):
        headline = "NYDIG Lays Off a Third of Its Staff"
        raw = {"results": [{
            "item_id": "1", "btc_relevance": "direct",
            "event_type": "liquidation_leverage", "affected_assets": [""],
            "direction": "negative", "severity": 0.8, "reported_surprise": 0.5,
            "expected_horizon": "24h", "confidence": 0.8, "evidence_span": headline,
        }]}
        with self.assertRaisesRegex(ValueError, "invalid affected asset value"):
            parse_batch(json.dumps(raw), expected_item(headline), "ordinal_item_id")


if __name__ == "__main__":
    unittest.main()
