"""Daily research gate for an independent short-only Bear book.

The long portfolio is not inverted.  A short is allowed only in a persistent
BTC DOWN->DOWN state and after a pre-existing compressed-channel breakdown.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from backtester import build_exchange, fetch_ohlcv_with_retry, normalize_derivative_symbol
from technical_cross_asset_research import _closed_rows, _metrics
from technical_rule_research import RuleSpec, _long_exit, _long_signal


BREAKDOWN = RuleSpec("CHANNEL", 10, 0.0, 1, channel_width=0.10, holding=0, side="short")


def main() -> None:
    parser = argparse.ArgumentParser(description="Short-only Bear-book research")
    parser.add_argument("--symbols", default="BTC/USDT,ETH/USDT,XRP/USDT,SOL/USDT,BNB/USDT")
    parser.add_argument("--market-symbol", default="BTC/USDT")
    parser.add_argument("--days", type=int, default=1460)
    parser.add_argument("--top-n", type=int, default=2)
    parser.add_argument("--rank-days", type=int, default=20)
    parser.add_argument("--fold-days", type=int, default=180)
    parser.add_argument("--fee-bps", type=float, default=10.0)
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--output", type=Path, default=Path("results/technical_bear_research.json"))
    args = parser.parse_args()
    raw_symbols = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
    exchange = build_exchange(args.exchange)
    market_rows = _closed_rows(exchange, normalize_derivative_symbol(exchange, args.market_symbol), args.days)
    market_by_time = {int(row[0]): float(row[4]) for row in market_rows}
    data = {raw: _closed_rows(exchange, normalize_derivative_symbol(exchange, raw), args.days) for raw in raw_symbols}
    timestamps = [int(row[0]) for row in next(iter(data.values()))]
    if any([int(row[0]) for row in rows] != timestamps for rows in data.values()):
        raise RuntimeError("daily universe is not aligned")
    market = [market_by_time.get(timestamp) for timestamp in timestamps]
    if any(value is None for value in market):
        raise RuntimeError("market proxy is not aligned")
    closes = {s: [float(r[4]) for r in rows] for s, rows in data.items()}
    highs = {s: [float(r[2]) for r in rows] for s, rows in data.items()}
    lows = {s: [float(r[3]) for r in rows] for s, rows in data.items()}
    active: set[str] = set()
    weights = {s: 0.0 for s in raw_symbols}
    periods: list[float] = []
    for i in range(max(20, args.rank_days), len(timestamps) - 1):
        down_down = market[i] <= market[i - 7] <= market[i - 14]
        if not down_down:
            active.clear()
        else:
            active = {s for s in active if not _long_signal(BREAKDOWN, closes[s], highs[s], lows[s], i)}
            entrants = [s for s in raw_symbols if s not in active and _long_exit(BREAKDOWN, closes[s], highs[s], lows[s], i)]
            entrants.sort(key=lambda s: closes[s][i] / closes[s][i - args.rank_days] - 1)
            active.update(entrants[:max(0, args.top_n - len(active))])
        target = {s: (-1 / len(active) if s in active else 0.0) for s in raw_symbols}
        turnover = sum(abs(target[s] - weights[s]) for s in raw_symbols)
        gross = sum(target[s] * (closes[s][i + 1] / closes[s][i] - 1) for s in raw_symbols)
        periods.append(gross - turnover * args.fee_bps / 10_000)
        weights = target
    folds = [_metrics(periods[start:start + args.fold_days]) for start in range(0, len(periods) - args.fold_days + 1, args.fold_days)]
    passing = [fold for fold in folds if fold["return_pct"] > 0 and fold["profit_factor"] > 1]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {"allowed_universe": raw_symbols, "entry": "BTC DOWN-DOWN + 10d compressed channel breakdown + lowest 20d momentum", "exit": "opposite channel breakout or regime off", "top_n": args.top_n, "fee_bps": args.fee_bps},
        "full_period": _metrics(periods), "folds": folds, "passing_folds": len(passing), "folds_tested": len(folds),
        "eligible_for_execution_test": len(passing) >= max(3, (len(folds) + 1) // 2) and statistics.median(f["return_pct"] for f in folds) > 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("full_period", "passing_folds", "folds_tested", "eligible_for_execution_test")}, indent=2))


if __name__ == "__main__":
    main()
