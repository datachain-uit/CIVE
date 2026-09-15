"""Evaluate the predeclared full-inference calibration gate without a trading backtest."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from llm_causal_pipeline import write_json


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(config: dict, stage1: dict, full_run: dict, calibration: dict) -> dict:
    if not stage1.get("passed"):
        raise ValueError("stage 1 did not authorize full inference")
    candidate = config["candidate"]
    contract = config["frozen_input_contract"]
    gate = config["stage2_only_if_stage1_passes"]
    required = gate["required"]

    if full_run.get("model_digest") != candidate["digest"]:
        raise ValueError("full-run digest does not match predeclaration")
    if full_run.get("prompt_version") != contract["prompt_version"]:
        raise ValueError("full-run prompt version does not match predeclaration")
    if full_run.get("prompt_hash") != contract["prompt_hash"]:
        raise ValueError("full-run prompt hash does not match predeclaration")

    overall = calibration["overall"]
    pearson_ci = calibration["uncertainty"]["pearson_score_forward_return_95_ci"]
    spread_ci = calibration["uncertainty"]["long_minus_flat_mean_bps_95_ci"]
    checks = {
        "full_records": {
            "observed": len(full_run["records"]),
            "required": 2927,
            "passed": len(full_run["records"]) == 2927,
        },
        "schema_errors": {
            "observed": full_run["summary"]["errors"],
            "required": required["schema_errors"],
            "passed": full_run["summary"]["errors"] == required["schema_errors"],
        },
        "calibration_observations": {
            "observed": overall["observations"],
            "required_min": gate["minimum_observations"],
            "passed": overall["observations"] >= gate["minimum_observations"],
        },
        "long_rule_observations": {
            "observed": overall["long_rule"]["observations"],
            "required_min": gate["minimum_long_rule_observations"],
            "passed": overall["long_rule"]["observations"]
            >= gate["minimum_long_rule_observations"],
        },
        "pearson_ci_lower_bound": {
            "observed": pearson_ci[0],
            "required_gt": required["pearson_score_forward_return_95_ci_lower_bound_gt"],
            "passed": pearson_ci[0]
            > required["pearson_score_forward_return_95_ci_lower_bound_gt"],
        },
        "long_minus_flat_ci_lower_bound": {
            "observed": spread_ci[0],
            "required_gt": required["long_minus_flat_mean_bps_95_ci_lower_bound_gt"],
            "passed": spread_ci[0]
            > required["long_minus_flat_mean_bps_95_ci_lower_bound_gt"],
        },
    }
    passed = all(check["passed"] for check in checks.values())
    return {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "candidate": candidate,
        "stage1_gate_passed": True,
        "trading_backtest_consulted": False,
        "checks": checks,
        "passed": passed,
        "status": (
            "stage2-pass-full-repeat-authorized"
            if passed
            else "stage2-fail-stop-before-repeat-or-backtest"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--stage1", type=Path, required=True)
    parser.add_argument("--full-run", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = evaluate(
        json.loads(args.config.read_text(encoding="utf-8")),
        json.loads(args.stage1.read_text(encoding="utf-8")),
        json.loads(args.full_run.read_text(encoding="utf-8")),
        json.loads(args.calibration.read_text(encoding="utf-8")),
    )
    payload["inputs"] = {
        "config": str(args.config),
        "config_sha256": file_hash(args.config),
        "stage1": str(args.stage1),
        "stage1_sha256": file_hash(args.stage1),
        "full_run": str(args.full_run),
        "full_run_sha256": file_hash(args.full_run),
        "calibration": str(args.calibration),
        "calibration_sha256": file_hash(args.calibration),
    }
    write_json(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
