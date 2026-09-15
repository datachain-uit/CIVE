"""Walk-forward validation for the pre-specified Channel-breakout candidate.

This remains a research gate.  It does not import or change live execution.
The candidate was identified as a *family cluster* in the broad daily sweep;
this runner reports its stability per asset before any 4H implementation.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from backtester import build_exchange, fetch_ohlcv_with_retry, normalize_derivative_symbol
from technical_rule_research import DEFAULT_SYMBOLS, RuleSpec, _backtest


# Locked before this walk-forward run: daily compressed-channel breakout with
# a BTC market-state gate.  No per-asset parameter fitting is allowed here.
CHANNEL_CANDIDATE = RuleSpec(
    family="CHANNEL", lookback=10, threshold=0.0, persistence=1,
    channel_width=0.10, holding=0, up_up_gate=True,
    market_regime_gate=True, side="long",
)
SR_CANDIDATE = RuleSpec(
    family="SR", lookback=10, threshold=0.005, persistence=1,
    holding=5, up_up_gate=True, market_regime_gate=True, side="long",
)


def _closed_daily_rows(exchange, symbol: str, days: int) -> list[list[float]]:
    rows = fetch_ohlcv_with_retry(exchange, symbol, "1d", limit=days + 10)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if rows and int(rows[-1][0]) + 86_400_000 > now_ms:
        rows = rows[:-1]
    return rows[-days:]


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward Channel-breakout validation")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--market-symbol", default="BTC/USDT")
    parser.add_argument("--days", type=int, default=1460)
    parser.add_argument("--candidate", choices=("channel", "sr"), default="channel")
    parser.add_argument("--warmup-days", type=int, default=365)
    parser.add_argument("--test-days", type=int, default=180)
    parser.add_argument("--step-days", type=int, default=180)
    parser.add_argument("--fee-bps", type=float, default=10.0)
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--output", type=Path, default=Path("results/technical_channel_walkforward.json"))
    args = parser.parse_args()
    if min(args.warmup_days, args.test_days, args.step_days) <= 0:
        raise ValueError("walk-forward windows must be positive")

    exchange = build_exchange(args.exchange)
    candidate = CHANNEL_CANDIDATE if args.candidate == "channel" else SR_CANDIDATE
    market_symbol = normalize_derivative_symbol(exchange, args.market_symbol)
    market_rows = _closed_daily_rows(exchange, market_symbol, args.days)
    market_by_time = {int(row[0]): float(row[4]) for row in market_rows}
    fold_starts = list(range(args.warmup_days, args.days - args.test_days, args.step_days))
    per_asset: dict[str, dict] = {}

    for raw_symbol in (s.strip() for s in args.symbols.split(",") if s.strip()):
        symbol = normalize_derivative_symbol(exchange, raw_symbol)
        rows = _closed_daily_rows(exchange, symbol, args.days)
        market_closes = [market_by_time.get(int(row[0])) for row in rows]
        if len(rows) < args.days * 0.9 or any(close is None for close in market_closes):
            raise RuntimeError(f"insufficient aligned data for {raw_symbol}")

        folds = []
        for start in fold_starts:
            end = min(start + args.test_days, len(rows) - 1)
            # Preserve state from all observations before this test window while
            # reporting returns only from [start, end).  _backtest's hold-out
            # begins at split_index, so truncating at end isolates one fold.
            _, test = _backtest(
                candidate, rows[:end + 1], args.fee_bps / 10_000, start,
                market_closes=market_closes[:end + 1],
            )
            folds.append({"start_index": start, "end_index": end, **test})

        passing = [f for f in folds if f["return_pct"] > 0 and f["profit_factor"] > 1 and f["trades"] >= 3]
        returns = [f["return_pct"] for f in folds]
        per_asset[raw_symbol] = {
            "folds": folds,
            "median_fold_return_pct": round(statistics.median(returns), 4),
            "mean_fold_return_pct": round(statistics.mean(returns), 4),
            "passing_folds": len(passing),
            "folds_tested": len(folds),
            "eligible_for_4h_execution_test": len(passing) >= max(3, (len(folds) + 1) // 2) and statistics.median(returns) > 0,
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate": {"label": candidate.label, "spec": candidate.__dict__},
        "protocol": {
            "daily_data": "closed UTC candles only; close-to-close accounting",
            "market_state_proxy": args.market_symbol,
            "warmup_days": args.warmup_days,
            "test_days": args.test_days,
            "step_days": args.step_days,
            "fee_bps_per_position_change": args.fee_bps,
            "promotion": "majority of folds pass and median fold return is positive; then 4H execution test only",
        },
        "per_asset": per_asset,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({
        "candidate": candidate.label,
        "assets": {symbol: {key: value[key] for key in ("passing_folds", "folds_tested", "median_fold_return_pct", "eligible_for_4h_execution_test")} for symbol, value in per_asset.items()},
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
