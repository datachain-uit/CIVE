"""Evaluate HYB-010 CryptoBERT risk-budget reallocation.

The policy and all assignments are loaded from a frozen predeclaration.  This
runner performs no tuning and does not read any feature artifact directly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SEED = 20260914
DRAWS = 20_000


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trade_key(row: dict[str, Any]) -> str:
    return f"{int(row['entry_time'])}::{row['symbol']}"


def quarter(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc)
    return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def cluster_bootstrap_ci(rows: list[dict[str, Any]], field: str) -> list[float]:
    clusters: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        clusters[quarter(int(row["entry_time"]))].append(float(row[field]))
    labels = sorted(clusters)
    rng = random.Random(SEED)
    estimates: list[float] = []
    for _ in range(DRAWS):
        sample: list[float] = []
        for _ in labels:
            sample.extend(clusters[rng.choice(labels)])
        estimates.append(statistics.fmean(sample))
    return [percentile(estimates, 0.025), percentile(estimates, 0.975)]


def tail_metrics(returns: list[float]) -> dict[str, float | int]:
    tail_n = max(1, math.ceil(0.10 * len(returns)))
    ordered = sorted(returns)
    return {
        "tail_trade_count": tail_n,
        "es10_trade_return": statistics.fmean(ordered[:tail_n]),
        "worst_trade_return": ordered[0],
    }


def summarize(
    name: str,
    weights: dict[str, float],
    base: list[dict[str, Any]],
    folds: list[list[str]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    equity = peak = 1.0
    max_drawdown = 0.0
    for trade in base:
        weight = float(weights[trade_key(trade)])
        hybrid_net = weight * float(trade["tech_net_return"])
        hybrid_gross = weight * float(trade["tech_gross_return"])
        row = {
            **trade,
            "weight": weight,
            "hybrid_net_return": hybrid_net,
            "hybrid_gross_return": hybrid_gross,
            "paired_net_difference": hybrid_net - float(trade["tech_net_return"]),
            "paired_gross_difference": hybrid_gross - float(trade["tech_gross_return"]),
        }
        rows.append(row)
        equity *= 1.0 + hybrid_net
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, 1.0 - equity / peak)

    fold_rows: list[dict[str, Any]] = []
    for start, end in folds:
        start_ms = int(datetime.fromisoformat(start).timestamp() * 1000)
        end_ms = int(datetime.fromisoformat(end).timestamp() * 1000)
        values = [
            float(row["paired_net_difference"])
            for row in rows
            if start_ms <= int(row["entry_time"]) < end_ms
        ]
        fold_rows.append(
            {
                "start": start,
                "end": end,
                "n": len(values),
                "mean_paired_net_difference": statistics.fmean(values) if values else None,
            }
        )

    hybrid_returns = [float(row["hybrid_net_return"]) for row in rows]
    net_differences = [float(row["paired_net_difference"]) for row in rows]
    gross_differences = [float(row["paired_gross_difference"]) for row in rows]
    return {
        "name": name,
        "n": len(rows),
        "mean_weight": statistics.fmean(float(row["weight"]) for row in rows),
        "min_weight": min(float(row["weight"]) for row in rows),
        "max_weight": max(float(row["weight"]) for row in rows),
        "mean_paired_net_difference": statistics.fmean(net_differences),
        "paired_net_difference_ci95": cluster_bootstrap_ci(rows, "paired_net_difference"),
        "mean_paired_gross_difference": statistics.fmean(gross_differences),
        "compounded_net_return": equity - 1.0,
        "closed_trade_max_drawdown": max_drawdown,
        **tail_metrics(hybrid_returns),
        "folds": fold_rows,
        "positive_folds": sum(
            row["mean_paired_net_difference"] is not None
            and float(row["mean_paired_net_difference"]) > 0
            for row in fold_rows
        ),
        "paired_rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = read_json(args.config)
    for source in config["sources"].values():
        path = Path(source["path"])
        if sha256(path) != source["sha256"]:
            raise ValueError(f"frozen input hash mismatch: {path}")

    tech = read_json(Path(config["sources"]["tech"]["path"]))
    required = set(config["assignments"]["tech_control"])
    cumulative_pnl = 0.0
    base: list[dict[str, Any]] = []
    for trade in sorted(tech["closed_trades"], key=lambda row: (int(row["entry_time"]), row["symbol"])):
        entry_equity = float(tech["result"]["starting_balance"]) + cumulative_pnl
        if trade_key(trade) in required:
            cost = float(trade["execution_cost"]) + float(trade["fees"]) + float(trade["funding_paid"])
            base.append(
                {
                    "symbol": str(trade["symbol"]),
                    "entry_time": int(trade["entry_time"]),
                    "exit_time": int(trade["exit_time"]),
                    "exit_reason": str(trade["reason"]),
                    "tech_entry_equity": entry_equity,
                    "tech_gross_return": float(trade["gross_price_pnl"]) / entry_equity,
                    "tech_cost_return": cost / entry_equity,
                    "tech_net_return": float(trade["net_pnl"]) / entry_equity,
                }
            )
        cumulative_pnl += float(trade["net_pnl"])

    if {trade_key(row) for row in base} != required:
        raise ValueError("Tech replay does not cover every frozen opportunity")

    results = {
        name: summarize(name, weights, base, config["folds"])
        for name, weights in config["assignments"].items()
    }
    tech_result = results["tech_control"]
    primary = results["cryptobert_reallocation"]
    shuffled = results["shuffled_reallocation"]
    constant = results["constant_matched_budget"]

    allocation_selectivity = {
        "mean_net_above_shuffled": primary["mean_paired_net_difference"]
        > shuffled["mean_paired_net_difference"],
        "mean_net_above_constant_matched_budget": primary["mean_paired_net_difference"]
        > constant["mean_paired_net_difference"],
        "mdd_below_shuffled": primary["closed_trade_max_drawdown"]
        < shuffled["closed_trade_max_drawdown"],
        "mdd_below_constant_matched_budget": primary["closed_trade_max_drawdown"]
        < constant["closed_trade_max_drawdown"],
    }
    return_conversion = {
        "compounded_return_above_tech": primary["compounded_net_return"]
        > tech_result["compounded_net_return"],
        "mean_paired_net_ci_lower_above_zero": primary["paired_net_difference_ci95"][0] > 0,
        "positive_folds_at_least_2_of_3": primary["positive_folds"] >= 2,
    }
    risk_preservation = {
        "mdd_not_worse_than_tech": primary["closed_trade_max_drawdown"]
        <= tech_result["closed_trade_max_drawdown"],
        "es10_not_worse_than_tech": primary["es10_trade_return"] >= tech_result["es10_trade_return"],
        "worst_trade_not_worse_than_tech": primary["worst_trade_return"]
        >= tech_result["worst_trade_return"],
    }

    output = {
        "schema_version": 1,
        "experiment_id": config["experiment_id"],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETE",
        "research_role": config["research_role"],
        "results": results,
        "gates": {
            "allocation_selectivity": allocation_selectivity,
            "return_conversion": return_conversion,
            "risk_preservation": risk_preservation,
            "strong_risk_budget_conversion_pass": all(all(group.values()) for group in (
                allocation_selectivity, return_conversion, risk_preservation
            )),
        },
        "interpretation": {
            "incremental_value_rule": "Report every Tech+LLM minus Tech change in return, risk, cost, stability and uncertainty; overall-return dominance is not required for an incremental-value finding on another dimension.",
            "strong_conversion_rule": "A stronger claim that saved risk was converted into higher return requires every frozen allocation-selectivity, return-conversion and risk-preservation condition to pass.",
            "limits": "Post-outcome exploratory development on 24 historical Tech opportunities; closed-trade MDD is not intrabar MDD; not validation, sealed holdout or live evidence.",
        },
        "predeclaration": {"path": str(args.config), "sha256": sha256(args.config)},
    }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "gates": output["gates"], "primary": {k: v for k, v in primary.items() if k != "paired_rows"}}, indent=2))


if __name__ == "__main__":
    main()
