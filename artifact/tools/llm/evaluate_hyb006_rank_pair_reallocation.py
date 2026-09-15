"""Run the frozen HYB-006 evaluation after an outcome-free sample PASS."""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hyb005_cross_asset_common import SYMBOLS, percentile, read_json, sha256, write_json
from hyb006_rank_pair_common import construct_assignments


ARMS = {
    "tech": "base_weights",
    "primary": "primary_weights",
    "opposite": "opposite_weights",
    "delayed": "delayed_weights",
    "shuffled": "shuffled_weights",
}


def turnovers(rows: list[dict[str, Any]], weight_key: str) -> list[float]:
    output: list[float] = []
    previous: dict[str, float] | None = None
    for row in rows:
        weights = row[weight_key]
        value = sum(abs(weights[symbol]) for symbol in SYMBOLS) if previous is None else 0.5 * sum(abs(weights[symbol] - previous[symbol]) for symbol in SYMBOLS)
        output.append(value)
        previous = weights
    return output


def arm_series(rows: list[dict[str, Any]], closes: dict[str, list[float]], weight_key: str, cost_rate: float) -> dict[str, list[float]]:
    turnover = turnovers(rows, weight_key)
    gross = []
    for row in rows:
        i = int(row["index"])
        gross.append(sum(row[weight_key][symbol] * (closes[symbol][i + 1] / closes[symbol][i] - 1.0) for symbol in SYMBOLS))
    costs = [value * cost_rate for value in turnover]
    return {"gross": gross, "turnover": turnover, "cost": costs, "net": [g - c for g, c in zip(gross, costs, strict=True)]}


def summarize(series: dict[str, list[float]]) -> dict[str, float]:
    equity = 1.0
    peak = 1.0
    mdd = 0.0
    for value in series["net"]:
        equity *= 1.0 + value
        peak = max(peak, equity)
        mdd = max(mdd, 1.0 - equity / peak)
    n = len(series["net"])
    return {
        "total_return": equity - 1.0,
        "annualized_return": equity ** (365.0 / n) - 1.0 if equity > 0 else -1.0,
        "mean_daily_net_return": sum(series["net"]) / n,
        "max_drawdown": mdd,
        "total_turnover": sum(series["turnover"]),
        "total_cost": sum(series["cost"]),
    }


def block_bootstrap_mean_ci(values: list[float], replicates: int, block: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(replicates):
        sampled: list[float] = []
        while len(sampled) < n:
            start = rng.randrange(0, n - block + 1)
            sampled.extend(values[start:start + block])
        means.append(sum(sampled[:n]) / n)
    return [percentile(means, 0.025), percentile(means, 0.975)]


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    daily_dir = root / "results/bybit_lifecycle_daily"
    events = root / "paper/input/results/llm/v3/llm_event_extractor_v3_9_full_development.json"
    inputs = root / "paper/input/results/llm/v3/llm_event_extraction_inputs_v3_development.json"
    pre_path = root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_predeclared.json"
    audit_path = root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_feasibility.json"
    pre = read_json(pre_path)
    audit = read_json(audit_path)
    if audit.get("status") != "PASS_FREEZE_AND_EVALUATE_AUTHORIZED" or audit.get("passed") is not True or audit.get("outcomes_consulted") is not False:
        raise RuntimeError("HYB-006 evaluation is not authorized by the sample audit")
    if audit["predeclaration"]["sha256"] != sha256(pre_path):
        raise RuntimeError("predeclaration changed after audit")
    for item in pre["inputs"]["scripts"]:
        if sha256(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"frozen script changed: {item['path']}")
    built = construct_assignments(daily_dir, events, inputs)
    rows = built["rows"]
    if len(rows) != audit["sample"]["pair_days"] or sum(row["active"] for row in rows) != audit["sample"]["active_days"]:
        raise RuntimeError("assignment sample no longer matches audited sample")

    cost_rate = float(pre["evaluation"]["cost_bps_per_unit_turnover"]) / 10_000.0
    series = {arm: arm_series(rows, built["closes"], key, cost_rate) for arm, key in ARMS.items()}
    summaries = {arm: summarize(values) for arm, values in series.items()}
    delta = [p - t for p, t in zip(series["primary"]["net"], series["tech"]["net"], strict=True)]
    bootstrap = pre["evaluation"]["bootstrap"]
    ci = block_bootstrap_mean_ci(delta, int(bootstrap["replicates"]), int(bootstrap["moving_block_days"]), int(bootstrap["seed"]))
    n = len(delta)
    fold_means = []
    for fold in range(int(pre["evaluation"]["folds"])):
        start = fold * n // 5
        end = (fold + 1) * n // 5
        fold_means.append(sum(delta[start:end]) / (end - start))
    checks = {
        "bootstrap_ci_lower_positive": ci[0] > 0.0,
        "positive_folds_at_least_3_of_5": sum(value > 0.0 for value in fold_means) >= 3,
        "primary_exceeds_all_placebos": all(summaries["primary"]["mean_daily_net_return"] > summaries[name]["mean_daily_net_return"] for name in ("opposite", "delayed", "shuffled")),
        "mdd_not_worse_by_more_than_5pp": summaries["primary"]["max_drawdown"] - summaries["tech"]["max_drawdown"] <= 0.05,
    }
    passed = all(checks.values())
    panel_rows = []
    for position, row in enumerate(rows):
        i = int(row["index"])
        panel_rows.append({
            "information_date": row["information_date"],
            "selected": row["selected"],
            "signed_scores": row["signed_scores"],
            "weights": {arm: row[key] for arm, key in ARMS.items()},
            "next_returns": {symbol: built["closes"][symbol][i + 1] / built["closes"][symbol][i] - 1.0 for symbol in SYMBOLS},
            "arm_net_returns": {arm: series[arm]["net"][position] for arm in ARMS},
            "primary_minus_tech": delta[position],
        })
    panel_path = root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_daily_panel.json"
    write_json(panel_path, {"schema_version": "hyb006-rank-pair-panel-v1", "experiment_id": "HYB-006", "rows": panel_rows})
    result = {
        "schema_version": "hyb006-rank-pair-evaluation-v1",
        "experiment_id": "HYB-006",
        "status": "EXPLORATORY_TRANSFER_PASS" if passed else "EXPLORATORY_TRANSFER_FAIL",
        "passed": passed,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "research_role": pre["research_role"],
        "predeclaration": {"path": str(pre_path), "sha256": sha256(pre_path)},
        "sample_audit": {"path": str(audit_path), "sha256": sha256(audit_path)},
        "daily_panel": {"path": str(panel_path), "sha256": sha256(panel_path), "rows": len(panel_rows)},
        "cost_bps_per_unit_turnover": pre["evaluation"]["cost_bps_per_unit_turnover"],
        "arms": summaries,
        "primary_contrast": {
            "mean_daily_net_delta": sum(delta) / len(delta),
            "block_bootstrap_95_ci": ci,
            "fold_mean_deltas": fold_means,
            "positive_folds": sum(value > 0.0 for value in fold_means),
        },
        "checks": checks,
        "interpretation": "Evidence of incremental value within this exploratory transfer design only." if passed else "No incremental-value evidence under the frozen HYB-006 pass rule; do not retune on these outcomes.",
    }
    output = root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_evaluation.json"
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
