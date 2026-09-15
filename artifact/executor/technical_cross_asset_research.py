"""Research-only cross-asset Technical portfolio.

The configured universe is a hard allow-list.  The strategy may select only
from that list; it never discovers or trades an outside symbol.  This turns
technical events into entries in a portfolio process instead of assuming a
single indicator is a complete per-coin strategy.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

from backtester import build_exchange, fetch_ohlcv_with_retry, normalize_derivative_symbol
from technical_rule_research import RuleSpec, _long_exit, _long_signal


CHANNEL_EVENT = RuleSpec(
    family="CHANNEL", lookback=10, threshold=0.0, persistence=1,
    channel_width=0.10, holding=0, side="long",
)
SR_EVENT = RuleSpec(
    family="SR", lookback=10, threshold=0.005, persistence=1,
    holding=5, side="long",
)


def _closed_rows(exchange, symbol: str, days: int) -> list[list[float]]:
    rows = fetch_ohlcv_with_retry(exchange, symbol, "1d", limit=days + 10)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if rows and int(rows[-1][0]) + 86_400_000 > now_ms:
        rows = rows[:-1]
    return rows[-days:]


def _metrics(periods: list[float]) -> dict:
    equity = peak = 1.0
    max_dd = 0.0
    positive = negative = 0.0
    for ret in periods:
        equity *= 1 + ret
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
        positive += max(ret, 0)
        negative -= min(ret, 0)
    return {
        "return_pct": round((equity - 1) * 100, 4),
        "profit_factor": round(positive / negative if negative else 0.0, 4),
        "max_dd_pct": round(max_dd * 100, 4),
    }


def _simulate(
    data: dict[str, list[list[float]]],
    market_closes: list[float],
    fee_rate: float,
    top_n: int,
    rank_days: int,
    event: RuleSpec,
) -> list[float]:
    """Daily close-to-close portfolio returns, with only causal observations."""
    symbols = list(data)
    closes = {symbol: [float(row[4]) for row in rows] for symbol, rows in data.items()}
    highs = {symbol: [float(row[2]) for row in rows] for symbol, rows in data.items()}
    lows = {symbol: [float(row[3]) for row in rows] for symbol, rows in data.items()}
    positions: set[str] = set()
    weights = {symbol: 0.0 for symbol in symbols}
    periods: list[float] = []
    warmup = max(20, rank_days, event.lookback)

    for i in range(warmup, len(market_closes) - 1):
        market_up_up = market_closes[i] >= market_closes[i - 7] >= market_closes[i - 14]
        if not market_up_up:
            positions.clear()
        else:
            positions = {
                symbol for symbol in positions
                if not _long_exit(event, closes[symbol], highs[symbol], lows[symbol], i)
            }
            slots = max(0, top_n - len(positions))
            entrants = [
                symbol for symbol in symbols
                if symbol not in positions
                and _long_signal(event, closes[symbol], highs[symbol], lows[symbol], i)
            ]
            entrants.sort(key=lambda symbol: closes[symbol][i] / closes[symbol][i - rank_days] - 1, reverse=True)
            positions.update(entrants[:slots])

        target = {symbol: (1 / len(positions) if symbol in positions else 0.0) for symbol in symbols}
        turnover = sum(abs(target[symbol] - weights[symbol]) for symbol in symbols)
        gross = sum(target[symbol] * (closes[symbol][i + 1] / closes[symbol][i] - 1) for symbol in symbols)
        periods.append(gross - turnover * fee_rate)
        weights = target
    return periods


def _risk_managed_weights(
    selected: set[str],
    closes: dict[str, list[float]],
    index: int,
    vol_days: int,
) -> dict[str, float]:
    """Inverse-realized-volatility weights, normalised without leverage.

    The calculation is deliberately limited to closes available at ``index``.
    It tests the risk-managed-momentum mechanism from the literature without
    silently increasing portfolio leverage to hit a volatility target.
    """
    if not selected:
        return {symbol: 0.0 for symbol in closes}
    inverse_vol: dict[str, float] = {}
    for symbol in selected:
        returns = [
            closes[symbol][t] / closes[symbol][t - 1] - 1
            for t in range(index - vol_days + 1, index + 1)
        ]
        volatility = statistics.pstdev(returns) if len(returns) > 1 else 0.0
        inverse_vol[symbol] = 1 / max(volatility, 1e-6)
    total = sum(inverse_vol.values())
    return {symbol: inverse_vol.get(symbol, 0.0) / total for symbol in closes}


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-asset Technical portfolio research")
    parser.add_argument("--symbols", default="BTC/USDT,ETH/USDT,XRP/USDT,SOL/USDT,BNB/USDT")
    parser.add_argument("--market-symbol", default="BTC/USDT")
    parser.add_argument("--days", type=int, default=1460)
    parser.add_argument("--top-n", type=int, default=2)
    parser.add_argument("--rank-days", type=int, default=20)
    parser.add_argument("--weighting", choices=("equal", "inverse-vol"), default="equal")
    parser.add_argument("--vol-days", type=int, default=20)
    parser.add_argument("--event-family", choices=("channel", "sr"), default="channel")
    parser.add_argument("--fold-days", type=int, default=180)
    parser.add_argument("--fee-bps", type=float, default=10.0)
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--output", type=Path, default=Path("results/technical_cross_asset_research.json"))
    args = parser.parse_args()
    raw_symbols = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
    if not 1 <= args.top_n <= len(raw_symbols):
        raise ValueError("top-n must be between 1 and the number of allowed symbols")

    exchange = build_exchange(args.exchange)
    market_rows = _closed_rows(exchange, normalize_derivative_symbol(exchange, args.market_symbol), args.days)
    market_by_time = {int(row[0]): float(row[4]) for row in market_rows}
    data: dict[str, list[list[float]]] = {}
    for raw_symbol in raw_symbols:
        rows = _closed_rows(exchange, normalize_derivative_symbol(exchange, raw_symbol), args.days)
        if len(rows) < args.days * 0.9:
            raise RuntimeError(f"insufficient data for {raw_symbol}")
        data[raw_symbol] = rows

    timestamps = [int(row[0]) for row in next(iter(data.values()))]
    if any([int(row[0]) for row in rows] != timestamps for rows in data.values()):
        raise RuntimeError("configured symbols have non-aligned daily candles")
    market_closes = [market_by_time.get(timestamp) for timestamp in timestamps]
    if any(value is None for value in market_closes):
        raise RuntimeError("market proxy has missing dates")
    event = CHANNEL_EVENT if args.event_family == "channel" else SR_EVENT
    if args.weighting == "equal":
        periods = _simulate(data, market_closes, args.fee_bps / 10_000, args.top_n, args.rank_days, event)
    else:
        # Same selection and causal close-to-close timing as _simulate, but
        # replaces equal weights with unlevered inverse-volatility weights.
        closes = {symbol: [float(row[4]) for row in rows] for symbol, rows in data.items()}
        highs = {symbol: [float(row[2]) for row in rows] for symbol, rows in data.items()}
        lows = {symbol: [float(row[3]) for row in rows] for symbol, rows in data.items()}
        positions: set[str] = set()
        weights = {symbol: 0.0 for symbol in raw_symbols}
        periods = []
        warmup = max(20, args.rank_days, args.vol_days, event.lookback)
        for i in range(warmup, len(market_closes) - 1):
            if not (market_closes[i] >= market_closes[i - 7] >= market_closes[i - 14]):
                positions.clear()
            else:
                positions = {symbol for symbol in positions if not _long_exit(event, closes[symbol], highs[symbol], lows[symbol], i)}
                entrants = [symbol for symbol in raw_symbols if symbol not in positions and _long_signal(event, closes[symbol], highs[symbol], lows[symbol], i)]
                entrants.sort(key=lambda symbol: closes[symbol][i] / closes[symbol][i - args.rank_days] - 1, reverse=True)
                positions.update(entrants[:max(0, args.top_n - len(positions))])
            target = _risk_managed_weights(positions, closes, i, args.vol_days)
            turnover = sum(abs(target[symbol] - weights[symbol]) for symbol in raw_symbols)
            gross = sum(target[symbol] * (closes[symbol][i + 1] / closes[symbol][i] - 1) for symbol in raw_symbols)
            periods.append(gross - turnover * args.fee_bps / 10_000)
            weights = target
    folds = [_metrics(periods[start:start + args.fold_days]) for start in range(0, len(periods) - args.fold_days + 1, args.fold_days)]
    passing = [fold for fold in folds if fold["return_pct"] > 0 and fold["profit_factor"] > 1]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "allowed_universe": raw_symbols,
            "market_state": f"{args.market_symbol} 7d>=0 for two consecutive weeks",
            "entry": f"{event.label}; only top-N by trailing momentum among fresh events",
            "exit": "opposite event or market state off",
            "top_n": args.top_n,
            "rank_days": args.rank_days,
            "weighting": args.weighting,
            "vol_days": args.vol_days if args.weighting == "inverse-vol" else None,
            "fee_bps_per_weight_turnover": args.fee_bps,
            "execution": "daily close-to-close; no leverage, stops or pyramiding",
        },
        "full_period": _metrics(periods),
        "folds": folds,
        "passing_folds": len(passing),
        "folds_tested": len(folds),
        "eligible_for_execution_test": len(passing) >= max(3, (len(folds) + 1) // 2) and statistics.median(fold["return_pct"] for fold in folds) > 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("full_period", "passing_folds", "folds_tested", "eligible_for_execution_test")}, indent=2))


if __name__ == "__main__":
    main()
