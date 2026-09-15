import gzip
import json
import tempfile
import unittest
from pathlib import Path

from build_llm_daily_information_sets import balanced_selection, build


class DailyInformationSetsTest(unittest.TestCase):
    def test_balances_sources_and_delays_until_next_day(self):
        rows = [
            {"content_hash": str(index).zfill(64), "text": f"headline {index}",
             "published_at": f"2020-01-01T{index:02d}:00:00+00:00", "available_at": "unused",
             "source_domain": "coindesk.com" if index < 3 else "decrypt.co", "coin_type": "Bitcoin",
             "url": f"https://example/{index}"}
            for index in range(4)
        ]
        chosen = balanced_selection(rows, 2)
        self.assertEqual({item["source_domain"] for item in chosen}, {"coindesk.com", "decrypt.co"})
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.gz", Path(directory) / "sets.json"
            with gzip.open(source, "wt", encoding="utf-8") as stream:
                for row in rows:
                    stream.write(json.dumps(row) + "\n")
            payload = build(source, output, maximum=2)
            record = payload["records"][0]
            self.assertEqual(record["available_at"], "2020-01-02T00:00:00+00:00")
            self.assertEqual(record["article_count"], 4)
            self.assertEqual(record["selected_article_count"], 2)


if __name__ == "__main__":
    unittest.main()
