import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from collect_prospective_official_crypto_tail_risk_v12 import Collector, ROOT, SOURCES, parse_feed, provenance_headers


def rss(items):
    body = "".join(
        f"<item><title>{title}</title><link>{url}</link><pubDate>{published}</pubDate></item>"
        for title, url, published in items
    )
    return f"<?xml version='1.0'?><rss><channel>{body}</channel></rss>".encode()


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []
        self.index = 0

    def __call__(self, url):
        self.calls.append(url)
        value = self.pages[url]
        if isinstance(value, list):
            data = value.pop(0)
        else:
            data = value
        self.index += 1
        stamp = datetime(2026, 9, 6, 0, 0, self.index, tzinfo=timezone.utc).isoformat()
        return data, {"url": url, "http_status": 200, "headers": {}, "started_at": stamp, "completed_at": stamp,
                      "bytes": len(data), "sha256": "fake"}


class ProspectiveCollectorTests(unittest.TestCase):
    def test_provenance_headers_redacts_cookie_and_omits_unneeded_values(self):
        headers = provenance_headers({"Date": "Sat", "Set-Cookie": "secret", "Server": "private"})
        self.assertEqual(headers, {"Date": "Sat", "Set-Cookie": "<redacted>"})
    def test_parse_atom_and_rss_timezones(self):
        rows = parse_feed(rss([("Bitcoin enforcement", "https://example.test/a?ref=feed", "Sat, 06 Sep 2026 00:00:00 GMT")]))
        self.assertEqual(rows[0]["published_at"], "2026-09-06T00:00:00+00:00")
        atom = b"""<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>Token rule</title><link href='https://example.test/b'/><published>2026-09-06T00:00:00Z</published></entry></feed>"""
        self.assertEqual(parse_feed(atom)[0]["link"], "https://example.test/b")

    def test_initial_baseline_is_never_admitted_and_later_item_is(self):
        old_url, new_url = "https://example.test/old", "https://example.test/new"
        old = ("Old Bitcoin release", old_url, "Sat, 06 Sep 2026 00:00:00 GMT")
        new = ("New digital asset release", new_url, "Sat, 06 Sep 2026 01:00:00 GMT")
        pages = {source: [rss([old]), rss([old, new])] for source in SOURCES.values()}
        pages[new_url] = b"<html><title>New digital asset release</title><body><p>Digital asset enforcement action.</p></body></html>"
        fetcher = FakeFetcher(pages)
        runtime_dir = ROOT / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime_dir) as directory:
            collector = Collector(Path(directory), fetcher=fetcher)
            initial = collector.initialize()
            self.assertTrue(initial.initialized)
            self.assertEqual(initial.admitted, 0)
            self.assertNotIn(old_url, fetcher.calls)
            result = collector.poll()
            self.assertEqual(result.admitted, 1)
            records = json.loads((Path(directory) / "records.json").read_text(encoding="utf-8"))
            self.assertEqual([row["canonical_url"] for row in records], [new_url])
            self.assertEqual(records[0]["collection_mode"], "prospective_post_baseline")
            audit = json.loads((Path(directory) / "latest_audit.json").read_text(encoding="utf-8"))
            self.assertTrue(audit["backfill_prohibited"])
            self.assertEqual(audit["records_admitted_total"], 1)


if __name__ == "__main__":
    unittest.main()