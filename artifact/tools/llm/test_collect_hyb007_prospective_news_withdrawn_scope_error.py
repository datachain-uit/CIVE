import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from collect_hyb007_prospective_news_withdrawn_scope_error import Collector, ROOT, SOURCE, parse_rss


def rss(items):
    body = "".join(
        f"<item><title>{title}</title><link>{url}</link><pubDate>{published}</pubDate><category>{category}</category></item>"
        for title, url, published, category in items
    )
    return f"<?xml version='1.0'?><rss><channel>{body}</channel></rss>".encode()


class FakeFetcher:
    def __init__(self, payloads):
        self.payloads = payloads
        self.counter = 0

    def __call__(self, url):
        value = self.payloads[url]
        data = value.pop(0) if isinstance(value, list) else value
        self.counter += 1
        stamp = datetime(2026, 9, 11, 0, 0, self.counter, tzinfo=timezone.utc).isoformat()
        return data, {"url": url, "http_status": 200, "headers": {}, "started_at": stamp,
                      "completed_at": stamp, "bytes": len(data), "sha256": "fake"}


class Hyb007CollectorTests(unittest.TestCase):
    def test_parse_rss_preserves_timestamp_and_category(self):
        rows = parse_rss(rss([("ETH protocol update", "https://example.test/a?utm=x", "Fri, 11 Sep 2026 00:00:00 GMT", "Ethereum")]))
        self.assertEqual(rows[0]["link"], "https://example.test/a")
        self.assertEqual(rows[0]["published_at"], "2026-09-11T00:00:00+00:00")
        self.assertEqual(rows[0]["categories"], ["Ethereum"])

    def test_initialize_excludes_backlog_and_poll_admits_only_new_editorial(self):
        feed_url = SOURCE["cointelegraph"]
        old = ("Old Bitcoin item", "https://example.test/old", "Fri, 11 Sep 2026 00:00:00 GMT", "Bitcoin")
        new = ("Ethereum exchange security incident", "https://example.test/new", "Fri, 11 Sep 2026 01:00:00 GMT", "Ethereum")
        sponsored = ("BTC product", "https://example.test/press-releases/ad", "Fri, 11 Sep 2026 02:00:00 GMT", "Press Release")
        payloads = {
            feed_url: [rss([old]), rss([old, new, sponsored])],
            "https://example.test/new": b"<html><body><article>Ethereum crypto exchange security incident.</article></body></html>",
            "https://example.test/press-releases/ad": b"<html><body>Bitcoin sponsored item.</body></html>",
        }
        runtime_dir = ROOT / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime_dir) as directory:
            collector = Collector(Path(directory), fetcher=FakeFetcher(payloads))
            initial = collector.initialize()
            self.assertEqual(initial["baseline_urls"], 1)
            result = collector.poll()
            self.assertEqual(result["admitted"], 1)
            self.assertEqual(result["rejected"], 1)
            records = json.loads((Path(directory) / "records.json").read_text(encoding="utf-8"))
            self.assertEqual([row["canonical_url"] for row in records], ["https://example.test/new"])
            audit = json.loads((Path(directory) / "latest_sample_audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["status"], "COLLECTING_INSUFFICIENT_EFFECTIVE_SAMPLE")
            self.assertFalse(audit["market_outcomes_accessed"])
            self.assertTrue(audit["backfill_prohibited"])


if __name__ == "__main__":
    unittest.main()

