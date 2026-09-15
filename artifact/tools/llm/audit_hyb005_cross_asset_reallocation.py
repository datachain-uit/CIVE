"""Outcome-free effective-sample audit for HYB-005."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from hyb005_cross_asset_common import SYMBOLS, construct_assignments, sha256, write_json


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    daily_dir = root / "results/bybit_lifecycle_daily"
    events = root / "paper/input/results/llm/v3/llm_event_extractor_v3_9_full_development.json"
    inputs = root / "paper/input/results/llm/v3/llm_event_extraction_inputs_v3_development.json"
    output = root / "paper/input/results/hybrid/hyb005_cross_asset_reallocation_feasibility.json"
    built = construct_assignments(daily_dir, events, inputs)
    rows = built["rows"]
    pair_rows = [row for row in rows if len(row["selected"]) == 2]
    active = [row for row in pair_rows if row["active"]]
    cut1, cut2 = len(rows) // 3, 2 * len(rows) // 3
    thirds = [rows[:cut1], rows[cut1:cut2], rows[cut2:]]
    active_by_third = [sum(len(row["selected"]) == 2 and row["active"] for row in part) for part in thirds]
    thresholds = {
        "minimum_total_days": 1000,
        "minimum_two_position_days": 100,
        "minimum_active_reallocation_days": 60,
        "minimum_active_days_each_chronological_third": 15,
    }
    checks = {
        "total_days": len(rows) >= thresholds["minimum_total_days"],
        "two_position_days": len(pair_rows) >= thresholds["minimum_two_position_days"],
        "active_reallocation_days": len(active) >= thresholds["minimum_active_reallocation_days"],
        "active_each_third": all(value >= thresholds["minimum_active_days_each_chronological_third"] for value in active_by_third),
        "weights_capital_neutral": all(abs(sum(row["primary_weights"].values()) - (1.0 if row["selected"] else 0.0)) < 1e-12 for row in rows),
        "weight_bounds": all(
            all(0.0 <= value <= (0.75 if len(row["selected"]) == 2 else 1.0) for value in row["primary_weights"].values())
            for row in rows
        ),
    }
    passed = all(checks.values())
    daily_inputs = []
    for symbol in SYMBOLS:
        path = next(daily_dir.glob(f"{symbol}_*.json"))
        daily_inputs.append({"symbol": symbol, "path": str(path), "sha256": sha256(path)})
    payload = {
        "schema_version": "hyb005-cross-asset-feasibility-v1",
        "experiment_id": "HYB-005",
        "status": "PASS_FREEZE_AND_EVALUATE_AUTHORIZED" if passed else "FAIL_STOP_BEFORE_TARGET_EVALUATION",
        "passed": passed,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "outcomes_consulted": False,
        "audit_contract": "Selection, text availability, weights and sample counts only; no i+1 return or PnL is read.",
        "research_role": "exploratory development feasibility; not validation or holdout",
        "baseline_scope": "daily top-2 predecessor, not canonical top-1 Tech-Control",
        "coverage": built["coverage"],
        "sample": {
            "total_days": len(rows),
            "invested_days": sum(bool(row["selected"]) for row in rows),
            "two_position_days": len(pair_rows),
            "active_reallocation_days": len(active),
            "active_days_by_chronological_third": active_by_third,
            "selected_pair_counts": dict(Counter("+".join(row["selected"]) for row in pair_rows)),
        },
        "thresholds": thresholds,
        "checks": checks,
        "inputs": {
            "events": {"path": str(events), "sha256": sha256(events)},
            "extractor_inputs": {"path": str(inputs), "sha256": sha256(inputs)},
            "daily_candles": daily_inputs,
            "baseline_result": {
                "path": str(root / "results/technical_cross_asset_4y_top2.json"),
                "sha256": sha256(root / "results/technical_cross_asset_4y_top2.json"),
            },
        },
        "next_authorized_action": "Freeze assignments and evaluation before reading forward returns." if passed else "Stop HYB-005.",
    }
    write_json(output, payload)
    print(json.dumps({"status": payload["status"], "sample": payload["sample"], "checks": checks, "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
