#!/usr/bin/env python3
"""Finalize the local, outcome-blind SEC RSS archive corpus."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "paper" / "input" / "results" / "llm" / "v14" / "sec_rss_archive_corpus_v14"
SRC = ROOT / "paper" / "input" / "references" / "source_artifacts" / "sec_rss_internet_archive_v14"


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def text(item: ET.Element, name: str) -> str:
    node = item.find(name)
    return " ".join((node.text if node is not None and node.text else "").split())


def main() -> None:
    predeclared = json.loads((OUT / "predeclared.json").read_text(encoding="utf-8"))
    if predeclared["selection_uses_outcomes"] or predeclared["market_data_accessed"] or predeclared["model_run"]:
        raise RuntimeError("predeclaration must remain outcome-blind")
    cdx = json.loads((SRC / "cdx_index.json").read_text(encoding="utf-8"))
    rows = cdx["rows"]
    records: dict[str, dict] = {}
    excluded: list[dict] = []
    snapshots: list[dict] = []
    for row in rows:
        capture = row["archive_capture"]
        capture_at = datetime.strptime(capture, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        snapshot = SRC / "rss_snapshots" / f"{capture}.xml"
        if not snapshot.exists():
            excluded.append({"archive_capture": capture, "reason": "snapshot_missing"})
            continue
        payload = snapshot.read_bytes()
        info = {"archive_capture": capture, "archive_digest": row["digest"], "archive_length": int(row["length"]), "bytes": len(payload), "sha256": digest(payload)}
        try:
            items = ET.fromstring(payload).findall("./channel/item")
        except ET.ParseError as exc:
            excluded.append({"archive_capture": capture, "reason": f"xml_parse_error:{exc}"})
            snapshots.append({**info, "items_seen": 0, "items_admitted": 0})
            continue
        admitted = 0
        for item in items:
            title, description, link, pub_raw, guid = (text(item, key) for key in ("title", "description", "link", "pubDate", "guid"))
            if not guid:
                guid = digest(json.dumps([title, link, pub_raw], ensure_ascii=True).encode("utf-8"))
            if not title or not description or not link or not pub_raw:
                excluded.append({"archive_capture": capture, "guid": guid, "reason": "missing_required_rss_plaintext_field"})
                continue
            try:
                pub_at = parsedate_to_datetime(pub_raw)
                if pub_at.tzinfo is None or pub_at.utcoffset() is None:
                    raise ValueError("missing_utc_offset")
            except (TypeError, ValueError) as exc:
                excluded.append({"archive_capture": capture, "guid": guid, "reason": f"pubdate_offset_invalid:{exc}"})
                continue
            if pub_at.astimezone(timezone.utc) > capture_at:
                excluded.append({"archive_capture": capture, "guid": guid, "reason": "pubdate_after_archive_capture"})
                continue
            if guid in records:
                continue
            body = f"TITLE: {title}\nDESCRIPTION: {description}"
            records[guid] = {
                "record_id": digest(json.dumps([guid, capture, body], ensure_ascii=True).encode("utf-8")),
                "guid": guid,
                "text": body,
                "title": title,
                "description": description,
                "link": link,
                "publisher_pubdate": pub_at.isoformat(),
                "archive_capture_at": capture_at.isoformat(),
                "archive_capture": capture,
                "archive_digest": row["digest"],
                "archive_length": int(row["length"]),
                "snapshot_sha256": info["sha256"],
            }
            admitted += 1
        snapshots.append({**info, "items_seen": len(items), "items_admitted": admitted})
    ordered = sorted(records.values(), key=lambda item: (item["archive_capture_at"], item["guid"]))
    corpus = {"schema_version": 1, "corpus_id": "sec-rss-internet-archive-v14", "information_time": "archive_capture_at", "selection_uses_outcomes": False, "market_data_accessed": False, "model_run": False, "records": ordered}
    exclusion = {"schema_version": 1, "corpus_id": "sec-rss-internet-archive-v14", "selection_uses_outcomes": False, "records": excluded}
    dump(OUT / "corpus.json", corpus)
    dump(OUT / "excluded.json", exclusion)
    manifest = {
        "schema_version": 1,
        "status": "OUTCOME_BLIND_CORPUS_CLOSED_PENDING_SCHEMA_AUDIT",
        "corpus_id": "sec-rss-internet-archive-v14",
        "information_time": "archive_capture_at",
        "selection_uses_outcomes": False,
        "market_data_accessed": False,
        "model_run": False,
        "snapshot_count": len(snapshots),
        "admitted_records": len(ordered),
        "excluded_records": len(excluded),
        "files": {
            "predeclared.json": digest((OUT / "predeclared.json").read_bytes()),
            "finalize_sec_rss_archive_corpus_v14.py": digest(Path(__file__).read_bytes()),
            "cdx_index.json": digest((SRC / "cdx_index.json").read_bytes()),
            "corpus.json": digest((OUT / "corpus.json").read_bytes()),
            "excluded.json": digest((OUT / "excluded.json").read_bytes()),
        },
        "cdx_provenance": cdx["provenance"],
        "snapshots": snapshots,
    }
    dump(OUT / "manifest.json", manifest)
    print(json.dumps({"status": manifest["status"], "snapshots": len(snapshots), "admitted": len(ordered), "excluded": len(excluded)}))


if __name__ == "__main__":
    main()
