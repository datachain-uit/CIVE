"""Exploratory selection-risk inference for the inspected lifecycle grid."""
from __future__ import annotations

import argparse
import itertools
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist

import numpy as np


def annualized_sharpe(values: np.ndarray) -> float:
    sigma = values.std(ddof=1)
    return float(values.mean() / sigma * math.sqrt(365)) if sigma > 0 else float("nan")


def max_drawdown_from_returns(values: np.ndarray) -> float:
    equity = np.cumprod(1 + values)
    peaks = np.maximum.accumulate(np.r_[1.0, equity])[:-1]
    return float(np.max(1 - equity / peaks))


def moving_block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    indices = []
    while len(indices) < n:
        start = int(rng.integers(0, n))
        indices.extend((start + offset) % n for offset in range(block))
    return np.asarray(indices[:n])


def bootstrap(values: np.ndarray, block: int, draws: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    sharpes = np.empty(draws)
    total_returns = np.empty(draws)
    drawdowns = np.empty(draws)
    for draw in range(draws):
        sample = values[moving_block_indices(len(values), block, rng)]
        means[draw] = sample.mean()
        sharpes[draw] = annualized_sharpe(sample)
        total_returns[draw] = np.prod(1 + sample) - 1
        drawdowns[draw] = max_drawdown_from_returns(sample)
    quantiles = lambda x: [float(np.quantile(x, 0.025)), float(np.quantile(x, 0.975))]
    return {
        "mean_daily_return_ci_95": quantiles(means),
        "annualized_sharpe_ci_95": quantiles(sharpes),
        "total_return_ci_95": quantiles(total_returns),
        "max_drawdown_ci_95": quantiles(drawdowns),
        "probability_mean_return_positive": float(np.mean(means > 0)),
        "block_days": block, "draws": draws, "seed": seed,
    }


def cscv_pbo(matrix: np.ndarray, partitions: int = 8) -> dict:
    if partitions % 2 or len(matrix) < partitions:
        raise ValueError("CSCV requires an even feasible partition count")
    blocks = np.array_split(np.arange(len(matrix)), partitions)
    logits = []
    selected = []
    for train_blocks in itertools.combinations(range(partitions), partitions // 2):
        train_set = set(train_blocks)
        train_idx = np.concatenate([blocks[i] for i in train_blocks])
        test_idx = np.concatenate([blocks[i] for i in range(partitions) if i not in train_set])
        train_scores = np.asarray([annualized_sharpe(matrix[train_idx, col]) for col in range(matrix.shape[1])])
        winner = int(np.nanargmax(train_scores))
        test_scores = np.asarray([annualized_sharpe(matrix[test_idx, col]) for col in range(matrix.shape[1])])
        rank = int(np.argsort(np.argsort(test_scores))[winner]) + 1
        relative_rank = (rank - 0.5) / matrix.shape[1]
        logits.append(math.log(relative_rank / (1 - relative_rank)))
        selected.append(winner)
    return {
        "method": "CSCV using annualized Sharpe selection and eight contiguous partitions",
        "combinations": len(logits),
        "pbo": float(np.mean(np.asarray(logits) <= 0)),
        "median_oos_rank_logit": float(np.median(logits)),
        "distinct_selected_strategies": len(set(selected)),
    }


def deflated_sharpe(values: np.ndarray, trial_sharpes: np.ndarray) -> dict:
    n = len(values)
    observed = annualized_sharpe(values)
    sigma_trials = float(np.nanstd(trial_sharpes, ddof=1))
    trials = len(trial_sharpes)
    normal = NormalDist()
    gamma = 0.5772156649015329
    expected_max = sigma_trials * (
        (1 - gamma) * normal.inv_cdf(1 - 1 / trials)
        + gamma * normal.inv_cdf(1 - 1 / (trials * math.e))
    )
    daily_sr = values.mean() / values.std(ddof=1)
    benchmark_daily_sr = expected_max / math.sqrt(365)
    skew = float(np.mean(((values - values.mean()) / values.std(ddof=0)) ** 3))
    kurtosis = float(np.mean(((values - values.mean()) / values.std(ddof=0)) ** 4))
    denominator = math.sqrt(max(1e-12, 1 - skew * daily_sr + ((kurtosis - 1) / 4) * daily_sr ** 2))
    statistic = (daily_sr - benchmark_daily_sr) * math.sqrt(n - 1) / denominator
    return {
        "observed_annualized_sharpe": observed,
        "expected_max_annualized_sharpe_under_trials": expected_max,
        "deflated_sharpe_probability": normal.cdf(statistic),
        "test_statistic": statistic, "trials": trials,
        "sample_skewness": skew, "sample_kurtosis": kurtosis,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid-dir", type=Path, default=Path("results/lifecycle_grid_v2"))
    parser.add_argument("--candidate", default="top1_rank20_stop3p0_trail4p0")
    parser.add_argument("--block-days", type=int, default=14)
    parser.add_argument("--draws", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--output", type=Path, default=Path("results/technical_selection_inference_v2.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    files = sorted(path for path in (root / args.grid_dir).glob("*.json") if not path.name.endswith(".manifest.json"))
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    names = [path.stem for path in files]
    if len(payloads) != 54:
        raise ValueError(f"expected 54 configurations, found {len(payloads)}")
    common = sorted(set.intersection(*[{int(row[0]) for row in p["daily_returns"]} for p in payloads]))
    matrix = np.asarray([
        [{int(row[0]): float(row[1]) for row in payload["daily_returns"]}[timestamp] for payload in payloads]
        for timestamp in common
    ])
    candidate_index = names.index(args.candidate)
    trial_sharpes = np.asarray([annualized_sharpe(matrix[:, col]) for col in range(matrix.shape[1])])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "exploratory development-sample inference; not sealed-holdout evidence",
        "matrix": {
            "observations": matrix.shape[0], "configurations": matrix.shape[1],
            "frequency": "daily close-to-close marked-to-market return",
            "start_timestamp": common[0], "end_timestamp": common[-1],
        },
        "candidate": args.candidate,
        "candidate_full_sample": {
            "annualized_sharpe": annualized_sharpe(matrix[:, candidate_index]),
            "total_return_pct": float((np.prod(1 + matrix[:, candidate_index]) - 1) * 100),
            "max_drawdown_pct": max_drawdown_from_returns(matrix[:, candidate_index]) * 100,
        },
        "cscv_pbo": cscv_pbo(matrix),
        "deflated_sharpe": deflated_sharpe(matrix[:, candidate_index], trial_sharpes),
        "moving_block_bootstrap": bootstrap(
            matrix[:, candidate_index], args.block_days, args.draws, args.seed
        ),
        "warnings": [
            "The same inspected development period supplies selection trials and inference.",
            "The 54 strategies are highly correlated; the DSR trial adjustment is descriptive, not an independence claim.",
            "CSCV measures selection instability inside this historical sample and does not replace a future sealed holdout.",
        ],
    }
    output = root / args.output
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
