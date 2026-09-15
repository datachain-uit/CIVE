"""Freeze v18 targets and family inference after outcome-free screening."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from eth_transfer_v17_common import FOLDS, sha256, write_json


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    screen_path = root / "paper/input/results/llm/v18/llm_only_multicoin_screen_v18.json"
    screen = json.loads(screen_path.read_text(encoding="utf-8"))
    if screen["outcomes_consulted"] is not False or not screen["eligible_assets"]:
        raise ValueError("no outcome-free eligible asset")
    bars = {}
    for symbol in screen["eligible_assets"]:
        matches = sorted(root / "results/bybit_lifecycle_4h".glob(f"{symbol}_*.json"))
        if len(matches) != 1:
            raise ValueError(f"expected one bar artifact for {symbol}")
        bars[symbol] = {"path": str(matches[0]), "sha256": sha256(matches[0])}
    info = root / "paper/input/results/llm/llm_daily_information_sets_multisource_v2_development.json"
    extraction = root / "paper/input/results/llm/v3/llm_event_extractor_v3_9_full_development.json"
    target_builder = root / "tools/llm/build_llm_only_multicoin_targets_v18.py"
    evaluator = root / "tools/llm/evaluate_llm_only_multicoin_transfer_v18.py"
    common = root / "tools/llm/multicoin_transfer_v18_common.py"
    payload = {
        "schema_version": 1,
        "family_id": screen["family_id"],
        "stage": "PREDECLARED_BEFORE_TARGET_BUILD",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "outcomes_consulted_for_this_design": False,
        "research_status": "development transfer; historical project period is not sealed",
        "assets": {symbol: screen["assets"][symbol] for symbol in screen["eligible_assets"]},
        "eligible_assets": screen["eligible_assets"],
        "stopped_assets": screen["stopped_assets"],
        "target_contract": {"information_cutoff": "daily available_at", "entry_delay_hours": 4, "horizon_hours": 24, "price": "asset 4H bar open-to-open"},
        "folds": FOLDS,
        "model": {"family": "ridge", "alpha": 10.0, "standardization": "train fold only", "tuning": False},
        "bootstrap": {"iterations": 5000, "block_length_days": 7, "seed": 20260918},
        "per_coin_gate": "delta-MSE CI lower >0; event Pearson CI lower >0; >=3/5 MSE fold wins; nonconstant predictions",
        "family_gate": "Holm-adjusted one-sided p<0.05 for both delta-MSE and Pearson on at least one eligible coin, plus fold/nonconstant gates",
        "sources": {
            "screen": {"path": str(screen_path), "sha256": sha256(screen_path)},
            "information_sets": {"path": str(info), "sha256": sha256(info)},
            "extraction": {"path": str(extraction), "sha256": sha256(extraction)},
            "bars": bars,
            "target_builder": {"path": str(target_builder), "sha256": sha256(target_builder)},
            "evaluator": {"path": str(evaluator), "sha256": sha256(evaluator)},
            "common_helper": {"path": str(common), "sha256": sha256(common)},
        },
    }
    output = root / "paper/input/results/llm/v18/llm_only_multicoin_evaluation_v18_predeclared.json"
    write_json(output, payload)
    print(output)


if __name__ == "__main__":
    main()
