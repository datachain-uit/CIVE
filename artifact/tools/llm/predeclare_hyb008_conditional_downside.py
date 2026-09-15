"""Freeze HYB-008 before its outcome-free sample audit."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from hyb008_conditional_downside_common import sha, write


def main():
    root = Path(__file__).resolve().parents[2]
    protocol = root / "paper/working/protocols/Tech_LLM_Conditional_Downside_Protocol_HYB008.md"
    panel = root / "paper/input/results/llm/v20/llm_only_multicoin_short_panel_v20.json"
    tech = root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_daily_panel.json"
    scripts = [root / "tools/llm/hyb008_conditional_downside_common.py", root / "tools/llm/audit_hyb008_conditional_downside.py", root / "tools/llm/evaluate_hyb008_conditional_downside.py"]
    bars = [root / "results/bybit_lifecycle_4h" / f"{s}_1660348800000_1786492800000.json" for s in ("ETHUSDT", "SOLUSDT")]
    result = {
        "schema_version": 1,
        "experiment_id": "HYB-008",
        "status": "FROZEN_BEFORE_SAMPLE_AUDIT",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "research_role": "historical post-outcome development information gate; not validation, holdout, live evidence or economic value",
        "researcher_prior_outcome_awareness": "HYB-001--007 and LLM-only v20 results were seen; HYB-008-specific predictions and metrics were not computed before this freeze.",
        "population": "ETH/SOL v20 event buckets where historical HYB-006 Tech rank-pair selected the same asset",
        "target": "next 4h return <= asset-specific training-fold q10",
        "models": {"type": "LogisticRegression L2", "C": 1.0, "solver": "lbfgs", "max_iter": 2000, "scaler": "StandardScaler fit in training fold", "arms": ["tech", "tech_metadata", "tech_generic", "tech_event", "event_permuted_shift17"]},
        "sample_gate": {"rows_min": 900, "eth_min": 500, "sol_min": 300, "each_third_min": 250, "utc_dates_min": 400, "history_coverage_min": 0.95},
        "evaluation": {"initial_train_date_fraction": 0.30, "test_folds": 5, "primary_contrast": "paired Brier(tech_generic)-Brier(tech_event)", "bootstrap_unit": "UTC date", "bootstrap_draws": 10000, "seed": 20260914, "permutation_shift": 17},
        "pass_rule": ["primary Brier improvement CI95 lower > 0", "tech_event Brier < tech, tech_metadata, tech_generic, event_permuted", "tech_event beats tech_generic in >=3/5 folds", "tech_event AUC > tech_generic AUC", "nonconstant predictions and both classes in every fold"],
        "inputs": {"protocol": {"path": str(protocol), "sha256": sha(protocol)}, "v20_panel": {"path": str(panel), "sha256": sha(panel)}, "tech_assignments": {"path": str(tech), "sha256": sha(tech)}, "bars": [{"path": str(p), "sha256": sha(p)} for p in bars], "scripts": [{"path": str(p), "sha256": sha(p)} for p in scripts]},
        "next_authorized_action": "Run outcome-free sample audit only.",
    }
    out = root / "paper/input/results/hybrid/hyb008_conditional_downside_predeclared.json"
    write(out, result)
    print(json.dumps({"path": str(out), "sha256": sha(out)}, indent=2))


if __name__ == "__main__":
    main()
