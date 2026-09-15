"""Point-in-time, delta-neutral funding-carry research book.

Each selected notional is hedged: long spot and short the matching perpetual.
The model earns/loses realised perpetual funding and charges both legs on
entry/exit. This is research only; it needs simultaneous spot/perp execution
before it could be traded live.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backtester import build_exchange
from technical_cross_asset_execution import DAY_MS, _bybit_funding_history


def main() -> None:
    parser = argparse.ArgumentParser(description="Delta-neutral funding-carry research")
    parser.add_argument("--symbols", default="BTC/USDT,ETH/USDT,XRP/USDT,SOL/USDT,BNB/USDT")
    parser.add_argument("--days", type=int, default=1460)
    parser.add_argument("--top-n", type=int, default=2)
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--min-trailing-funding-bps", type=float, default=1.0)
    parser.add_argument("--fee-bps-per-leg", type=float, default=6.0)
    parser.add_argument("--slippage-bps-per-leg", type=float, default=5.0)
    parser.add_argument("--fold-days", type=int, default=180)
    parser.add_argument("--output", type=Path, default=Path("results/funding_carry_research.json"))
    args = parser.parse_args()
    symbols = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
    if not 1 <= args.top_n <= len(symbols):
        raise ValueError("top-n must fit the configured universe")
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    rates = {symbol: _bybit_funding_history(symbol, start_ms, end_ms) for symbol in symbols}
    daily = {symbol: {} for symbol in symbols}
    for symbol, records in rates.items():
        for timestamp, rate in records.items():
            day = timestamp - timestamp % DAY_MS
            daily[symbol][day] = daily[symbol].get(day, 0.0) + rate
    days = sorted(set().union(*(set(values) for values in daily.values())))
    weights = {symbol: 0.0 for symbol in symbols}
    periods: list[float] = []
    fee_per_turnover = 2 * (args.fee_bps_per_leg + args.slippage_bps_per_leg) / 10_000
    for index in range(args.lookback_days, len(days) - 1):
        day = days[index]
        scores = {
            symbol: sum(daily[symbol].get(days[t], 0.0) for t in range(index - args.lookback_days, index))
            for symbol in symbols
        }
        eligible = [symbol for symbol in symbols if scores[symbol] * 10_000 >= args.min_trailing_funding_bps]
        eligible.sort(key=lambda symbol: scores[symbol], reverse=True)
        selected = eligible[:args.top_n]
        target = {symbol: (1 / len(selected) if symbol in selected else 0.0) for symbol in symbols}
        turnover = sum(abs(target[symbol] - weights[symbol]) for symbol in symbols)
        # At day close, receive funding settled during this day for a short-perp
        # / long-spot hedge. The score used only funding known before this day.
        carry = sum(target[symbol] * daily[symbol].get(day, 0.0) for symbol in symbols)
        periods.append(carry - turnover * fee_per_turnover)
        weights = target
    folds = []
    for start_index in range(0, len(periods) - args.fold_days + 1, args.fold_days):
        values = periods[start_index:start_index + args.fold_days]
        equity = math.prod(1 + value for value in values)
        folds.append(round((equity - 1) * 100, 4))
    full_return = (math.prod(1 + value for value in periods) - 1) * 100
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "allowed_universe": symbols,
            "position": "equal-notional long spot / short perpetual",
            "selection": f"top-{args.top_n} trailing {args.lookback_days}d realised funding; signal is lagged one day",
            "min_trailing_funding_bps": args.min_trailing_funding_bps,
            "cost": "fee and slippage charged on both spot and perpetual legs",
            "funding": "public Bybit settled historical funding",
        },
        "result": {"return_pct": round(full_return, 4), "positive_folds": sum(value > 0 for value in folds), "folds_tested": len(folds), "fold_returns_pct": folds},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
