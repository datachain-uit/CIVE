"""Causal transfer test of Chi et al. (2023) cryptocurrency futures basis.

This is not a reproduction of their 2017-2021 quarterly-futures universe.
It tests the same cross-sectional high-minus-low idea on a fixed five-name
perpetual universe using independently observed Bybit and OKX basis histories.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

from backtester import build_exchange, normalize_derivative_symbol
from technical_cross_asset_execution import _bybit_funding_history
from technical_cross_asset_research import _closed_rows, _metrics

DAY_MS = 86_400_000


def _cached_series(cache_dir: Path, venue: str, symbol: str) -> dict[int, float]:
    safe = symbol.replace("/", "_")
    matches = sorted(cache_dir.glob(f"{venue}_v1_{safe}_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not matches:
        raise RuntimeError(f"missing {venue} basis cache for {symbol}; run technical_cross_asset_execution.py first")
    raw = json.loads(matches[0].read_text(encoding="utf-8"))
    return {int(timestamp): float(value) for timestamp, value in raw.items()}


def _funding_series(cache_dir: Path, symbol: str, start_ms: int, end_ms: int) -> dict[int, float]:
    safe = symbol.replace("/", "_")
    matches = sorted(cache_dir.glob(f"bybit_v2_{safe}_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in matches:
        raw = json.loads(path.read_text(encoding="utf-8"))
        series = {int(timestamp): float(value) for timestamp, value in raw.items()}
        if series and min(series) <= start_ms and max(series) >= end_ms - DAY_MS:
            return series
    return _bybit_funding_history(symbol, start_ms, end_ms)


def _simulate(
    data: dict[str, list[list[float]]],
    bybit_basis: dict[str, dict[int, float]],
    okx_basis: dict[str, dict[int, float]],
    funding: dict[str, dict[int, float]],
    venue: str,
    portfolio: str,
    cost_rate: float,
) -> list[float]:
    symbols = tuple(data)
    opens = {symbol: [float(row[1]) for row in rows] for symbol, rows in data.items()}
    timestamps = [int(row[0]) for row in next(iter(data.values()))]
    funding_times = {symbol: sorted(series) for symbol, series in funding.items()}
    weights = {symbol: 0.0 for symbol in symbols}
    periods: list[float] = []
    high_count = max(1, math.ceil(len(symbols) / 3))

    for i in range(len(timestamps) - 2):
        decision_time = timestamps[i] + DAY_MS
        eligible = [symbol for symbol in symbols if decision_time in bybit_basis[symbol]]
        if venue == "consensus":
            eligible = [symbol for symbol in eligible if decision_time in okx_basis[symbol]]
        if len(eligible) < high_count * (2 if portfolio == "high-low" else 1):
            target = {symbol: 0.0 for symbol in symbols}
        else:
            rank_score = {symbol: 0.0 for symbol in eligible}
            venues = [bybit_basis] if venue == "bybit" else [bybit_basis, okx_basis]
            for history in venues:
                ordered = sorted(eligible, key=lambda symbol: history[symbol][decision_time])
                for rank, symbol in enumerate(ordered):
                    rank_score[symbol] += rank
            ordered = sorted(eligible, key=lambda symbol: rank_score[symbol])
            highs = set(ordered[:high_count])
            lows = set(ordered[-high_count:])
            if portfolio == "long-high":
                target = {symbol: (1 / high_count if symbol in highs else 0.0) for symbol in symbols}
            else:
                target = {
                    symbol: (0.5 / high_count if symbol in highs else -0.5 / high_count if symbol in lows else 0.0)
                    for symbol in symbols
                }

        turnover = sum(abs(target[symbol] - weights[symbol]) for symbol in symbols)
        period_return = -turnover * cost_rate
        exit_time = decision_time + DAY_MS
        for symbol, weight in target.items():
            if weight == 0:
                continue
            period_return += weight * (opens[symbol][i + 2] / opens[symbol][i + 1] - 1)
            times = funding_times[symbol]
            left = bisect.bisect_right(times, decision_time)
            right = bisect.bisect_right(times, exit_time)
            period_return -= weight * sum(funding[symbol][timestamp] for timestamp in times[left:right])
        periods.append(period_return)
        weights = target

    if periods:
        periods[-1] -= sum(abs(weight) for weight in weights.values()) * cost_rate
    return periods


def main() -> None:
    parser = argparse.ArgumentParser(description="Peer-reviewed crypto futures basis transfer test")
    parser.add_argument("--symbols", default="BTC/USDT,ETH/USDT,XRP/USDT,SOL/USDT,BNB/USDT")
    parser.add_argument("--days", type=int, default=1460)
    parser.add_argument("--venue", choices=("bybit", "consensus"), default="consensus")
    parser.add_argument("--portfolio", choices=("long-high", "high-low"), default="long-high")
    parser.add_argument("--fee-bps", type=float, default=6.0)
    parser.add_argument("--execution-bps", type=float, default=5.0)
    parser.add_argument("--fold-days", type=int, default=180)
    parser.add_argument("--basis-cache-dir", type=Path, default=Path("results/basis_cache"))
    parser.add_argument("--funding-cache-dir", type=Path, default=Path("results/funding_cache"))
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--output", type=Path, default=Path("results/technical_basis_factor.json"))
    args = parser.parse_args()

    symbols = tuple(symbol.strip() for symbol in args.symbols.split(",") if symbol.strip())
    exchange = build_exchange(args.exchange)
    data = {symbol: _closed_rows(exchange, normalize_derivative_symbol(exchange, symbol), args.days) for symbol in symbols}
    timestamps = [int(row[0]) for row in next(iter(data.values()))]
    if any([int(row[0]) for row in rows] != timestamps for rows in data.values()):
        raise RuntimeError("daily universe is not aligned")
    bybit_basis = {symbol: _cached_series(args.basis_cache_dir, "bybit", symbol) for symbol in symbols}
    okx_basis = {symbol: _cached_series(args.basis_cache_dir, "okx", symbol) for symbol in symbols}
    funding = {symbol: _funding_series(args.funding_cache_dir, symbol, timestamps[0], timestamps[-1]) for symbol in symbols}
    periods = _simulate(
        data, bybit_basis, okx_basis, funding, args.venue, args.portfolio,
        (args.fee_bps + args.execution_bps) / 10_000,
    )
    folds = [_metrics(periods[start:start + args.fold_days]) for start in range(0, len(periods) - args.fold_days + 1, args.fold_days)]
    passing = [fold for fold in folds if fold["return_pct"] > 0 and fold["profit_factor"] > 1]
    full_period = _metrics(periods)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "paper": "Chi et al. (2023), Journal of Futures Markets, DOI 10.1002/fut.22425",
            "transfer_not_replication": "fixed current-liquid perpetual universe, 2022-2026; paper used a dynamic quarterly-futures universe, 2017-2021",
            "venue_signal": args.venue,
            "portfolio": args.portfolio,
            "high_basis_definition": "highest tercile of spot-minus-futures basis, equivalent to lowest perpetual premium",
            "execution": "signal at daily close; enter next daily open; hold one day; actual Bybit funding",
            "cost_bps_per_weight_turnover": args.fee_bps + args.execution_bps,
        },
        "full_period": full_period,
        "folds": folds,
        "passing_folds": len(passing),
        "folds_tested": len(folds),
        "eligible_for_tech_integration": full_period["return_pct"] > 0 and full_period["max_dd_pct"] <= 30 and len(passing) >= max(3, (len(folds) + 1) // 2) and statistics.median(fold["return_pct"] for fold in folds) > 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("full_period", "passing_folds", "folds_tested", "eligible_for_tech_integration")}, indent=2))


if __name__ == "__main__":
    main()
