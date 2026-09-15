"""Register HYB-003 text-state v3.1 after the outcome-blind v3 operational failure."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--failure", type=Path, required=True)
    parser.add_argument("--postprocessor", type=Path, required=True)
    parser.add_argument("--base-postprocessor", type=Path, required=True)
    parser.add_argument("--regression", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = json.loads(args.base_config.read_text(encoding="utf-8"))
    failure = json.loads(args.failure.read_text(encoding="utf-8"))
    if failure.get("status") != "full-extraction-operational-fail-stop-before-model-fit":
        raise ValueError("v3 failure artifact does not authorize an operational repair")
    payload = copy.deepcopy(base)
    payload["experiment_id"] = "hyb-003-text-state-ministral3-8b-v3.1-stage1-reliability"
    payload["status"] = "predeclared-after-v3-operational-failure-before-v3.1-inference"
    payload["predeclared_at"] = "2026-09-10T00:00:00+07:00"
    payload["research_role"] = "Outcome-blind reliability rerun after exact-decimal tolerance repair; no target, policy, backtest or performance evaluation."
    payload["repair_scope"] = {
        "only_change": "Evaluate the already-frozen absolute horizon-sum tolerance 0.001 with Decimal(str(value)) rather than binary float.",
        "v3_failure": {"path": str(args.failure).replace("\\", "/"), "sha256": sha256(args.failure)},
        "restart_rule": "Two fresh reliability runs, then a fresh full extraction from record 0; v3 checkpoint is not resumed.",
    }
    contract = payload["frozen_contract"]
    contract["postprocessor"] = {"path": str(args.postprocessor).replace("\\", "/"), "sha256": sha256(args.postprocessor)}
    contract["base_postprocessor"] = {"path": str(args.base_postprocessor).replace("\\", "/"), "sha256": sha256(args.base_postprocessor)}
    contract["regression_test"] = {
        "path": str(args.regression).replace("\\", "/"), "sha256": sha256(args.regression),
        "status": "passed-before-v3.1-predeclaration",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output)}))


if __name__ == "__main__":
    main()
