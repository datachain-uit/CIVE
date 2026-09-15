"""Outcome-free feasibility audit for direct-ETH reuse of frozen v3.9 extraction."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from eth_transfer_v17_common import ETH_ALIASES, FOLDS, is_eth_event, sha256, write_json


def audit(inputs_path: Path, extraction_path: Path, information_sets_path: Path) -> dict:
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))["records"]
    extraction = json.loads(extraction_path.read_text(encoding="utf-8"))["records"]
    info = json.loads(information_sets_path.read_text(encoding="utf-8"))["records"]
    input_ids = {row["headline_id"] for row in inputs}
    extraction_ids = {row["headline_id"] for row in extraction}
    dates = [row["information_date"] for row in info]
    events = [row for row in extraction if is_eth_event(row)]
    event_dates = {row["information_date"] for row in events}
    fold_counts = []
    for fold in FOLDS:
        valid_dates = {d for d in dates if fold["valid_start"] <= d <= fold["valid_end"]}
        fold_counts.append({
            "fold": fold["fold"], "calendar_dates": len(valid_dates),
            "eth_event_dates": len(valid_dates & event_dates),
            "eth_event_records": sum(row["information_date"] in valid_dates for row in events),
        })
    checks = {
        "extractor_input_one_to_one": len(inputs) == len(extraction) == 39393 and input_ids == extraction_ids,
        "all_extractions_successful": all(r.get("status") == "success" and r.get("error") is None for r in extraction),
        "calendar_is_frozen_1079_dates": len(dates) == 1079 and dates == sorted(dates),
        "direct_eth_records_at_least_1000": len(events) >= 1000,
        "direct_eth_dates_at_least_700": len(event_dates) >= 700,
        "each_oos_fold_has_at_least_100_eth_event_dates": all(x["eth_event_dates"] >= 100 for x in fold_counts),
        "fallback_fraction_below_0_05": (sum(r.get("evidence_fallback") is True for r in events) / len(events)) < 0.05,
    }
    passed = all(checks.values())
    return {
        "schema_version": 1,
        "experiment_id": "LLM-072-ETH-transfer-feasibility-v17",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_TARGET_AND_EVALUATION_AUTHORIZED" if passed else "FAIL_STOP_BEFORE_TARGET",
        "outcomes_consulted": False,
        "eth_alias_contract": sorted(ETH_ALIASES),
        "summary": {
            "calendar_dates": len(dates), "eth_event_records": len(events), "eth_event_dates": len(event_dates),
            "coverage_start": min(event_dates), "coverage_end": max(event_dates),
            "fallback_records": sum(r.get("evidence_fallback") is True for r in events),
            "direction_counts": dict(Counter(r["direction"] for r in events)),
            "fold_counts": fold_counts,
        },
        "checks": checks,
        "passed": passed,
        "inputs": {
            "extraction_inputs": {"path": str(inputs_path), "sha256": sha256(inputs_path)},
            "extraction": {"path": str(extraction_path), "sha256": sha256(extraction_path)},
            "information_sets": {"path": str(information_sets_path), "sha256": sha256(information_sets_path)},
        },
        "scope": "Outcome-free coverage/power screen only; no predictive or trading claim.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--extraction", type=Path, required=True)
    parser.add_argument("--information-sets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = audit(args.inputs, args.extraction, args.information_sets)
    write_json(args.output, payload)
    print(json.dumps(payload["summary"], indent=2))
    if not payload["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

