"""Execution-constrained robustness evaluator for the Technical core.

This module borrows governance ideas from AutoQuant without treating that
preprint as alpha evidence. It runs a pre-declared configuration grid under
identical T+1/funding semantics, applies explicit cost scenarios, and computes
a CSCV/PBO diagnostic from non-overlapping execution folds.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


CONFIG_GRID = [
    {"top_n": top_n, "rank_days": rank_days, "stop_atr": stop_atr}
    for top_n in (1, 2, 3)
    for rank_days in (10, 20)
    for stop_atr in (0.0, 2.5)
]

COST_SCENARIOS = (
    {"name": "base_decomposed", "fee_bps": 6.0, "slippage_bps": 3.0, "spread_bps": 2.0, "impact_bps": 1.0},
    {"name": "stress", "fee_bps": 10.0, "slippage_bps": 8.0, "spread_bps": 4.0, "impact_bps": 5.0},
    {"name": "harsh", "fee_bps": 15.0, "slippage_bps": 15.0, "spread_bps": 8.0, "impact_bps": 10.0},
)


def _config_name(config: dict) -> str:
    stop = str(config["stop_atr"]).replace(".", "p")
    return f"top{config['top_n']}_rank{config['rank_days']}_stop{stop}"


def _run_execution(project_root: Path, output: Path, config: dict, cost: dict, days: int, include_equity_curve: bool = False) -> dict:
    if output.exists():
        try:
            cached = json.loads(output.read_text(encoding="utf-8"))
            protocol = cached.get("protocol", {})
            if (
                cached.get("missing_funding_events") == 0
                and protocol.get("fee_bps") == cost["fee_bps"]
                and protocol.get("slippage_bps") == cost["slippage_bps"]
                and protocol.get("spread_bps") == cost["spread_bps"]
                and protocol.get("impact_bps") == cost["impact_bps"]
                and f"top-N {config['rank_days']}d" in protocol.get("daily_selection", "")
                and (not include_equity_curve or bool(cached.get("equity_points")))
            ):
                print(f"  reuse audited artifact: {output.name}", flush=True)
                return cached
        except (OSError, ValueError, TypeError):
            pass
    command = [
        sys.executable,
        str(project_root / "executor" / "technical_cross_asset_execution.py"),
        "--days", str(days),
        "--top-n", str(config["top_n"]),
        "--rank-days", str(config["rank_days"]),
        "--stop-atr", str(config["stop_atr"]),
        "--trail-atr", "0",
        "--pyramid-mode", "off",
        "--funding-source", "bybit-history",
        "--fee-bps", str(cost["fee_bps"]),
        "--slippage-bps", str(cost["slippage_bps"]),
        "--spread-bps", str(cost["spread_bps"]),
        "--impact-bps", str(cost["impact_bps"]),
        "--fold-days", "180",
        "--output", str(output),
    ]
    if include_equity_curve:
        command.append("--include-equity-curve")
    completed = None
    for attempt in range(1, 4):
        completed = subprocess.run(command, cwd=project_root, text=True, capture_output=True, check=False)
        if completed.returncode == 0:
            return json.loads(output.read_text(encoding="utf-8"))
        if attempt < 3:
            print(f"  transient failure; retry {attempt + 1}/3", flush=True)
            time.sleep(3)
    raise RuntimeError(
        f"execution failed for {_config_name(config)} / {cost['name']}:\n{completed.stderr[-4000:]}"
    )


def _partition_score(returns_pct: list[float], indexes: tuple[int, ...]) -> float:
    # Log compounding is stable and preserves the ordering of compounded
    # returns while preventing a large positive fold from dominating by sum.
    return sum(math.log1p(returns_pct[index] / 100) for index in indexes)


def _cscv_pbo(config_results: dict[str, dict]) -> dict:
    names = tuple(config_results)
    fold_count = min(len(result["walk_forward_folds"]) for result in config_results.values())
    if fold_count < 4:
        raise RuntimeError("CSCV/PBO requires at least four common folds")
    if fold_count % 2:
        fold_count -= 1
    returns = {
        name: [float(fold["return_pct"]) for fold in result["walk_forward_folds"][:fold_count]]
        for name, result in config_results.items()
    }
    all_indexes = tuple(range(fold_count))
    logits: list[float] = []
    selected: Counter[str] = Counter()
    winner_logits: dict[str, list[float]] = defaultdict(list)
    winner_regret: dict[str, list[float]] = defaultdict(list)
    degradation: list[float] = []

    for train_indexes in itertools.combinations(all_indexes, fold_count // 2):
        test_indexes = tuple(index for index in all_indexes if index not in train_indexes)
        train_scores = {name: _partition_score(values, train_indexes) for name, values in returns.items()}
        winner = max(names, key=lambda name: (train_scores[name], name))
        selected[winner] += 1
        test_scores = {name: _partition_score(values, test_indexes) for name, values in returns.items()}
        ordered = sorted(names, key=lambda name: (test_scores[name], name))
        rank = ordered.index(winner) + 1  # 1=worst, N=best
        relative_rank = rank / (len(names) + 1)
        logit = math.log(relative_rank / (1 - relative_rank))
        regret = test_scores[winner] - max(test_scores.values())
        logits.append(logit)
        degradation.append(regret)
        winner_logits[winner].append(logit)
        winner_regret[winner].append(regret)

    pbo = sum(value <= 0 for value in logits) / len(logits)
    return {
        "method": "CSCV on common non-overlapping 180-day fold-return matrix; performance statistic is compounded log return",
        "configurations": len(names),
        "folds": fold_count,
        "partitions": len(logits),
        "pbo": round(pbo, 6),
        "median_oos_rank_logit": round(statistics.median(logits), 6),
        "mean_selected_oos_regret_log_return": round(statistics.mean(degradation), 6),
        "is_winner_frequency": dict(selected.most_common()),
        "winner_specific_diagnostics": {
            name: {
                "selections": len(values),
                "pbo_when_selected": round(sum(value <= 0 for value in values) / len(values), 6),
                "median_oos_rank_logit": round(statistics.median(values), 6),
                "mean_oos_regret_log_return": round(statistics.mean(winner_regret[name]), 6),
            }
            for name, values in winner_logits.items()
        },
        "interpretation": (
            "high overfit risk" if pbo > 0.20 else
            "moderate overfit risk" if pbo > 0.10 else
            "low measured overfit risk; not proof of live alpha"
        ),
        "limitation": "Eight coarse folds provide a diagnostic, not a definitive bar-level PBO estimate.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoQuant-style robustness evaluation for the Technical core")
    parser.add_argument("--days", type=int, default=1460)
    parser.add_argument("--output-dir", type=Path, default=Path("results/technical_autoquant"))
    parser.add_argument("--output", type=Path, default=Path("results/technical_autoquant_evaluation.json"))
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent.parent
    output_dir = project_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    base_cost = COST_SCENARIOS[0]
    config_results: dict[str, dict] = {}

    for number, config in enumerate(CONFIG_GRID, start=1):
        name = _config_name(config)
        print(f"[{number}/{len(CONFIG_GRID)}] base configuration {name}", flush=True)
        config_results[name] = _run_execution(
            project_root, output_dir / f"{name}_{base_cost['name']}.json",
            config, base_cost, args.days,
        )

    locked = {"top_n": 2, "rank_days": 20, "stop_atr": 2.5}
    locked_name = _config_name(locked)
    cost_results = {base_cost["name"]: config_results[locked_name]}
    for cost in COST_SCENARIOS[1:]:
        print(f"[cost] locked core / {cost['name']}", flush=True)
        cost_results[cost["name"]] = _run_execution(
            project_root, output_dir / f"{locked_name}_{cost['name']}.json",
            locked, cost, args.days,
        )

    cscv = _cscv_pbo(config_results)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "research diagnostic; not live approval",
        "predeclared_grid": CONFIG_GRID,
        "cost_scenarios": COST_SCENARIOS,
        "locked_core": locked,
        "locked_cost_stress": {
            name: {
                "result": result["result"],
                "positive_folds": result["positive_folds"],
                "folds_tested": result["folds_tested"],
                "applied_funding_events": result["applied_funding_events"],
                "missing_funding_events": result["missing_funding_events"],
            }
            for name, result in cost_results.items()
        },
        "configuration_summary": {
            name: {
                "result": result["result"],
                "positive_folds": result["positive_folds"],
                "folds_tested": result["folds_tested"],
            }
            for name, result in config_results.items()
        },
        "cscv_pbo": cscv,
    }
    output = project_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"locked_cost_stress": payload["locked_cost_stress"], "cscv_pbo": cscv}, indent=2), flush=True)


if __name__ == "__main__":
    main()
