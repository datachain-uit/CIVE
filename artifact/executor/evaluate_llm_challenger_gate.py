"""Evaluate a predeclared LLM challenger reliability gate without market outcomes."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from llm_causal_pipeline import write_json


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(config: dict, audit: dict, left: dict, right: dict) -> dict:
    candidate = config["candidate"]
    contract = config["frozen_input_contract"]
    gate = config["stage1_operational_gate"]
    required = gate["required"]
    expected = int(gate["expected_information_sets"])

    for payload in (audit, left, right):
        if payload.get("model_digest") != candidate["digest"]:
            raise ValueError("candidate digest does not match predeclaration")
        if payload.get("prompt_version") != contract["prompt_version"]:
            raise ValueError("prompt version does not match predeclaration")
        if payload.get("prompt_hash") != contract["prompt_hash"]:
            raise ValueError("prompt hash does not match predeclaration")

    checks = {
        "information_sets": {
            "observed": audit["information_sets"],
            "required": expected,
            "passed": audit["information_sets"] == expected,
        },
        "schema_success_run1": {
            "observed": left["summary"]["success"],
            "required": required["schema_success_each_run"],
            "passed": left["summary"]["success"] == required["schema_success_each_run"]
            and left["summary"]["errors"] == 0,
        },
        "schema_success_run2": {
            "observed": right["summary"]["success"],
            "required": required["schema_success_each_run"],
            "passed": right["summary"]["success"] == required["schema_success_each_run"]
            and right["summary"]["errors"] == 0,
        },
        "exact_score_agreement": {
            "observed": audit["exact_score_agreement"],
            "required_min": required["exact_score_agreement_min"],
            "passed": audit["exact_score_agreement"] >= required["exact_score_agreement_min"],
        },
        "long_flat_action_agreements": {
            "observed": audit["long_flat_action_agreements"],
            "required_min": required["long_flat_action_agreements_min"],
            "passed": audit["long_flat_action_agreements"]
            >= required["long_flat_action_agreements_min"],
        },
        "mean_absolute_score_difference": {
            "observed": audit["mean_absolute_score_difference"],
            "required_max": required["mean_absolute_score_difference_max"],
            "passed": audit["mean_absolute_score_difference"]
            <= required["mean_absolute_score_difference_max"],
        },
        "max_absolute_score_difference": {
            "observed": audit["max_absolute_score_difference"],
            "required_max": required["max_absolute_score_difference_max"],
            "passed": audit["max_absolute_score_difference"]
            <= required["max_absolute_score_difference_max"],
        },
    }
    passed = all(check["passed"] for check in checks.values())
    return {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "candidate": candidate,
        "market_outcomes_consulted": False,
        "trading_backtest_consulted": False,
        "checks": checks,
        "passed": passed,
        "status": (
            "stage1-pass-full-calibration-authorized"
            if passed
            else "stage1-fail-stop-before-full-inference"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = evaluate(
        json.loads(args.config.read_text(encoding="utf-8")),
        json.loads(args.audit.read_text(encoding="utf-8")),
        json.loads(args.left.read_text(encoding="utf-8")),
        json.loads(args.right.read_text(encoding="utf-8")),
    )
    payload["inputs"] = {
        "config": str(args.config),
        "config_sha256": file_hash(args.config),
        "audit": str(args.audit),
        "audit_sha256": file_hash(args.audit),
        "left": str(args.left),
        "left_sha256": file_hash(args.left),
        "right": str(args.right),
        "right_sha256": file_hash(args.right),
    }
    write_json(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
