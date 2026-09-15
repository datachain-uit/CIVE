"""Freeze HYB-003 full text-state extraction after the Stage-1 gate passes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage1-config", type=Path, required=True)
    parser.add_argument("--stage1-gate", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = json.loads(args.stage1_config.read_text(encoding="utf-8"))
    gate = json.loads(args.stage1_gate.read_text(encoding="utf-8"))
    if not gate.get("passed") or gate.get("status") != "stage1-pass-full-text-state-extraction-authorized":
        raise ValueError("Stage-1 gate does not authorize full extraction")
    full_input = base["frozen_contract"]["full_input"]
    contract = dict(base["frozen_contract"])
    contract["stage1_sample"] = {**full_input, "role": "operational full-input binding for frozen scorer"}
    contract["audit"] = {"path": str(args.audit).replace("\\", "/"), "sha256": sha256(args.audit)}
    contract["expected_batches_per_run"] = (int(full_input["records"]) + int(contract["batch_size"]) - 1) // int(contract["batch_size"])
    payload = {
        "schema_version": 1,
        "experiment_id": "hyb-003-text-state-ministral3-8b-v3-full-extraction",
        "status": "predeclared-after-stage1-pass-before-full-extraction",
        "predeclared_at": "2026-09-10T00:00:00+07:00",
        "research_role": "One outcome-blind extraction over all frozen HYB-003 context-headline rows; no target, learner, action mapping or performance evaluation.",
        "candidate": base["candidate"],
        "authorization": {
            "stage1_gate": {"path": str(args.stage1_gate).replace("\\", "/"), "sha256": sha256(args.stage1_gate)},
            "passed": True,
        },
        "frozen_contract": contract,
        "completion_gate": {
            "required": {
                "records": int(full_input["records"]),
                "schema_success": int(full_input["records"]),
                "context_id_match": int(full_input["records"]),
                "headline_id_match": int(full_input["records"]),
                "evidence_exact_substring": int(full_input["records"]),
                "evidence_fallback_max": 260,
            },
            "decision": "Every requirement must pass before power/economic-MDE freeze or T1/T3 fitting.",
        },
        "prohibited": base["prohibited"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output), "records": full_input["records"]}))


if __name__ == "__main__":
    main()
