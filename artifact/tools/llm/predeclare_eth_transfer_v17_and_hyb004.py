"""Freeze LLM-072 and HYB-004 contracts after outcome-free ETH feasibility passes."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from eth_transfer_v17_common import FOLDS, sha256, write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--information-sets", type=Path, required=True)
    parser.add_argument("--extraction", type=Path, required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--target-builder", type=Path, required=True)
    parser.add_argument("--llm-evaluator", type=Path, required=True)
    parser.add_argument("--hybrid-evaluator", type=Path, required=True)
    parser.add_argument("--common-helper", type=Path, required=True)
    parser.add_argument("--llm-output", type=Path, required=True)
    parser.add_argument("--hybrid-output", type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    if not audit.get("passed") or audit.get("outcomes_consulted") is not False:
        raise ValueError("outcome-free ETH feasibility audit did not pass")
    sources = {
        "information_sets": {"path": str(args.information_sets), "sha256": sha256(args.information_sets)},
        "extraction": {"path": str(args.extraction), "sha256": sha256(args.extraction)},
        "eth_bars": {"path": str(args.bars), "sha256": sha256(args.bars)},
        "eth_funding": {"path": str(args.funding), "sha256": sha256(args.funding)},
        "target_builder": {"path": str(args.target_builder), "sha256": sha256(args.target_builder)},
        "llm_evaluator": {"path": str(args.llm_evaluator), "sha256": sha256(args.llm_evaluator)},
        "hybrid_evaluator": {"path": str(args.hybrid_evaluator), "sha256": sha256(args.hybrid_evaluator)},
        "common_helper": {"path": str(args.common_helper), "sha256": sha256(args.common_helper)},
        "feasibility_audit": {"path": str(args.audit), "sha256": sha256(args.audit)},
    }
    common = {
        "schema_version": 1, "frozen_at": datetime.now(timezone.utc).isoformat(),
        "stage": "PREDECLARED_BEFORE_TARGET_BUILD", "outcomes_consulted_for_this_design": False,
        "research_status": "development-transfer; historical project period has been viewed elsewhere and is not sealed",
        "target_contract": {"asset": "ETHUSDT", "information_cutoff": "daily available_at", "entry_delay_hours": 4, "horizon_hours": 24, "price": "4H bar open-to-open"},
        "folds": FOLDS, "model": {"family": "ridge", "alpha": 10.0, "standardization": "train fold only", "tuning": False},
        "bootstrap": {"iterations": 5000, "block_length_days": 7, "seed": 20260911},
        "sources": sources,
    }
    llm = dict(common)
    llm.update({
        "experiment_id": "LLM-072-ETH-event-conditioned-transfer-v17",
        "arms": ["train-mean prior", "generic LLM-only", "event-conditioned LLM-only"],
        "primary_contrast": "event-conditioned minus generic via paired MSE",
        "gate": "delta-MSE CI lower >0; event Pearson CI lower >0; >=3/5 MSE fold wins; nonconstant predictions",
        "stop_rule": "FAIL stops before LLM-only action mapping/backtest",
    })
    hybrid = dict(common)
    hybrid.update({
        "experiment_id": "HYB-004-Bennett-adaptive-MSFE-ETH-transfer",
        "external_method": {"source": "Bennett et al. (2024)", "doi": "10.1016/j.gfj.2024.100945", "transferred_component": "adaptive combination weighted by recent MSFE", "replication": False},
        "adaptive_fusion": {"components": ["ETH causal Tech ridge", "event-conditioned LLM-only ridge"], "recent_msfe_window": 30, "weight_rule": "normalized inverse recent MSFE; only matured targets update validation history"},
        "execution": {"position": "daily sign(prediction), long or short", "one_way_cost_rate": 0.0011, "cost_components": "6 bps fee + 5 bps adverse execution", "funding": "signed sum in (entry, exit]", "fold_boundaries": "flatten and reopen"},
        "primary_contrast": "adaptive fusion minus Tech-only under identical prediction and execution calendar",
        "gate": "delta-MSE CI lower >0; mean daily net delta CI lower >0; >=3/5 MSE fold wins",
        "holdout_authorization": False,
    })
    write_json(args.llm_output, llm)
    write_json(args.hybrid_output, hybrid)
    print(json.dumps({"llm": str(args.llm_output), "hybrid": str(args.hybrid_output)}, indent=2))


if __name__ == "__main__":
    main()

