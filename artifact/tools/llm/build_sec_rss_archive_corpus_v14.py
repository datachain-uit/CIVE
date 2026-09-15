#!/usr/bin/env python3
"""Build an outcome-blind SEC RSS corpus from pinned Internet Archive snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "paper" / "input" / "results" / "llm" / "v14" / "sec_rss_archive_corpus_v14"
SOURCES = ROOT / "paper" / "input" / "references" / "source_artifacts" / "sec_rss_internet_archive_v14"
PREDECLARED = OUTPUT / "predeclared.json"
CDX_URL = (
    "https://web.archive.org/cdx/search/cdx?"
    "url=www.sec.gov%2Fnews%2Fpressreleases.rss&output=json&filter=statuscode:200&"
    "fl=timestamp,digest,length&collapse=timestamp:8&from=2021&to=2026"
)
RSS_URL = "https://www.sec.gov/news/pressreleases.rss"
USER_AGENT = "KLTN-sec-rss-provenance-audit/1.0 (research; contact@example.edu)"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch(url: str, timeout_seconds: int) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml, application/json, text/xml"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return int(response.status), response.read()


def parse_capture_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def parse_pub_date(value: str) -> datetime:
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("pubDate lacks explicit UTC offset")
    return parsed


def normalized_text(value: str | None) -> str:
    return " ".join((value or "").split())


def item_value(item: ET.Element, name: str) -> str:
    child = item.find(name)
    return normalized_text(child.text if child is not None else None)


def replay_url(capture: str) -> str:
    return f"https://web.archive.org/web/{capture}id_/{RSS_URL}"


def load_cdx(timeout_seconds: int) -> tuple[list[dict[str, str]], dict[str, Any]]:
    status, payload = fetch(CDX_URL, timeout_seconds)
    if status != 200:
        raise RuntimeError(f"CDX returned HTTP {status}")
    parsed = json.loads(payload)
    if not isinstance(parsed, list) or not parsed or not isinstance(parsed[0], list):
        raise RuntimeError("CDX response does not have a header row")
    header = parsed[0]
    expected = ["timestamp", "digest", "length"]
    if header != expected:
        raise RuntimeError(f"unexpected CDX header: {header!r}")
    rows: list[dict[str, str]] = []
    for row in parsed[1:]:
        if not isinstance(row, list) or len(row) != len(header):
            raise RuntimeError("malformed CDX row")
        capture, digest, length = (str(part) for part in row)
        parse_capture_time(capture)
        if not digest or not length.isdigit():
            raise RuntimeError("CDX row lacks digest or numeric length")
        rows.append({"archive_capture": capture, "digest": digest, "length": length})
    rows.sort(key=lambda row: row["archive_capture"])
    provenance = {
        "url": CDX_URL,
        "http_status": status,
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "records": len(rows),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    return rows, provenance


def build(timeout_seconds: int, request_delay_seconds: float) -> None:
    predeclared = read_json(PREDECLARED)
    if predeclared.get("selection_uses_outcomes") is not False or predeclared.get("market_data_accessed") is not False:
        raise RuntimeError("predeclaration does not enforce outcome blindness")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    SOURCES.mkdir(parents=True, exist_ok=True)
    snapshots_dir = SOURCES / "rss_snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    cdx_rows, cdx_provenance = load_cdx(timeout_seconds)
    (SOURCES / "cdx_index.json").write_bytes(canonical_json({"rows": cdx_rows, "provenance": cdx_provenance}))

    admitted_by_guid: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, str]] = []
    snapshots: list[dict[str, Any]] = []
    for index, row in enumerate(cdx_rows, start=1):
        capture = row["archive_capture"]
        capture_at = parse_capture_time(capture)
        status, payload = fetch(replay_url(capture), timeout_seconds)
        if status != 200:
            excluded.append({"archive_capture": capture, "reason": f"replay_http_{status}"})
            continue
        snapshot_path = snapshots_dir / f"{capture}.xml"
        snapshot_path.write_bytes(payload)
        snapshot_info = {
            **row,
            "replay_url": replay_url(capture),
            "bytes": len(payload),
            "sha256": sha256_bytes(payload),
        }
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            excluded.append({"archive_capture": capture, "reason": f"xml_parse_error:{exc}"})
            snapshots.append({**snapshot_info, "items_seen": 0, "items_admitted": 0, "parse_ok": False})
            continue
        items = root.findall("./channel/item")
        admitted_here = 0
        for item in items:
            title = item_value(item, "title")
            description = item_value(item, "description")
            link = item_value(item, "link")
            pub_date_raw = item_value(item, "pubDate")
            guid = item_value(item, "guid")
            if not guid:
                guid = sha256_bytes(canonical_json({"title": title, "link": link, "pubDate": pub_date_raw}))
            if not title or not description or not link or not pub_date_raw:
                excluded.append({"archive_capture": capture, "guid": guid, "reason": "missing_required_rss_plaintext_field"})
                continue
            try:
                pub_date = parse_pub_date(pub_date_raw)
            except (TypeError, ValueError) as exc:
                excluded.append({"archive_capture": capture, "guid": guid, "reason": f"pubdate_offset_invalid:{exc}"})
                continue
            if pub_date.astimezone(timezone.utc) > capture_at:
                excluded.append({"archive_capture": capture, "guid": guid, "reason": "pubdate_after_archive_capture"})
                continue
            if guid in admitted_by_guid:
                continue
            text = f"TITLE: {title}\nDESCRIPTION: {description}"
            record = {
                "record_id": sha256_bytes(canonical_json({"guid": guid, "archive_capture": capture, "text": text})),
                "guid": guid,
                "text": text,
                "title": title,
                "description": description,
                "link": link,
                "publisher_pubdate": pub_date.isoformat(),
                "archive_capture_at": capture_at.isoformat(),
                "archive_capture": capture,
                "archive_digest": row["digest"],
                "archive_length": int(row["length"]),
                "snapshot_sha256": snapshot_info["sha256"],
            }
            admitted_by_guid[guid] = record
            admitted_here += 1
        snapshots.append({**snapshot_info, "items_seen": len(items), "items_admitted": admitted_here, "parse_ok": True})
        if request_delay_seconds:
            time.sleep(request_delay_seconds)

    corpus = sorted(admitted_by_guid.values(), key=lambda record: (record["archive_capture_at"], record["guid"]))
    corpus_payload = {
        "schema_version": 1,
        "corpus_id": "sec-rss-internet-archive-v14",
        "information_time": "archive_capture_at",
        "selection_uses_outcomes": False,
        "market_data_accessed": False,
        "model_run": False,
        "records": corpus,
    }
    excluded_payload = {
        "schema_version": 1,
        "corpus_id": "sec-rss-internet-archive-v14",
        "selection_uses_outcomes": False,
        "records": excluded,
    }
    corpus_path = OUTPUT / "corpus.json"
    excluded_path = OUTPUT / "excluded.json"
    corpus_path.write_bytes(canonical_json(corpus_payload))
    excluded_path.write_bytes(canonical_json(excluded_payload))
    manifest = {
        "schema_version": 1,
        "status": "OUTCOME_BLIND_CORPUS_CLOSED_PENDING_SCHEMA_AUDIT",
        "corpus_id": "sec-rss-internet-archive-v14",
        "selection_uses_outcomes": False,
        "market_data_accessed": False,
        "model_run": False,
        "information_time": "archive_capture_at",
        "snapshot_count": len(snapshots),
        "admitted_records": len(corpus),
        "excluded_records": len(excluded),
        "files": {
            "predeclared.json": sha256_bytes(PREDECLARED.read_bytes()),
            "build_sec_rss_archive_corpus_v14.py": sha256_bytes(Path(__file__).read_bytes()),
            "cdx_index.json": sha256_bytes((SOURCES / "cdx_index.json").read_bytes()),
            "corpus.json": sha256_bytes(corpus_path.read_bytes()),
            "excluded.json": sha256_bytes(excluded_path.read_bytes()),
        },
        "cdx_provenance": cdx_provenance,
        "snapshots": snapshots,
    }
    (OUTPUT / "manifest.json").write_bytes(canonical_json(manifest))
    print(json.dumps({"status": manifest["status"], "snapshots": len(snapshots), "admitted": len(corpus), "excluded": len(excluded)}))


def verify() -> None:
    manifest = read_json(OUTPUT / "manifest.json")
    if manifest.get("status") != "OUTCOME_BLIND_CORPUS_CLOSED_PENDING_SCHEMA_AUDIT":
        raise RuntimeError("unexpected manifest status")
    for name, expected in manifest["files"].items():
        path = PREDECLARED if name == "predeclared.json" else (Path(__file__) if name == "build_sec_rss_archive_corpus_v14.py" else (SOURCES / name if name == "cdx_index.json" else OUTPUT / name))
        actual = sha256_bytes(path.read_bytes())
        if actual != expected:
            raise RuntimeError(f"hash mismatch for {name}")
    corpus = read_json(OUTPUT / "corpus.json")
    previous: datetime | None = None
    seen_guids: set[str] = set()
    for record in corpus["records"]:
        capture = datetime.fromisoformat(record["archive_capture_at"])
        pub_date = datetime.fromisoformat(record["publisher_pubdate"])
        if capture.tzinfo is None or capture.utcoffset() is None or pub_date.tzinfo is None or pub_date.utcoffset() is None:
            raise RuntimeError("timestamp lacks offset")
        if pub_date.astimezone(timezone.utc) > capture.astimezone(timezone.utc):
            raise RuntimeError("publisher time is after archive availability")
        if previous is not None and capture < previous:
            raise RuntimeError("corpus is not time ordered")
        if record["guid"] in seen_guids:
            raise RuntimeError("duplicate GUID")
        if not record["text"].startswith("TITLE: "):
            raise RuntimeError("unexpected text contract")
        previous = capture
        seen_guids.add(record["guid"])
    print(json.dumps({"status": "VERIFY_PASS", "records": len(corpus["records"])}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--request-delay-seconds", type=float, default=0.25)
    args = parser.parse_args()
    if args.verify:
        verify()
    else:
        build(args.timeout_seconds, args.request_delay_seconds)


if __name__ == "__main__":
    main()
