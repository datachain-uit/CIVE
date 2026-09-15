"""Statistics for reproducible, paired portfolio backtests.

This intentionally does not implement a Diebold--Mariano test on trading PnL:
DM is a forecast-loss test, not a generic trading-performance test.  It builds
daily marked-to-market portfolio returns and reports a paired moving-block
bootstrap confidence interval for the incremental mean return and Sharpe.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _daily_equity(record: dict) -> pd.Series:
    timestamps = record.get('equity_timestamps', [])
    equity = record.get('equity_curve', [])
    if len(timestamps) != len(equity) or len(equity) < 2:
        raise ValueError('result has no aligned marked-to-market equity curve')
    index = pd.to_datetime(timestamps, unit='ms', utc=True).floor('D')
    series = pd.Series(equity, index=index).groupby(level=0).last()
    return series.pct_change().dropna()


def portfolio_returns(result: dict, symbols: list[str]) -> pd.Series:
    columns = [_daily_equity(result['per_symbol'][symbol]).rename(symbol) for symbol in symbols]
    frame = pd.concat(columns, axis=1, join='inner').dropna()
    if frame.empty:
        raise ValueError('no common marked-to-market dates across the fixed universe')
    return frame.mean(axis=1)


def annualised_sharpe(returns: np.ndarray) -> float:
    sigma = returns.std(ddof=1)
    return float(returns.mean() / sigma * np.sqrt(365)) if sigma > 0 else float('nan')


def moving_block_bootstrap(diff: np.ndarray, block: int, draws: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = len(diff)
    samples = np.empty(draws)
    for draw in range(draws):
        chunks = []
        while sum(len(chunk) for chunk in chunks) < n:
            start = rng.integers(0, n)
            chunk = np.take(diff, np.arange(start, start + block) % n)
            chunks.append(chunk)
        samples[draw] = np.concatenate(chunks)[:n].mean()
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description='Paired statistics from marked-to-market backtest results')
    parser.add_argument('--baseline', required=True, help='Technical result JSON from multi_backtest')
    parser.add_argument('--model', required=True, help='Treatment result JSON from multi_backtest')
    parser.add_argument('--block-days', type=int, default=7)
    parser.add_argument('--draws', type=int, default=10_000)
    parser.add_argument('--seed', type=int, default=20260805)
    parser.add_argument('--output', default='results/research_statistics.json')
    args = parser.parse_args()

    baseline = json.loads(Path(args.baseline).read_text(encoding='utf-8'))
    model = json.loads(Path(args.model).read_text(encoding='utf-8'))
    baseline_symbols = {s for s, v in baseline.get('per_symbol', {}).items() if isinstance(v, dict)}
    model_symbols = {s for s, v in model.get('per_symbol', {}).items() if isinstance(v, dict)}
    if baseline_symbols != model_symbols:
        raise ValueError('fixed-universe violation: successful symbols differ between baseline and treatment')
    symbols = sorted(baseline_symbols)
    if not symbols:
        raise ValueError('no successful symbols')

    left = portfolio_returns(baseline, symbols)
    right = portfolio_returns(model, symbols)
    joined = pd.concat([left.rename('baseline'), right.rename('treatment')], axis=1, join='inner').dropna()
    if len(joined) < max(30, args.block_days * 3):
        raise ValueError('insufficient common daily observations for block bootstrap')
    diff = (joined['treatment'] - joined['baseline']).to_numpy()
    boot = moving_block_bootstrap(diff, args.block_days, args.draws, args.seed)
    result = {
        'method': 'paired moving-block bootstrap on daily marked-to-market equal-weight portfolio returns',
        'symbols': symbols,
        'n_days': int(len(joined)),
        'baseline_sharpe': annualised_sharpe(joined['baseline'].to_numpy()),
        'treatment_sharpe': annualised_sharpe(joined['treatment'].to_numpy()),
        'mean_active_return_daily': float(diff.mean()),
        'mean_active_return_ci_95': [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))],
        'bootstrap_probability_active_return_positive': float((boot > 0).mean()),
        'block_days': args.block_days,
        'draws': args.draws,
        'seed': args.seed,
        'warning': 'This is performance inference, not a Diebold--Mariano predictive-accuracy test. Apply SPA/Reality Check separately if model/rule selection searched multiple candidates.',
    }
    Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
