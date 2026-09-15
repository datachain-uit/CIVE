#!/usr/bin/env python3
"""Audit the frozen outcome-blind SEC RSS corpus before any LLM work."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "paper" / "input" / "results" / "llm" / "v14" / "sec_rss_archive_corpus_v14"
ALLOWED_RECORD_FIELDS = {
    "record_id", "guid", "text", "title", "description", "link", "publisher_pubdate",
    "archive_capture_at", "archive_capture", "archive_digest", "archive_length", "snapshot_sha256",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    corpus_path = OUT / "corpus.json"
    manifest_path = OUT / "manifest.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    records = corpus["records"]
    checks = {
        "outcome_blind_flags": corpus["selection_uses_outcomes"] is False and corpus["market_data_accessed"] is False and corpus["model_run"] is False,
        "information_time_is_archive_capture": corpus["information_time"] == "archive_capture_at",
        "records_nonempty": bool(records),
        "exact_record_schema": all(set(record) == ALLOWED_RECORD_FIELDS for record in records),
        "unique_record_ids": len({record["record_id"] for record in records}) == len(records),
        "unique_guids": len({record["guid"] for record in records}) == len(records),
        "text_contract": all(record["text"] == f"TITLE: {record['title']}\nDESCRIPTION: {record['description']}" for record in records),
        "no_market_or_outcome_fields": all(not ({"price", "return", "label", "outcome", "feature", "reflection", "candle", "ohlcv"} & set(record)) for record in records),
        "timestamps_have_offsets": True,
        "publisher_not_after_availability": True,
        "availability_time_ordered": True,
    }
    prior: datetime | None = None
    for record in records:
        publisher_time = datetime.fromisoformat(record["publisher_pubdate"])
        availability_time = datetime.fromisoformat(record["archive_capture_at"])
        if publisher_time.tzinfo is None or publisher_time.utcoffset() is None or availability_time.tzinfo is None or availability_time.utcoffset() is None:
            checks["timestamps_have_offsets"] = False
        if publisher_time.astimezone(timezone.utc) > availability_time.astimezone(timezone.utc):
            checks["publisher_not_after_availability"] = False
        if prior is not None and availability_time < prior:
            checks["availability_time_ordered"] = False
        prior = availability_time
    audit = {
        "schema_version": 1,
        "corpus_id": corpus["corpus_id"],
        "status": "DATA_GATE_PASS_OUTCOME_BLIND_CORPUS_READY_FOR_PROTOCOL_FREEZE" if all(checks.values()) else "DATA_GATE_FAIL_STOP",
        "passed": all(checks.values()),
        "records": len(records),
        "checks": checks,
        "predictive_feature_contract": "No corpus field is an allowed predictive feature before a separate LLM event-vector protocol is frozen. Archive provenance may be used only for PIT ordering and audit.",
        "inputs": {
            "corpus.json": sha256(corpus_path),
            "manifest.json": sha256(manifest_path),
            "audit_sec_rss_archive_corpus_v14.py": sha256(Path(__file__)),
        },
        "market_data_accessed": False,
        "model_run": False,
    }
    (OUT / "schema_audit.json").write_text(json.dumps(audit, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"status": audit["status"], "records": len(records)}))


if __name__ == "__main__":
    main()
