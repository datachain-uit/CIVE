"""Record an irreversible Stage 1 failure from a partial extractor run."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--partial-run", type=Path, required=True)
    parser.add_argument("--run-number", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    run = json.loads(args.partial_run.read_text(encoding="utf-8"))
    expected = config["frozen_contract"]["stage1_sample"]["records"]
    observed = len(run["records"])
    errors = run["summary"]["errors"]
    if errors < 1:
        raise ValueError("fail-fast evaluation requires at least one recorded error")
    result = {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "outcomes_consulted": False,
        "trading_backtest_consulted": False,
        "passed": False,
        "status": "stage1-fail-fast-stop-before-full-extraction",
        "observed": {
            "failed_run_number": args.run_number,
            "records_attempted": observed,
            "schema_success": run["summary"]["success"],
            "errors": errors,
            "maximum_possible_schema_success": expected - errors,
            "required_schema_success": config["stage1_gate"]["required"]["schema_success_each_run"],
        },
        "inputs": {
            "config": {"path": str(args.config), "sha256": sha256(args.config)},
            "partial_run": {"path": str(args.partial_run), "sha256": sha256(args.partial_run)},
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
