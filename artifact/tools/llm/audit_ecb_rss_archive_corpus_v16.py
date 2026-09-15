#!/usr/bin/env python3
"""Audit the frozen outcome-blind ECB RSS Internet Archive corpus v16."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_corpus_v16"
CORPUS = BASE / "corpus.json"
EXCLUDED = BASE / "excluded.json"
MANIFEST = BASE / "manifest.json"
PREDECLARED = BASE / "predeclared.json"
OUTPUT = BASE / "corpus_gate.json"
MINIMUM = 96


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamp lacks offset")
    return result


def audit() -> dict:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    excluded = json.loads(EXCLUDED.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    predeclared = json.loads(PREDECLARED.read_text(encoding="utf-8"))
    records = corpus["records"]
    times = sorted({record["archive_capture_at"] for record in records}, key=parse)
    checks = {
        "predeclaration_frozen_before_corpus_build": predeclared.get("status")
        == "FROZEN_BEFORE_FULL_SNAPSHOT_DOWNLOAD",
        "outcome_blind": corpus.get("selection_uses_outcomes") is False
        and corpus.get("market_data_accessed") is False
        and corpus.get("model_run") is False,
        "manifest_outcome_blind": manifest.get("selection_uses_outcomes") is False
        and manifest.get("market_data_accessed") is False
        and manifest.get("model_run") is False
        and manifest.get("trading_backtest_consulted") is False,
        "manifest_hashes_match": manifest["files"]["corpus.json"] == sha(CORPUS)
        and manifest["files"]["excluded.json"] == sha(EXCLUDED)
        and manifest["files"]["predeclared.json"] == sha(PREDECLARED),
        "record_count_matches": manifest["admitted_records"] == len(records),
        "information_set_count_matches": manifest["information_sets"] == len(times),
        "unique_record_ids": len({record["record_id"] for record in records}) == len(records),
        "unique_canonical_links": len({record["canonical_link"] for record in records}) == len(records),
        "timestamps_ordered": all(
            parse(records[index]["archive_capture_at"]) <= parse(records[index + 1]["archive_capture_at"])
            for index in range(len(records) - 1)
        ),
        "publisher_time_not_after_information_time": all(
            parse(record["publisher_pubdate"]) <= parse(record["archive_capture_at"]) for record in records
        ),
        "title_only_contract": all(
            record["title"] and record["text"] == f'TITLE: {record["title"]}' for record in records
        ),
        "minimum_information_sets_met": len(times) >= MINIMUM,
    }
    passed = all(checks.values())
    reason_classes = Counter(
        "publisher_pubdate_without_explicit_offset"
        if str(record.get("reason", "")).startswith("Invalid date value or format")
        else str(record.get("reason", ""))
        for record in excluded["records"]
    )
    return {
        "schema_version": "ecb-rss-archive-corpus-gate-v16",
        "status": "OUTCOME_BLIND_CORPUS_GATE_PASS_EXTRACTION_AUTHORIZED"
        if passed
        else "OUTCOME_BLIND_CORPUS_GATE_FAIL_STOP",
        "passed": passed,
        "extraction_authorized": passed,
        "target_join_authorized": False,
        "outcomes_consulted": False,
        "market_data_accessed": False,
        "model_run": False,
        "counts": {
            "downloaded_snapshots": manifest["snapshot_count"],
            "parseable_snapshots": manifest["parseable_snapshots"],
            "corpus_records": len(records),
            "information_sets": len(times),
            "minimum_information_sets": MINIMUM,
            "excluded_item_or_snapshot_records": len(excluded["records"]),
        },
        "information_time_range": {"first": times[0] if times else None, "last": times[-1] if times else None},
        "exclusion_reason_classes": dict(sorted(reason_classes.items())),
        "checks": checks,
        "inputs": {
            name: {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha(path),
            }
            for name, path in (
                ("corpus", CORPUS),
                ("excluded", EXCLUDED),
                ("manifest", MANIFEST),
                ("predeclared", PREDECLARED),
                ("auditor", Path(__file__)),
            )
        },
        "interpretation": (
            "Pass authorizes only outcome-blind LLM extraction from the frozen title-only corpus. "
            "Market targets, predictive metrics, thresholds, backtests, Tech+LLM, and sealed holdout remain prohibited."
        ),
    }


def main() -> None:
    result = audit()
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()


