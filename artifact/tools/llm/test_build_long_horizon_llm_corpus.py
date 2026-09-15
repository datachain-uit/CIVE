import csv
import gzip
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from build_long_horizon_llm_corpus import build


class LongHorizonCorpusTest(unittest.TestCase):
    def test_excludes_outcomes_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "source.csv"
            fields = ["URL", "Title", "Date Time", "Coin Type", "sentiment_label", "Close", "Market_Move"]
            with csv_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow({"URL": "https://coindesk.com/a", "Title": " A headline ",
                                 "Date Time": "2020-01-01 12:00:00+00:00", "Coin Type": "Bitcoin",
                                 "sentiment_label": "POSITIVE", "Close": "99", "Market_Move": "Up"})
                writer.writerow({"URL": "https://decrypt.co/b", "Title": "A headline",
                                 "Date Time": "2020-01-01 13:00:00+00:00", "Coin Type": "Bitcoin"})
                writer.writerow({"URL": "https://example.com/c", "Title": "Rejected",
                                 "Date Time": "2020-01-01 14:00:00+00:00", "Coin Type": "Bitcoin"})
            archive = root / "source.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.write(csv_path, "dataset.csv")
            output, manifest_path = root / "corpus.jsonl.gz", root / "manifest.json"
            manifest = build(archive, output, manifest_path)
            with gzip.open(output, "rt", encoding="utf-8") as stream:
                records = [json.loads(line) for line in stream]
            self.assertEqual(len(records), 1)
            self.assertEqual(manifest["accepted_records"], 1)
            self.assertEqual(manifest["rejection_reasons"]["duplicate_title"], 1)
            self.assertEqual(manifest["rejection_reasons"]["missing_or_disallowed_url"], 1)
            self.assertFalse({"sentiment_label", "Close", "Market_Move"} & records[0].keys())
            self.assertEqual(records[0]["available_at"], "2020-01-01T12:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
