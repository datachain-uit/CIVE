import unittest
from datetime import datetime, timezone

from audit_fulltext_corpus_v5 import canonical_url, floor_4h, normalize_text


class AuditFulltextCorpusV5Tests(unittest.TestCase):
    def test_normalize_text_decodes_entities_and_space(self):
        self.assertEqual(normalize_text(" A&amp;B\n  C "), "A&B C")

    def test_canonical_url_removes_tracking_query(self):
        self.assertEqual(
            canonical_url("HTTPS://WWW.Example.com/news/item/?utm_source=x"),
            "https://example.com/news/item",
        )

    def test_floor_4h_is_utc_bucket(self):
        value = datetime(2024, 1, 2, 7, 59, tzinfo=timezone.utc)
        self.assertEqual(floor_4h(value), "2024-01-02T04:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
