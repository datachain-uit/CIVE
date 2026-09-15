"""Freeze the outcome-blind text aggregation and Stage-B power gate for HYB-003."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--extraction", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--aggregator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    gate = json.loads(args.gate.read_text(encoding="utf-8"))
    if not gate.get("passed"):
        raise ValueError("full extraction gate has not passed")
    payload = {
        "schema_version": "tech-llm-conditional-state-stage-b-predeclaration-v3.1",
        "experiment_id": "HYB-003", "status": "predeclared-before-stage-b-audit",
        "research_role": "Outcome-blind aggregation plus post-outcome feasibility/power diagnostic; no learner fit, action mapping or performance evaluation.",
        "frozen_contract": {
            "panel": {"path": str(args.panel).replace("\\", "/"), "sha256": sha256(args.panel)},
            "extraction": {"path": str(args.extraction).replace("\\", "/"), "sha256": sha256(args.extraction), "records": 2534},
            "full_gate": {"path": str(args.gate).replace("\\", "/"), "sha256": sha256(args.gate)},
            "aggregator": {"path": str(args.aggregator).replace("\\", "/"), "sha256": sha256(args.aggregator)},
        },
        "aggregation": {
            "deduplication": "exact headline_id only", "no_semantic_cross_domain_deduplication": True,
            "scope_weights": {"direct_held": 1.0, "crypto_systemic": 0.75, "other": 0.0, "unknown": 0.0},
            "forward_decay": "retain horizon mass only while elapsed hours are below 4, 12, 24 or 72 respectively",
            "unknown_and_two_sided": "no adverse or supportive mass",
        },
        "power_gate": {
            "minimum_panel_trade_clusters": 20, "minimum_text_trade_clusters": 12,
            "minimum_new_text_decisions": 50, "minimum_applicable_trade_clusters": 12,
            "minimum_adverse_mass": 0.25,
            "economic_mde_rule": "all-decision normal 80%-power, two-sided 5% MDE must not exceed the median one-bar registered overlay cost",
        },
        "prohibited": ["T1/T2/T3 fitting", "policy/action mapping", "performance evaluation", "semantic event clustering after seeing outcomes"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output)}, indent=2))


if __name__ == "__main__":
    main()
