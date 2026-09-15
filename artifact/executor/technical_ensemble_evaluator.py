"""Static-capital ensemble test for two independently executed Tech sleeves.

The growth sleeve is top-1/rank-20/no-stop. The defensive sleeve is the
locked top-2/rank-20/2.5-ATR core. Capital is split once at inception and is
not transferred between sleeves, avoiding hidden rebalancing or leverage.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from technical_autoquant_evaluator import COST_SCENARIOS, _cscv_pbo, _run_execution

DAY_MS = 86_400_000
STARTING_BALANCE = 10_000.0
GROWTH_WEIGHTS = (0.25, 0.50, 0.75)


def _combine_curves(defensive: dict, growth: dict, growth_weight: float) -> list[tuple[int, float]]:
    curves = [defensive["equity_points"], growth["equity_points"]]
    times = sorted(set(point[0] for curve in curves for point in curve))
    indexes = [0, 0]
    current = [STARTING_BALANCE, STARTING_BALANCE]
    combined: list[tuple[int, float]] = []
    for timestamp in times:
        for sleeve in range(2):
            curve = curves[sleeve]
            while indexes[sleeve] < len(curve) and int(curve[indexes[sleeve]][0]) <= timestamp:
                current[sleeve] = float(curve[indexes[sleeve]][1])
                indexes[sleeve] += 1
        value = (1 - growth_weight) * current[0] + growth_weight * current[1]
        combined.append((timestamp, value))
    return combined


def _result_from_curve(curve: list[tuple[int, float]], fold_days: int = 180) -> dict:
    peak = STARTING_BALANCE
    max_dd = 0.0
    for _, value in curve:
        peak = max(peak, value)
        max_dd = max(max_dd, 1 - value / peak)
    fold_ms = fold_days * DAY_MS
    folds = []
    first_time, last_time = curve[0][0], curve[-1][0]
    for start in range(first_time, last_time, fold_ms):
        values = [value for timestamp, value in curve if start <= timestamp < start + fold_ms]
        if len(values) < 2:
            continue
        fold_peak = values[0]
        fold_dd = 0.0
        for value in values:
            fold_peak = max(fold_peak, value)
            fold_dd = max(fold_dd, 1 - value / fold_peak)
        folds.append({
            "start": datetime.fromtimestamp(start / 1000, tz=timezone.utc).date().isoformat(),
            "return_pct": round((values[-1] / values[0] - 1) * 100, 4),
            "max_drawdown_pct": round(fold_dd * 100, 4),
        })
    final = curve[-1][1]
    return {
        "result": {
            "starting_balance": STARTING_BALANCE,
            "final_equity": round(final, 2),
            "return_pct": round((final / STARTING_BALANCE - 1) * 100, 4),
            "max_drawdown_pct": round(max_dd * 100, 4),
        },
        "walk_forward_folds": folds,
        "positive_folds": sum(fold["return_pct"] > 0 for fold in folds),
        "folds_tested": len(folds),
    }


def _sleeve_summary(payload: dict) -> dict:
    return {
        "result": payload["result"],
        "walk_forward_folds": payload["walk_forward_folds"],
        "positive_folds": payload["positive_folds"],
        "folds_tested": payload["folds_tested"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Static two-sleeve Technical ensemble evaluator")
    parser.add_argument("--days", type=int, default=1460)
    parser.add_argument("--output-dir", type=Path, default=Path("results/technical_ensemble"))
    parser.add_argument("--output", type=Path, default=Path("results/technical_ensemble_evaluation.json"))
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent.parent
    output_dir = project_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    defensive_config = {"top_n": 2, "rank_days": 20, "stop_atr": 2.5}
    growth_config = {"top_n": 1, "rank_days": 20, "stop_atr": 0.0}
    scenarios: dict[str, dict] = {}

    for cost in COST_SCENARIOS:
        print(f"[ensemble] {cost['name']} defensive sleeve", flush=True)
        defensive = _run_execution(
            project_root, output_dir / f"defensive_{cost['name']}.json",
            defensive_config, cost, args.days, include_equity_curve=True,
        )
        print(f"[ensemble] {cost['name']} growth sleeve", flush=True)
        growth = _run_execution(
            project_root, output_dir / f"growth_{cost['name']}.json",
            growth_config, cost, args.days, include_equity_curve=True,
        )
        candidates = {
            "defensive": _sleeve_summary(defensive),
            "growth": _sleeve_summary(growth),
        }
        for growth_weight in GROWTH_WEIGHTS:
            name = f"blend_growth_{int(growth_weight * 100)}"
            candidates[name] = _result_from_curve(_combine_curves(defensive, growth, growth_weight))
        scenarios[cost["name"]] = {
            "cost": cost,
            "candidates": candidates,
            "cscv_pbo": _cscv_pbo(candidates),
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "research diagnostic; not live approval",
        "construction": "static initial capital split; independent sleeve accounting; no inter-sleeve rebalancing or leverage",
        "defensive_sleeve": defensive_config,
        "growth_sleeve": growth_config,
        "predeclared_growth_weights": GROWTH_WEIGHTS,
        "scenarios": scenarios,
    }
    output = project_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    concise = {
        scenario: {
            "results": {name: result["result"] for name, result in detail["candidates"].items()},
            "pbo": detail["cscv_pbo"]["pbo"],
        }
        for scenario, detail in scenarios.items()
    }
    print(json.dumps(concise, indent=2), flush=True)


if __name__ == "__main__":
    main()
