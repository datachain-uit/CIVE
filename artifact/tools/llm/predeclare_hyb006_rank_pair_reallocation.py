"""Write the outcome-free HYB-006 design freeze before any sample audit."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from hyb005_cross_asset_common import sha256, write_json


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    daily_dir = root / "results/bybit_lifecycle_daily"
    events = root / "paper/input/results/llm/v3/llm_event_extractor_v3_9_full_development.json"
    inputs = root / "paper/input/results/llm/v3/llm_event_extraction_inputs_v3_development.json"
    protocol = root / "paper/working/protocols/Tech_LLM_Rank_Pair_Reallocation_Protocol_HYB006.md"
    scripts = [
        root / "tools/llm/hyb005_cross_asset_common.py",
        root / "tools/llm/hyb006_rank_pair_common.py",
        root / "tools/llm/audit_hyb006_rank_pair_reallocation.py",
        root / "tools/llm/evaluate_hyb006_rank_pair_reallocation.py",
    ]
    daily = []
    for symbol in ("BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT"):
        path = next(daily_dir.glob(f"{symbol}_*.json"))
        daily.append({"symbol": symbol, "path": str(path), "sha256": sha256(path)})
    payload = {
        "schema_version": "hyb006-rank-pair-predeclaration-v1",
        "experiment_id": "HYB-006",
        "status": "PREDECLARED_BEFORE_SAMPLE_AUDIT",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "outcomes_consulted": False,
        "research_role": "exploratory development transfer diagnostic; not canonical Tech-Control, validation, holdout or live evidence",
        "rationale": "Daily Tech momentum rank defines a persistent two-asset estimand; LLM may only reallocate within that frozen pair.",
        "selection": {"universe": ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT"], "rank_feature": "close_t / close_t-20 - 1", "top_n": 2, "tie_break": "ticker ascending"},
        "weights": {"tech": "0.5/0.5", "llm": "w_first=clip(0.5+0.25*(score_first-score_second),0.25,0.75); w_second=1-w_first", "gross_exposure": 1.0},
        "sample_gate": {"minimum_pair_days": 1000, "minimum_active_days": 600, "minimum_active_days_each_chronological_third": 150, "minimum_selected_days_each_asset": 50},
        "evaluation": {
            "target": "next daily close-to-close simple return",
            "turnover": "first day sum(abs(w)); thereafter 0.5*sum(abs(w_t-w_t-1))",
            "cost_bps_per_unit_turnover": 10,
            "primary_contrast": "LLM primary net daily return minus Tech equal-weight net daily return",
            "bootstrap": {"replicates": 5000, "moving_block_days": 7, "seed": 20260912},
            "folds": 5,
            "placebos": ["opposite-sign", "one-day-delayed", "deterministically-shuffled-tilts"],
            "pass_rule": "paired mean net delta 95% block-bootstrap CI lower > 0; positive delta in >=3/5 folds; primary mean net return exceeds every placebo; LLM MDD no more than 5 percentage points worse than Tech",
        },
        "inputs": {
            "events": {"path": str(events), "sha256": sha256(events)},
            "extractor_inputs": {"path": str(inputs), "sha256": sha256(inputs)},
            "daily_candles": daily,
            "protocol": {"path": str(protocol), "sha256": sha256(protocol)},
            "scripts": [{"path": str(path), "sha256": sha256(path)} for path in scripts],
        },
        "next_authorized_action": "Run outcome-free effective-sample audit only.",
    }
    output = root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_predeclared.json"
    write_json(output, payload)
    print(output)


if __name__ == "__main__":
    main()
