"""Compare two frozen HYB-003 text-state reliability runs."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(config: dict, left: dict, right: dict) -> dict:
    required = config["stage1_gate"]["required"]
    expected = config["frozen_contract"]["stage1_sample"]["records"]
    paired = [
        (a, b) for a, b in zip(left["records"], right["records"])
        if a.get("status") == b.get("status") == "success" and a.get("context_id") == b.get("context_id")
    ]
    categorical = {
        key: sum(a[key] == b[key] for a, b in paired)
        for key in ("affected_asset_scope", "held_long_pressure", "mechanism", "event_stage")
    }
    confidence_differences = [abs(float(a["confidence"]) - float(b["confidence"])) for a, b in paired]
    horizon_l1 = [
        sum(abs(float(a["horizon_mass"][key]) - float(b["horizon_mass"][key])) for key in ("h4", "h12", "h24", "h72"))
        for a, b in paired
    ]
    observed = {
        "records_left": len(left["records"]), "records_right": len(right["records"]),
        "success_left": left["summary"]["success"], "success_right": right["summary"]["success"],
        "paired_success": len(paired), "categorical_exact_agreement": categorical,
        "confidence_mean_absolute_difference": statistics.fmean(confidence_differences) if confidence_differences else None,
        "confidence_max_absolute_difference": max(confidence_differences, default=None),
        "horizon_mean_l1_difference": statistics.fmean(horizon_l1) if horizon_l1 else None,
        "horizon_max_l1_difference": max(horizon_l1, default=None),
        "evidence_fallbacks_left": left["summary"].get("evidence_fallbacks", 0),
        "evidence_fallbacks_right": right["summary"].get("evidence_fallbacks", 0),
    }
    checks = {
        "record_count": len(left["records"]) == len(right["records"]) == expected,
        "schema_success": left["summary"]["success"] == right["summary"]["success"] == expected,
        "context_order": [row.get("context_id") for row in left["records"]] == [row.get("context_id") for row in right["records"]],
        "asset_scope_agreement": categorical["affected_asset_scope"] >= required["affected_asset_scope_exact_min"],
        "pressure_agreement": categorical["held_long_pressure"] >= required["held_long_pressure_exact_min"],
        "mechanism_agreement": categorical["mechanism"] >= required["mechanism_exact_min"],
        "stage_agreement": categorical["event_stage"] >= required["event_stage_exact_min"],
        "confidence_mean_difference": observed["confidence_mean_absolute_difference"] is not None and observed["confidence_mean_absolute_difference"] <= required["confidence_mean_absolute_difference_max"],
        "confidence_max_difference": observed["confidence_max_absolute_difference"] is not None and observed["confidence_max_absolute_difference"] <= required["confidence_max_absolute_difference_max"],
        "horizon_mean_l1": observed["horizon_mean_l1_difference"] is not None and observed["horizon_mean_l1_difference"] <= required["horizon_mean_l1_difference_max"],
        "horizon_max_l1": observed["horizon_max_l1_difference"] is not None and observed["horizon_max_l1_difference"] <= required["horizon_max_l1_difference_max"],
        "evidence_fallback_limit": observed["evidence_fallbacks_left"] <= required["evidence_fallback_max_each_run"] and observed["evidence_fallbacks_right"] <= required["evidence_fallback_max_each_run"],
    }
    passed = all(checks.values())
    return {
        "schema_version": "tech-llm-text-state-stage1-gate-v3",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"], "outcomes_consulted": False,
        "trading_backtest_consulted": False, "observed": observed, "checks": checks,
        "passed": passed,
        "status": "stage1-pass-full-text-state-extraction-authorized" if passed else "stage1-fail-stop-before-full-extraction",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = evaluate(
        config, json.loads(args.left.read_text(encoding="utf-8")),
        json.loads(args.right.read_text(encoding="utf-8")),
    )
    result["inputs"] = {name: {"path": str(path.resolve()), "sha256": sha(path)} for name, path in {"config": args.config, "left": args.left, "right": args.right}.items()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
