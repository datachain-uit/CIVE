#!/usr/bin/env python3
"""Outcome-blind source screen for the ECB press RSS archive candidate v16."""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "paper/input/references/source_artifacts/ecb_rss_internet_archive_v16"
SCREEN = OUT / "source_screen.json"
FEED = "https://www.ecb.europa.eu/rss/press.html"
CDX = "https://web.archive.org/cdx/search/cdx"
USER_AGENT = "KLTN-research-audit/1.0"


def fetch(url: str, attempts: int = 5) -> bytes:
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable retry state")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    query = CDX + "?" + urllib.parse.urlencode({
        "url": "www.ecb.europa.eu/rss/press.html",
        "output": "json",
        "filter": "statuscode:200",
        "fl": "timestamp,digest,length",
        "collapse": "timestamp:8",
        "from": "2010",
        "to": "2026",
    })
    raw = fetch(query)
    payload = json.loads(raw)
    rows = [dict(zip(payload[0], values)) for values in payload[1:]]
    if len(rows) < 96:
        raise RuntimeError("source-level archive coverage is below the frozen minimum")
    OUT.mkdir(parents=True, exist_ok=True)
    samples = []
    for index in sorted({0, len(rows) // 2, len(rows) - 1}):
        row = rows[index]
        timestamp = row["timestamp"]
        replay = f"https://web.archive.org/web/{timestamp}id_/{FEED}"
        body = fetch(replay)
        sample_path = OUT / f"sample_{timestamp}.xml"
        sample_path.write_bytes(body)
        record = {
            "timestamp": timestamp,
            "replay_url": replay,
            "file": str(sample_path.relative_to(ROOT)).replace("\\", "/"),
            "bytes": len(body),
            "sha256": sha(body),
            "parse_ok": False,
            "items": 0,
            "items_with_title_link_offset_pubdate": 0,
        }
        try:
            root = ET.fromstring(body)
            items = root.findall("./channel/item")
            record["parse_ok"] = True
            record["items"] = len(items)
            record["items_with_title_link_offset_pubdate"] = sum(
                bool((item.findtext("title") or "").strip())
                and bool((item.findtext("link") or "").strip())
                and bool((item.findtext("pubDate") or "").strip())
                and ("+" in (item.findtext("pubDate") or "") or "-" in (item.findtext("pubDate") or "")[10:])
                for item in items
            )
        except ET.ParseError as exc:
            record["parse_error"] = str(exc)
        samples.append(record)
        time.sleep(2)
    screen = {
        "schema_version": 1,
        "candidate_id": "ecb-rss-press-internet-archive-v16",
        "decision": "SOURCE_SCREEN_PASS_TITLE_ONLY_FULL_OUTCOME_BLIND_CORPUS_AUDIT_REQUIRED",
        "outcomes_consulted": False,
        "market_data_accessed": False,
        "model_run": False,
        "feed": FEED,
        "information_time": "archive_capture_at",
        "text_contract": "title only; description is not required or supplied to the model",
        "deduplication": "canonical link; retain first valid archived availability",
        "publication_time_rule": "pubDate must parse with an explicit UTC offset and must not exceed archive_capture_at",
        "rights": {
            "rss_page": "https://www.ecb.europa.eu/home/html/rss.en.html",
            "reuse_policy": "https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html",
            "scope": "ECB website information may be reused with accurate reproduction and ECB attribution; exclude named-author papers and third-party content.",
        },
        "archive": {
            "documentation": "https://github.com/internetarchive/wayback/blob/master/wayback-cdx-server/README.md",
            "query": query,
            "raw_query_sha256": sha(raw),
            "captures": len(rows),
            "first": rows[0]["timestamp"],
            "last": rows[-1]["timestamp"],
            "rows": rows,
        },
        "samples": samples,
        "next_authorized_step": "Freeze download/build contract, then download and hash every listed snapshot. No target, market data, or model access is authorized.",
    }
    SCREEN.write_text(json.dumps(screen, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": screen["decision"],
        "captures": len(rows),
        "first": rows[0]["timestamp"],
        "last": rows[-1]["timestamp"],
        "samples": samples,
        "source_screen_sha256": sha(SCREEN.read_bytes()),
    }, indent=2))


if __name__ == "__main__":
    main()
