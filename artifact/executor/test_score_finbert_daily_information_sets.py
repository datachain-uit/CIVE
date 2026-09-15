import json
import tempfile
import unittest
from pathlib import Path

from score_finbert_daily_information_sets import (
    CONTRACT_HASH,
    CONTRACT_TEXT,
    aggregate_probabilities,
    parse_headlines,
    save,
    stratified_sample,
)


class FinBertDailyScorerTest(unittest.TestCase):
    def test_contract_hash_is_pinned(self):
        self.assertEqual(
            CONTRACT_HASH,
            "2c77eb833953e9f73fe6723a0cfba66fd107be71c7a0602cf60a5a3afd2e63f7",
        )
        self.assertIn("market outcomes are not used", CONTRACT_TEXT)

    def test_parse_headlines_removes_metadata(self):
        text = (
            "- [10:00 UTC | example.com | Bitcoin] Bitcoin ETF receives approval\n"
            "- [11:00 UTC | example.org | Ethereum] Protocol exploit drains funds"
        )
        self.assertEqual(parse_headlines(text), [
            "Bitcoin ETF receives approval",
            "Protocol exploit drains funds",
        ])

    def test_parse_headlines_rejects_uncontracted_line(self):
        with self.assertRaises(ValueError):
            parse_headlines("Bitcoin rises")

    def test_aggregate_probabilities(self):
        result = aggregate_probabilities([
            {"positive": 0.8, "negative": 0.1, "neutral": 0.1},
            {"positive": 0.1, "negative": 0.6, "neutral": 0.3},
        ])
        self.assertAlmostEqual(result["score"], 0.1)
        self.assertAlmostEqual(result["confidence"], 0.7)
        self.assertAlmostEqual(result["mean_probabilities"]["neutral"], 0.2)

    def test_stratified_sample_spans_each_year(self):
        records = [
            {"information_date": f"{year}-{month:02d}-01"}
            for year in (2020, 2021) for month in range(1, 7)
        ]
        selected = stratified_sample(records, 2)
        self.assertEqual([record["information_date"] for record in selected], [
            "2020-01-01", "2020-06-01", "2021-01-01", "2021-06-01",
        ])

    def test_checkpoint_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "checkpoint.json"
            save(output, "run1", "ProsusAI/finbert", "revision", [], 16, 128, 2)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["model_digest"], "revision")
            self.assertEqual(payload["contract_hash"], CONTRACT_HASH)
            self.assertEqual(payload["runtime"]["workers"], 1)


if __name__ == "__main__":
    unittest.main()
