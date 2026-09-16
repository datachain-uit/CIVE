"""Outcome-free effective-sample audit for HYB-006."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from hyb005_cross_asset_common import SYMBOLS, read_json, sha256, write_json
from hyb006_rank_pair_common import construct_assignments


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    daily_dir = Path(r"D:\projects\auto-trading\results\bybit_lifecycle_daily")
    events = root / "paper/input/results/llm/v3/llm_event_extractor_v3_9_full_development.json"
    inputs = root / "paper/input/results/llm/v3/llm_event_extraction_inputs_v3_development.json"
    predeclared_path = root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_predeclared.json"
    predeclared = read_json(predeclared_path)
    if predeclared["status"] != "PREDECLARED_BEFORE_SAMPLE_AUDIT" or predeclared["outcomes_consulted"] is not False:
        raise ValueError("invalid HYB-006 predeclaration")
    built = construct_assignments(daily_dir, events, inputs)
    rows = built["rows"]
    active = [row for row in rows if row["active"]]
    cut1, cut2 = len(rows) // 3, 2 * len(rows) // 3
    thirds = [rows[:cut1], rows[cut1:cut2], rows[cut2:]]
    active_by_third = [sum(row["active"] for row in part) for part in thirds]
    selected_by_asset = {symbol: sum(symbol in row["selected"] for row in rows) for symbol in SYMBOLS}
    thresholds = dict(predeclared["sample_gate"])
    checks = {
        "pair_days": len(rows) >= thresholds["minimum_pair_days"] and all(len(row["selected"]) == 2 for row in rows),
        "active_days": len(active) >= thresholds["minimum_active_days"],
        "active_each_third": all(value >= thresholds["minimum_active_days_each_chronological_third"] for value in active_by_third),
        "selected_each_asset": all(value >= thresholds["minimum_selected_days_each_asset"] for value in selected_by_asset.values()),
        "weights_capital_neutral": all(abs(sum(row["primary_weights"].values()) - 1.0) < 1e-12 for row in rows),
        "weight_bounds": all(all(0.0 <= weight <= 0.75 for weight in row["primary_weights"].values()) for row in rows),
    }
    passed = all(checks.values())
    payload = {
        "schema_version": "hyb006-rank-pair-feasibility-v1",
        "experiment_id": "HYB-006",
        "status": "PASS_FREEZE_AND_EVALUATE_AUTHORIZED" if passed else "FAIL_STOP_BEFORE_TARGET_EVALUATION",
        "passed": passed,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "outcomes_consulted": False,
        "audit_contract": "Momentum ranks, selected pairs, text availability, weights and sample counts only; no next-day return or PnL is read.",
        "predeclaration": {"path": str(predeclared_path), "sha256": sha256(predeclared_path)},
        "coverage": built["coverage"],
        "sample": {
            "pair_days": len(rows),
            "active_days": len(active),
            "active_days_by_chronological_third": active_by_third,
            "selected_days_by_asset": selected_by_asset,
            "selected_pair_counts": dict(Counter("+".join(sorted(row["selected"])) for row in rows)),
        },
        "thresholds": thresholds,
        "checks": checks,
        "next_authorized_action": "Materialize frozen assignment panel and run exactly the predeclared evaluation." if passed else "Stop HYB-006.",
    }
    output = root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_feasibility.json"
    write_json(output, payload)
    print(json.dumps({"status": payload["status"], "sample": payload["sample"], "checks": checks, "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
