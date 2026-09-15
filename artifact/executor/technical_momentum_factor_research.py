"""Causal liquid-perpetual test of the crypto cross-sectional momentum factor.

The construction follows the high-minus-low intuition in Liu, Tsyvinski & Wu
(2022), but is deliberately narrower: a fixed liquid allow-list, equal dollar
long/short legs, strict next-day return and explicit turnover cost. It is a
transfer test, not a claim to reproduce their survivorship-aware factor data.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from backtester import build_exchange, normalize_derivative_symbol
from technical_cross_asset_research import _closed_rows, _metrics


def _simulate(data: dict[str, list[list[float]]], top_n: int, formation_start: int, formation_end: int, fee_rate: float) -> list[float]:
    symbols = tuple(data)
    closes = {symbol: [float(row[4]) for row in rows] for symbol, rows in data.items()}
    weights = {symbol: 0.0 for symbol in symbols}
    periods: list[float] = []
    # At t, skip t-1 and measure cumulative relative performance t-end to
    # t-start. The future return is t->t+1, so no close is reused as a fill.
    for t in range(formation_end, len(next(iter(closes.values()))) - 1):
        ranked = sorted(
            symbols,
            key=lambda symbol: closes[symbol][t - formation_start] / closes[symbol][t - formation_end] - 1,
            reverse=True,
        )
        longs, shorts = set(ranked[:top_n]), set(ranked[-top_n:])
        target = {
            symbol: (0.5 / top_n if symbol in longs else -0.5 / top_n if symbol in shorts else 0.0)
            for symbol in symbols
        }
        turnover = sum(abs(target[symbol] - weights[symbol]) for symbol in symbols)
        gross = sum(target[symbol] * (closes[symbol][t + 1] / closes[symbol][t] - 1) for symbol in symbols)
        periods.append(gross - turnover * fee_rate)
        weights = target
    return periods


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-sectional momentum factor transfer test")
    parser.add_argument("--symbols", default="BTC/USDT,ETH/USDT,XRP/USDT,SOL/USDT,BNB/USDT,DOGE/USDT,ADA/USDT,AVAX/USDT,LINK/USDT,LTC/USDT")
    parser.add_argument("--days", type=int, default=1460)
    parser.add_argument("--top-n", type=int, default=2)
    parser.add_argument("--formation-start", type=int, default=2)
    parser.add_argument("--formation-end", type=int, default=12)
    parser.add_argument("--fee-bps", type=float, default=10.0)
    parser.add_argument("--fold-days", type=int, default=180)
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--output", type=Path, default=Path("results/technical_momentum_factor.json"))
    args = parser.parse_args()
    if not 1 <= args.top_n * 2 <= len(tuple(s for s in args.symbols.split(",") if s.strip())):
        raise ValueError("top-n requires separate long and short names within the universe")
    if not 1 <= args.formation_start < args.formation_end:
        raise ValueError("formation-start must be positive and smaller than formation-end")
    raw_symbols = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
    exchange = build_exchange(args.exchange)
    data = {raw: _closed_rows(exchange, normalize_derivative_symbol(exchange, raw), args.days) for raw in raw_symbols}
    if any(len(rows) < args.days * 0.9 for rows in data.values()):
        missing = [symbol for symbol, rows in data.items() if len(rows) < args.days * 0.9]
        raise RuntimeError(f"insufficient history for: {', '.join(missing)}")
    timestamps = [int(row[0]) for row in next(iter(data.values()))]
    if any([int(row[0]) for row in rows] != timestamps for rows in data.values()):
        raise RuntimeError("configured universe has non-aligned daily candles")
    periods = _simulate(data, args.top_n, args.formation_start, args.formation_end, args.fee_bps / 10_000)
    folds = [_metrics(periods[start:start + args.fold_days]) for start in range(0, len(periods) - args.fold_days + 1, args.fold_days)]
    passing = [fold for fold in folds if fold["return_pct"] > 0 and fold["profit_factor"] > 1]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "allowed_universe": raw_symbols,
            "universe_bias": "fixed current-liquid allow-list; not survivorship-free",
            "signal": f"long top-{args.top_n}, short bottom-{args.top_n} by return from t-{args.formation_end} to t-{args.formation_start}; hold t to t+1",
            "gross_exposure": 1.0,
            "net_exposure": 0.0,
            "cost_bps_per_weight_turnover": args.fee_bps,
            "execution": "daily close-to-close; no funding, leverage, stops or pyramiding; promotion requires funding-aware 4H simulation",
        },
        "full_period": _metrics(periods),
        "folds": folds,
        "passing_folds": len(passing),
        "folds_tested": len(folds),
        "eligible_for_further_research": len(passing) >= max(3, (len(folds) + 1) // 2) and statistics.median(f["return_pct"] for f in folds) > 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("full_period", "passing_folds", "folds_tested", "eligible_for_further_research")}, indent=2))


if __name__ == "__main__":
    main()
