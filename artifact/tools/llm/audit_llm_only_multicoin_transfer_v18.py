"""Outcome-free coverage screen for BTC/XRP/SOL/BNB transfer v18."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from eth_transfer_v17_common import FOLDS, sha256, write_json
from multicoin_transfer_v18_common import ASSETS, is_asset_event


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    pre_path = root / "paper/input/results/llm/v18/llm_only_multicoin_screen_v18_predeclared.json"
    pre = json.loads(pre_path.read_text(encoding="utf-8"))
    if pre["stage"] != "PREDECLARED_BEFORE_OUTCOME_FREE_SCREEN" or pre["outcomes_consulted"] is not False:
        raise ValueError("invalid v18 screen predeclaration")
    for item in [pre["sources"]["protocol"], *pre["sources"]["scripts"]]:
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"frozen screen source changed: {item['path']}")
    inputs = json.loads(Path(pre["sources"]["extraction_inputs"]["path"]).read_text(encoding="utf-8"))["records"]
    extraction = json.loads(Path(pre["sources"]["extraction"]["path"]).read_text(encoding="utf-8"))["records"]
    info = json.loads(Path(pre["sources"]["information_sets"]["path"]).read_text(encoding="utf-8"))["records"]
    input_ids = {row["headline_id"] for row in inputs}
    extraction_ids = {row["headline_id"] for row in extraction}
    dates = [row["information_date"] for row in info]
    thresholds = pre["thresholds"]
    results = {}
    for symbol, spec in ASSETS.items():
        aliases = set(spec["aliases"])
        events = [row for row in extraction if is_asset_event(row, aliases)]
        event_dates = {row["information_date"] for row in events}
        fold_counts = []
        for fold in FOLDS:
            valid_dates = {date for date in dates if fold["valid_start"] <= date <= fold["valid_end"]}
            fold_counts.append({
                "fold": fold["fold"],
                "calendar_dates": len(valid_dates),
                "event_dates": len(valid_dates & event_dates),
                "event_records": sum(row["information_date"] in valid_dates for row in events),
            })
        fallback = sum(row.get("evidence_fallback") is True for row in events)
        checks = {
            "extractor_input_one_to_one": len(inputs) == len(extraction) == 39393 and input_ids == extraction_ids,
            "all_extractions_successful": all(row.get("status") == "success" and row.get("error") is None for row in extraction),
            "calendar_is_frozen_1079_dates": len(dates) == 1079 and dates == sorted(dates),
            "direct_records": len(events) >= thresholds["minimum_direct_event_records"],
            "direct_dates": len(event_dates) >= thresholds["minimum_direct_event_dates"],
            "each_oos_fold": all(item["event_dates"] >= thresholds["minimum_event_dates_each_oos_fold"] for item in fold_counts),
            "fallback_fraction": bool(events) and fallback / len(events) < thresholds["maximum_evidence_fallback_fraction"],
        }
        passed = all(checks.values())
        results[symbol] = {
            "experiment_id": spec["experiment_id"],
            "aliases": sorted(aliases),
            "passed": passed,
            "status": "PASS_TARGET_AND_EVALUATION_PREDECLARATION_AUTHORIZED" if passed else "FAIL_STOP_BEFORE_TARGET",
            "summary": {
                "calendar_dates": len(dates),
                "event_records": len(events),
                "event_dates": len(event_dates),
                "coverage_start": min(event_dates) if event_dates else None,
                "coverage_end": max(event_dates) if event_dates else None,
                "fallback_records": fallback,
                "fallback_fraction": fallback / len(events) if events else None,
                "direction_counts": dict(Counter(row["direction"] for row in events)),
                "fold_counts": fold_counts,
            },
            "checks": checks,
        }
    payload = {
        "schema_version": 1,
        "family_id": pre["family_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "SCREEN_COMPLETE",
        "outcomes_consulted": False,
        "predeclaration": {"path": str(pre_path), "sha256": sha256(pre_path)},
        "thresholds": thresholds,
        "assets": results,
        "eligible_assets": [symbol for symbol, result in results.items() if result["passed"]],
        "stopped_assets": [symbol for symbol, result in results.items() if not result["passed"]],
        "next_authorized_action": "Predeclare target/evaluation only for eligible_assets.",
    }
    output = root / "paper/input/results/llm/v18/llm_only_multicoin_screen_v18.json"
    write_json(output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
