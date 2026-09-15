"""Record an irreversible Stage-1 challenger failure from a partial operational run."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from llm_causal_pipeline import write_json


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(config: dict, partial_run: dict) -> dict:
    candidate = config["candidate"]
    contract = config["frozen_input_contract"]
    gate = config["stage1_operational_gate"]
    required = gate["required"]
    expected = int(gate["expected_information_sets"])

    if partial_run.get("model_digest") != candidate["digest"]:
        raise ValueError("candidate digest does not match predeclaration")
    if partial_run.get("prompt_version") != contract["prompt_version"]:
        raise ValueError("prompt version does not match predeclaration")
    if partial_run.get("prompt_hash") != contract["prompt_hash"]:
        raise ValueError("prompt hash does not match predeclaration")

    records = list(partial_run.get("records", []))
    observed = len(records)
    success = sum(record.get("status") == "success" for record in records)
    errors = observed - success
    required_success = int(required["schema_success_each_run"])
    if observed <= 0 or observed > expected:
        raise ValueError("partial run record count is outside the Stage-1 range")
    if errors <= 0:
        raise ValueError("fail-fast evaluation requires at least one schema error")

    maximum_possible_success = success + (expected - observed)
    irreversible = maximum_possible_success < required_success
    if not irreversible:
        raise ValueError("the observed failure is not mathematically irreversible")

    return {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "candidate": candidate,
        "market_outcomes_consulted": False,
        "trading_backtest_consulted": False,
        "stage1_partial_run": {
            "expected_information_sets": expected,
            "observed_information_sets": observed,
            "schema_success": success,
            "schema_errors": errors,
            "required_schema_success": required_success,
            "maximum_possible_schema_success_if_completed": maximum_possible_success,
        },
        "passed": False,
        "status": "stage1-fail-fast-stop-before-completing-run1",
        "stopping_rule_basis": (
            "schema success must equal the full expected sample; after the first schema error, "
            "the required count is mathematically unreachable"
        ),
        "next_action": "stop before run 2, full inference, calibration and trading backtest",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--partial-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = evaluate(
        json.loads(args.config.read_text(encoding="utf-8")),
        json.loads(args.partial_run.read_text(encoding="utf-8")),
    )
    payload["inputs"] = {
        "config": str(args.config),
        "config_sha256": file_hash(args.config),
        "partial_run": str(args.partial_run),
        "partial_run_sha256": file_hash(args.partial_run),
    }
    write_json(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
