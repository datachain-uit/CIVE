"""Research-only cross-sectional crypto reversal/liquidity sleeve.

This is a causal, long-only adaptation of Bianchi, Babiak & Dickerson (2022).
It intentionally uses a fixed allow-list of liquid perpetuals, so it does not
claim the paper's survivorship-aware multi-exchange universe.  The purpose is
to falsify whether the low-relative-volume reversal mechanism transfers after
costs before it is ever combined with the existing trend core.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from backtester import build_exchange, normalize_derivative_symbol
from technical_cross_asset_research import _closed_rows, _metrics


def _relative_volume(volumes: list[float], index: int, lookback: int) -> float | None:
    """Today's volume divided by the prior, fully-known median volume."""
    history = volumes[index - lookback:index]
    if len(history) < lookback or not history:
        return None
    median = statistics.median(history)
    return volumes[index] / median if median > 0 else None


def _simulate(
    rows_by_symbol: dict[str, list[list[float]]],
    *,
    top_n: int,
    volume_lookback: int,
    volume_bucket: str,
    fee_rate: float,
) -> list[float]:
    """Close-to-close, one-day holding returns with causal turnover costs."""
    symbols = tuple(rows_by_symbol)
    closes = {symbol: [float(row[4]) for row in rows] for symbol, rows in rows_by_symbol.items()}
    volumes = {symbol: [float(row[5]) for row in rows] for symbol, rows in rows_by_symbol.items()}
    previous: set[str] = set()
    periods: list[float] = []

    # A 1-day loser is the pre-specified short-horizon reversal signal.  The
    # volume split is a direct low-versus-high activity check, not a tuned
    # parameter sweep.  We use t data to earn t->t+1 return.
    for index in range(max(2, volume_lookback), len(next(iter(closes.values()))) - 1):
        candidates: list[tuple[float, str]] = []
        for symbol in symbols:
            rel_volume = _relative_volume(volumes[symbol], index, volume_lookback)
            if rel_volume is None:
                continue
            if volume_bucket == "low" and rel_volume > 1.0:
                continue
            if volume_bucket == "high" and rel_volume < 1.0:
                continue
            one_day_return = closes[symbol][index] / closes[symbol][index - 1] - 1
            candidates.append((one_day_return, symbol))
        selected = {symbol for _, symbol in sorted(candidates)[:top_n]}
        target = {symbol: (1 / len(selected) if symbol in selected else 0.0) for symbol in symbols}
        before = {symbol: (1 / len(previous) if symbol in previous else 0.0) for symbol in symbols}
        turnover = sum(abs(target[symbol] - before[symbol]) for symbol in symbols)
        gross = sum(target[symbol] * (closes[symbol][index + 1] / closes[symbol][index] - 1) for symbol in symbols)
        periods.append(gross - turnover * fee_rate)
        previous = selected
    return periods


def main() -> None:
    parser = argparse.ArgumentParser(description="Causal cross-sectional reversal/liquidity research")
    parser.add_argument("--symbols", default="BTC/USDT,ETH/USDT,XRP/USDT,SOL/USDT,BNB/USDT,DOGE/USDT,ADA/USDT,AVAX/USDT,LINK/USDT,LTC/USDT")
    parser.add_argument("--days", type=int, default=1460)
    parser.add_argument("--top-n", type=int, default=2)
    parser.add_argument("--volume-lookback", type=int, default=20)
    parser.add_argument("--volume-bucket", choices=("low", "all", "high"), default="low")
    parser.add_argument("--fee-bps", type=float, default=10.0)
    parser.add_argument("--fold-days", type=int, default=180)
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--output", type=Path, default=Path("results/technical_reversal_liquidity.json"))
    args = parser.parse_args()
    raw_symbols = tuple(symbol.strip() for symbol in args.symbols.split(",") if symbol.strip())
    if not 1 <= args.top_n <= len(raw_symbols):
        raise ValueError("top-n must be between 1 and the configured universe size")

    exchange = build_exchange(args.exchange)
    data = {
        raw: _closed_rows(exchange, normalize_derivative_symbol(exchange, raw), args.days)
        for raw in raw_symbols
    }
    if any(len(rows) < args.days * 0.9 for rows in data.values()):
        missing = [symbol for symbol, rows in data.items() if len(rows) < args.days * 0.9]
        raise RuntimeError(f"insufficient history for: {', '.join(missing)}")
    timestamps = [int(row[0]) for row in next(iter(data.values()))]
    if any([int(row[0]) for row in rows] != timestamps for rows in data.values()):
        raise RuntimeError("configured universe has non-aligned daily candles")

    periods = _simulate(
        data, top_n=args.top_n, volume_lookback=args.volume_lookback,
        volume_bucket=args.volume_bucket, fee_rate=args.fee_bps / 10_000,
    )
    folds = [
        _metrics(periods[start:start + args.fold_days])
        for start in range(0, len(periods) - args.fold_days + 1, args.fold_days)
    ]
    passing = [fold for fold in folds if fold["return_pct"] > 0 and fold["profit_factor"] > 1]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "allowed_universe": raw_symbols,
            "universe_bias": "fixed current-liquid allow-list; not survivorship-free",
            "signal": "buy the top-N one-day losers at close; hold to next close",
            "volume_measure": "today volume / median of prior fully-closed volume-lookback days",
            "volume_bucket": args.volume_bucket,
            "volume_lookback": args.volume_lookback,
            "cost_bps_per_weight_turnover": args.fee_bps,
            "execution": "daily close-to-close; unlevered; no stop or pyramiding",
        },
        "full_period": _metrics(periods),
        "folds": folds,
        "passing_folds": len(passing),
        "folds_tested": len(folds),
        "eligible_for_further_research": len(passing) >= max(3, (len(folds) + 1) // 2)
        and statistics.median(fold["return_pct"] for fold in folds) > 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("full_period", "passing_folds", "folds_tested", "eligible_for_further_research")}, indent=2))


if __name__ == "__main__":
    main()
