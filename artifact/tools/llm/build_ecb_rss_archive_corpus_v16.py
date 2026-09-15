#!/usr/bin/env python3
"""Build and verify the outcome-blind title-only ECB RSS archive corpus v16."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCREEN = ROOT / "paper/input/references/source_artifacts/ecb_rss_internet_archive_v16/source_screen.json"
PREDECLARED = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_corpus_v16/predeclared.json"
PROGRESS = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_corpus_v16/download_progress.json"
SNAPSHOTS = ROOT / "paper/input/references/source_artifacts/ecb_rss_internet_archive_v16/rss_snapshots"
OUT = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_corpus_v16"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(canonical_json(value))
    temporary.replace(path)


def capture_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def pub_time(value: str) -> datetime:
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("pubDate lacks explicit offset")
    return parsed


def clean(value: str | None) -> str:
    return " ".join(html.unescape(value or "").split())


def canonical_link(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    host = (parsed.hostname or "").lower()
    if host not in {"ecb.europa.eu", "www.ecb.europa.eu", "ecb.int", "www.ecb.int"}:
        raise ValueError("non-ECB host")
    path = re.sub("/+", "/", parsed.path).rstrip("/")
    if not path.lower().startswith("/press/"):
        raise ValueError("non-press link")
    return "https://www.ecb.europa.eu" + path


def build() -> dict:
    screen = json.loads(SCREEN.read_text(encoding="utf-8"))
    predeclared = json.loads(PREDECLARED.read_text(encoding="utf-8"))
    progress = json.loads(PROGRESS.read_text(encoding="utf-8"))
    if sha(SCREEN.read_bytes()) != predeclared["source_screen"]["sha256"]:
        raise RuntimeError("source screen hash mismatch")
    if progress["status"] != "DOWNLOAD_COMPLETE" or progress["success"] != progress["expected"] or progress["errors"]:
        raise RuntimeError("raw snapshot download is incomplete")
    rows = sorted(screen["archive"]["rows"], key=lambda row: row["timestamp"])
    progress_by_timestamp = {row["timestamp"]: row for row in progress["records"]}
    if len(rows) != len(progress_by_timestamp):
        raise RuntimeError("download records do not match frozen source screen")
    admitted = {}
    excluded = []
    snapshot_audit = []
    for row in rows:
        timestamp = row["timestamp"]
        path = SNAPSHOTS / f"{timestamp}.xml"
        body = path.read_bytes()
        recorded = progress_by_timestamp[timestamp]
        if sha(body) != recorded["sha256"]:
            raise RuntimeError(f"raw snapshot hash mismatch: {timestamp}")
        info = {
            "archive_capture": timestamp,
            "archive_capture_at": capture_time(timestamp).isoformat(),
            "cdx_digest": row["digest"],
            "cdx_length": int(row["length"]),
            "file": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha(body),
            "bytes": len(body),
        }
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            excluded.append({"archive_capture": timestamp, "reason": f"xml_parse_error:{exc}"})
            snapshot_audit.append({**info, "parse_ok": False, "items_seen": 0, "items_admitted": 0})
            continue
        items = root.findall("./channel/item")
        added = 0
        for item in items:
            title = clean(item.findtext("title"))
            link = clean(item.findtext("link"))
            raw_pub = clean(item.findtext("pubDate"))
            if not all((title, link, raw_pub)):
                excluded.append({"archive_capture": timestamp, "link": link, "reason": "missing_required_field"})
                continue
            try:
                canonical = canonical_link(link)
                published = pub_time(raw_pub)
            except (TypeError, ValueError) as exc:
                excluded.append({"archive_capture": timestamp, "link": link, "reason": str(exc)})
                continue
            available = capture_time(timestamp)
            if published.astimezone(timezone.utc) > available:
                excluded.append({"archive_capture": timestamp, "link": canonical, "reason": "pubdate_after_archive_capture"})
                continue
            if canonical in admitted:
                continue
            text = f"TITLE: {title}"
            admitted[canonical] = {
                "record_id": sha(canonical_json({"canonical_link": canonical, "archive_capture": timestamp, "text": text})),
                "canonical_link": canonical,
                "text": text,
                "title": title,
                "publisher_pubdate": published.isoformat(),
                "archive_capture_at": available.isoformat(),
                "archive_capture": timestamp,
                "archive_digest": row["digest"],
                "archive_length": int(row["length"]),
                "snapshot_sha256": sha(body),
            }
            added += 1
        snapshot_audit.append({**info, "parse_ok": True, "items_seen": len(items), "items_admitted": added})
    records = sorted(admitted.values(), key=lambda record: (record["archive_capture_at"], record["canonical_link"]))
    corpus = {
        "schema_version": 1,
        "corpus_id": "ecb-rss-internet-archive-v16",
        "information_time": "archive_capture_at",
        "text_contract": "title_only",
        "selection_uses_outcomes": False,
        "market_data_accessed": False,
        "model_run": False,
        "records": records,
    }
    exclusions = {
        "schema_version": 1,
        "corpus_id": corpus["corpus_id"],
        "selection_uses_outcomes": False,
        "records": excluded,
    }
    write(OUT / "corpus.json", corpus)
    write(OUT / "excluded.json", exclusions)
    manifest = {
        "schema_version": 1,
        "status": "OUTCOME_BLIND_CORPUS_CLOSED_PENDING_SCHEMA_AUDIT",
        "corpus_id": corpus["corpus_id"],
        "selection_uses_outcomes": False,
        "market_data_accessed": False,
        "model_run": False,
        "trading_backtest_consulted": False,
        "information_time": "archive_capture_at",
        "text_contract": "title_only",
        "snapshot_count": len(snapshot_audit),
        "parseable_snapshots": sum(bool(row["parse_ok"]) for row in snapshot_audit),
        "admitted_records": len(records),
        "excluded_records": len(excluded),
        "information_sets": len({record["archive_capture_at"] for record in records}),
        "exclusion_reasons": dict(sorted(Counter(row["reason"] for row in excluded).items())),
        "files": {
            "source_screen.json": sha(SCREEN.read_bytes()),
            "predeclared.json": sha(PREDECLARED.read_bytes()),
            "download_progress.json": sha(PROGRESS.read_bytes()),
            "build_ecb_rss_archive_corpus_v16.py": sha(Path(__file__).read_bytes()),
            "corpus.json": sha((OUT / "corpus.json").read_bytes()),
            "excluded.json": sha((OUT / "excluded.json").read_bytes()),
        },
        "snapshots": snapshot_audit,
    }
    write(OUT / "manifest.json", manifest)
    return manifest


def verify() -> dict:
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    corpus = json.loads((OUT / "corpus.json").read_text(encoding="utf-8"))
    paths = {
        "source_screen.json": SCREEN,
        "predeclared.json": PREDECLARED,
        "download_progress.json": PROGRESS,
        "build_ecb_rss_archive_corpus_v16.py": Path(__file__),
        "corpus.json": OUT / "corpus.json",
        "excluded.json": OUT / "excluded.json",
    }
    for name, path in paths.items():
        if sha(path.read_bytes()) != manifest["files"][name]:
            raise RuntimeError(f"hash mismatch: {name}")
    seen_links = set()
    seen_ids = set()
    previous = None
    for row in corpus["records"]:
        available = datetime.fromisoformat(row["archive_capture_at"])
        published = datetime.fromisoformat(row["publisher_pubdate"])
        if available.tzinfo is None or published.tzinfo is None or published.astimezone(timezone.utc) > available.astimezone(timezone.utc):
            raise RuntimeError("timestamp contract failure")
        if previous and available < previous:
            raise RuntimeError("order failure")
        if row["canonical_link"] in seen_links or row["record_id"] in seen_ids:
            raise RuntimeError("duplicate identity")
        if not row["text"].startswith("TITLE: ") or "description" in row:
            raise RuntimeError("title-only text contract failure")
        if any(token in row for token in ("price", "return", "target", "label", "feature", "outcome")):
            raise RuntimeError("forbidden market/outcome field")
        previous = available
        seen_links.add(row["canonical_link"])
        seen_ids.add(row["record_id"])
    return {
        "status": "SCHEMA_AUDIT_PASS",
        "records": len(corpus["records"]),
        "information_sets": len({row["archive_capture_at"] for row in corpus["records"]}),
        "first": corpus["records"][0]["archive_capture_at"] if corpus["records"] else None,
        "last": corpus["records"][-1]["archive_capture_at"] if corpus["records"] else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify() if args.verify else build(), indent=2))


if __name__ == "__main__":
    main()
