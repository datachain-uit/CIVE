import json
import tempfile
import unittest
from pathlib import Path

from build_llm_event_reliability_sample_v3 import build


class LlmEventReliabilitySampleV3Test(unittest.TestCase):
    def test_sample_is_balanced_and_repeatable(self):
        records = []
        for year in (2022, 2023):
            for domain in ("a.example", "b.example"):
                for group in ("Bitcoin", "Ethereum"):
                    for index in range(4):
                        headline_id = f"{year}-{domain}-{group}-{index}"
                        records.append({
                            "headline_id": headline_id,
                            "information_date": f"{year}-01-01",
                            "published_at": f"{year}-01-01T00:00:00+00:00",
                            "source_domain": domain,
                            "coin_type": group,
                        })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            first = root / "first.json"
            second = root / "second.json"
            source.write_text(json.dumps({"records": records}), encoding="utf-8")
            left = build(source, first, seed=7, per_stratum=2)
            right = build(source, second, seed=7, per_stratum=2)
            self.assertEqual(left["records"], right["records"])
            self.assertEqual(left["summary"]["records"], 16)
            self.assertEqual(set(left["summary"]["stratum_counts"].values()), {2})


if __name__ == "__main__":
    unittest.main()
