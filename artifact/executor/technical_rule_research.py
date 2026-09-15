"""Pre-registered daily technical-rule research runner.

This is deliberately separate from the live executor.  It reproduces the
technical-rule *families* from Hudson & Urquhart (2021) with one shared,
close-to-close accounting convention before any rule is promoted to 4H
execution, ATR sizing or pyramiding.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from backtester import build_exchange, fetch_ohlcv_with_retry, normalize_derivative_symbol


DEFAULT_SYMBOLS = ("BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT", "BNB/USDT")


@dataclass(frozen=True)
class RuleSpec:
    family: str
    lookback: int
    threshold: float
    persistence: int
    fast: int = 0
    slow: int = 0
    channel_width: float = 0.0
    rsi_period: int = 0
    rsi_lower: float = 0.0
    rsi_upper: float = 0.0
    holding: int = 0  # 0 = hold until reversal; otherwise fixed holding periods
    up_up_gate: bool = False
    market_regime_gate: bool = False
    side: str = "long"

    @property
    def label(self) -> str:
        fields = [self.family, f"j={self.lookback}", f"x={self.threshold:g}", f"d={self.persistence}"]
        if self.fast:
            fields += [f"fast={self.fast}", f"slow={self.slow}"]
        if self.channel_width:
            fields += [f"c={self.channel_width:g}"]
        if self.rsi_period:
            fields += [f"rsi={self.rsi_period}", f"lo={self.rsi_lower:g}", f"hi={self.rsi_upper:g}"]
        fields += ["exit=reverse" if self.holding == 0 else f"k={self.holding}"]
        fields += [
            "regime=UPUP-market" if self.up_up_gate and self.market_regime_gate
            else "regime=UPUP-asset" if self.up_up_gate
            else "regime=none"
        ]
        fields += [f"side={self.side}"]
        return "|".join(fields)


@dataclass
class Result:
    symbol: str
    spec: RuleSpec
    train_return_pct: float
    holdout_return_pct: float
    holdout_pf: float
    holdout_max_dd_pct: float
    holdout_trades: int
    holdout_turnover: int


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sma(values: list[float], end: int, period: int) -> float | None:
    if end + 1 < period:
        return None
    return _mean(values[end - period + 1:end + 1])


def _rsi(closes: list[float], end: int, period: int) -> float | None:
    if end < period:
        return None
    gains = losses = 0.0
    for index in range(end - period + 1, end + 1):
        change = closes[index] - closes[index - 1]
        gains += max(change, 0.0)
        losses -= min(change, 0.0)
    if losses == 0:
        return 100.0
    relative_strength = gains / losses
    return 100 - 100 / (1 + relative_strength)


def _persisted(condition: Iterable[bool], periods: int) -> bool:
    values = list(condition)
    return len(values) >= periods and all(values[-periods:])


def _long_signal(
    spec: RuleSpec,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    i: int,
    apply_regime: bool = True,
    regime_closes: list[float] | None = None,
) -> bool:
    """Signal at close i, using no observation after i."""
    if i < max(spec.lookback, spec.slow, spec.persistence):
        return False
    if apply_regime and spec.up_up_gate:
        state_closes = regime_closes if spec.market_regime_gate and regime_closes is not None else closes
        if i < 14 or not (state_closes[i] >= state_closes[i - 7] and state_closes[i - 7] >= state_closes[i - 14]):
            return False
    if spec.family == "MA":
        conditions: list[bool] = []
        for t in range(i - spec.persistence + 1, i + 1):
            fast = _sma(closes, t, spec.fast)
            slow = _sma(closes, t, spec.slow)
            conditions.append(fast is not None and slow is not None and fast > slow * (1 + spec.threshold))
        return _persisted(conditions, spec.persistence)

    if spec.family == "FILTER":
        conditions = []
        for t in range(i - spec.persistence + 1, i + 1):
            start = t - spec.lookback
            if start < 0:
                return False
            pivot_low = min(lows[start:t])
            conditions.append(closes[t] >= pivot_low * (1 + spec.threshold))
        return _persisted(conditions, spec.persistence)

    if spec.family == "CHANNEL":
        conditions = []
        for t in range(i - spec.persistence + 1, i + 1):
            start = t - spec.lookback
            if start < 0:
                return False
            prior_high = max(highs[start:t])
            prior_low = min(lows[start:t])
            compressed = (prior_high / prior_low - 1) <= spec.channel_width
            conditions.append(compressed and closes[t] > prior_high * (1 + spec.threshold))
        return _persisted(conditions, spec.persistence)

    if spec.family == "SR":
        conditions = []
        for t in range(i - spec.persistence + 1, i + 1):
            start = t - spec.lookback
            if start < 0:
                return False
            resistance = max(highs[start:t])
            conditions.append(closes[t] > resistance * (1 + spec.threshold))
        return _persisted(conditions, spec.persistence)

    if spec.family == "RSI":
        conditions = []
        for t in range(i - spec.persistence + 1, i + 1):
            current, previous = _rsi(closes, t, spec.rsi_period), _rsi(closes, t - 1, spec.rsi_period)
            conditions.append(current is not None and previous is not None and previous <= spec.rsi_lower < current)
        return _persisted(conditions, spec.persistence)

    raise ValueError(f"unsupported family: {spec.family}")


def _long_exit(spec: RuleSpec, closes: list[float], highs: list[float], lows: list[float], i: int) -> bool:
    """Opposite event for the T05-style reversal-exit variants."""
    if i < max(spec.lookback, spec.slow, spec.persistence):
        return False
    if spec.family == "MA":
        conditions = []
        for t in range(i - spec.persistence + 1, i + 1):
            fast = _sma(closes, t, spec.fast)
            slow = _sma(closes, t, spec.slow)
            conditions.append(fast is not None and slow is not None and fast < slow * (1 - spec.threshold))
        return _persisted(conditions, spec.persistence)
    if spec.family == "FILTER":
        conditions = []
        for t in range(i - spec.persistence + 1, i + 1):
            start = t - spec.lookback
            if start < 0:
                return False
            pivot_high = max(highs[start:t])
            conditions.append(closes[t] <= pivot_high * (1 - spec.threshold))
        return _persisted(conditions, spec.persistence)
    if spec.family == "CHANNEL":
        conditions = []
        for t in range(i - spec.persistence + 1, i + 1):
            start = t - spec.lookback
            if start < 0:
                return False
            prior_high = max(highs[start:t])
            prior_low = min(lows[start:t])
            compressed = (prior_high / prior_low - 1) <= spec.channel_width
            conditions.append(compressed and closes[t] < prior_low * (1 - spec.threshold))
        return _persisted(conditions, spec.persistence)
    if spec.family == "SR":
        conditions = []
        for t in range(i - spec.persistence + 1, i + 1):
            start = t - spec.lookback
            if start < 0:
                return False
            support = min(lows[start:t])
            conditions.append(closes[t] < support * (1 - spec.threshold))
        return _persisted(conditions, spec.persistence)
    if spec.family == "RSI":
        conditions = []
        for t in range(i - spec.persistence + 1, i + 1):
            current, previous = _rsi(closes, t, spec.rsi_period), _rsi(closes, t - 1, spec.rsi_period)
            conditions.append(current is not None and previous is not None and previous >= spec.rsi_upper > current)
        return _persisted(conditions, spec.persistence)
    raise ValueError(f"unsupported family: {spec.family}")


def _backtest(
    spec: RuleSpec,
    rows: list[list[float]],
    fee_rate: float,
    split_index: int,
    market_closes: list[float] | None = None,
) -> tuple[dict, dict]:
    closes = [float(r[4]) for r in rows]
    highs = [float(r[2]) for r in rows]
    lows = [float(r[3]) for r in rows]
    if market_closes is not None and len(market_closes) != len(closes):
        raise ValueError("market-regime series must align with the traded symbol")
    position = 0
    holding_age = 0
    periods: list[tuple[float, int]] = []

    # A signal available at close i earns only the i->i+1 close-to-close return.
    for i in range(max(spec.lookback, spec.slow, spec.persistence), len(closes) - 1):
        if spec.side == "short":
            state_closes = market_closes if spec.market_regime_gate and market_closes is not None else closes
            down_down = (not spec.up_up_gate or (i >= 14 and state_closes[i] <= state_closes[i - 7] and state_closes[i - 7] <= state_closes[i - 14]))
            entry_event = down_down and _long_exit(spec, closes, highs, lows, i)
            exit_event = _long_signal(spec, closes, highs, lows, i, apply_regime=False)
            direction = -1
        elif spec.side == "regime":
            trend = _sma(closes, i, 50)
            state_closes = market_closes if spec.market_regime_gate and market_closes is not None else closes
            up_up = not spec.up_up_gate or (i >= 14 and state_closes[i] >= state_closes[i - 7] and state_closes[i - 7] >= state_closes[i - 14])
            down_down = not spec.up_up_gate or (i >= 14 and state_closes[i] <= state_closes[i - 7] and state_closes[i - 7] <= state_closes[i - 14])
            long_event = _long_signal(spec, closes, highs, lows, i, apply_regime=False)
            short_event = _long_exit(spec, closes, highs, lows, i)
            if position > 0:
                entry_event, exit_event, direction = False, short_event, 1
            elif position < 0:
                entry_event, exit_event, direction = False, long_event, -1
            elif trend is not None and closes[i] > trend and up_up and long_event:
                entry_event, exit_event, direction = True, False, 1
            elif trend is not None and closes[i] < trend and down_down and short_event:
                entry_event, exit_event, direction = True, False, -1
            else:
                entry_event, exit_event, direction = False, False, 0
        else:
            entry_event = _long_signal(spec, closes, highs, lows, i, regime_closes=market_closes)
            exit_event = _long_exit(spec, closes, highs, lows, i)
            direction = 1
        if position == 0:
            next_position = direction if entry_event else 0
            holding_age = 0
        else:
            holding_age += 1
            should_exit = holding_age >= spec.holding if spec.holding else exit_event
            # Preserve the active direction.  In particular, a short must not
            # silently become a long after its entry bar.
            next_position = 0 if should_exit else position
            if should_exit:
                holding_age = 0
        turnover = abs(next_position - position)
        gross = (closes[i + 1] / closes[i] - 1) * next_position
        net = gross - turnover * fee_rate
        periods.append((net, turnover))
        position = next_position

    def metrics(segment: list[tuple[float, int]]) -> dict:
        compounded = math.prod(1 + ret for ret, _ in segment) - 1 if segment else 0.0
        positives = sum(max(ret, 0) for ret, _ in segment)
        negatives = -sum(min(ret, 0) for ret, _ in segment)
        pf = positives / negatives if negatives else 0.0
        equity = peak = 1.0
        max_dd = 0.0
        for ret, _ in segment:
            equity *= 1 + ret
            peak = max(peak, equity)
            max_dd = max(max_dd, 1 - equity / peak)
        return {
            "return_pct": compounded * 100,
            "profit_factor": pf,
            "max_dd_pct": max_dd * 100,
            "turnover": sum(turnover for _, turnover in segment),
            "trades": sum(turnover for _, turnover in segment),
        }

    # periods[0] corresponds to original index warmup -> warmup+1.
    warmup = max(spec.lookback, spec.slow, spec.persistence)
    train_periods = periods[:max(0, split_index - warmup)]
    holdout_periods = periods[max(0, split_index - warmup):]
    return metrics(train_periods), metrics(holdout_periods)


def rule_grid() -> list[RuleSpec]:
    specs: list[RuleSpec] = []
    for fast, slow in ((5, 20), (10, 50)):
        for threshold in (0.0, 0.005):
            for persistence in (1, 2):
                for holding in (0, 3, 5):
                    for up_up_gate in (False, True):
                        for market_regime_gate in ((False, True) if up_up_gate else (False,)):
                            for side in ("long", "short", "regime"):
                                specs.append(RuleSpec("MA", slow, threshold, persistence, fast=fast, slow=slow, holding=holding, up_up_gate=up_up_gate, market_regime_gate=market_regime_gate, side=side))
    for lookback in (10, 20, 50):
        for threshold in (0.01, 0.03, 0.05):
            for persistence in (1, 2):
                for holding in (0, 3, 5):
                    for up_up_gate in (False, True):
                        for market_regime_gate in ((False, True) if up_up_gate else (False,)):
                            for side in ("long", "short", "regime"):
                                specs.append(RuleSpec("FILTER", lookback, threshold, persistence, holding=holding, up_up_gate=up_up_gate, market_regime_gate=market_regime_gate, side=side))
    for lookback in (10, 20, 50):
        for width in (0.03, 0.05, 0.10):
            for threshold in (0.0, 0.005):
                for persistence in (1, 2):
                    for holding in (0, 3, 5):
                        for up_up_gate in (False, True):
                            for market_regime_gate in ((False, True) if up_up_gate else (False,)):
                                for side in ("long", "short", "regime"):
                                    specs.append(RuleSpec("CHANNEL", lookback, threshold, persistence, channel_width=width, holding=holding, up_up_gate=up_up_gate, market_regime_gate=market_regime_gate, side=side))
    for lookback in (10, 20, 50):
        for threshold in (0.0, 0.005):
            for persistence in (1, 2):
                for holding in (0, 3, 5):
                    for up_up_gate in (False, True):
                        for market_regime_gate in ((False, True) if up_up_gate else (False,)):
                            for side in ("long", "short", "regime"):
                                specs.append(RuleSpec("SR", lookback, threshold, persistence, holding=holding, up_up_gate=up_up_gate, market_regime_gate=market_regime_gate, side=side))
    for period in (7, 14):
        for lower, upper in ((20.0, 80.0), (30.0, 70.0), (40.0, 60.0)):
            for holding in (0, 3, 5):
                for up_up_gate in (False, True):
                    for market_regime_gate in ((False, True) if up_up_gate else (False,)):
                        for side in ("long", "short", "regime"):
                            specs.append(RuleSpec("RSI", period, 0.0, 1, holding=holding, up_up_gate=up_up_gate, market_regime_gate=market_regime_gate, side=side, rsi_period=period, rsi_lower=lower, rsi_upper=upper))
    return specs


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily technical-rule research runner")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--train-days", type=int, default=500)
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--market-symbol", default="BTC/USDT", help="BTC proxy for the market-wide T06 state ablation")
    parser.add_argument("--fee-bps", type=float, default=10.0, help="Round-trip-equivalent sensitivity per position change.")
    parser.add_argument("--output", type=Path, default=Path("results/technical_rule_research.json"))
    args = parser.parse_args()
    if not 180 <= args.train_days < args.days:
        raise ValueError("train-days must be at least 180 and less than days")

    exchange = build_exchange(args.exchange)
    specs = rule_grid()
    all_results: list[Result] = []
    market_symbol = normalize_derivative_symbol(exchange, args.market_symbol)
    market_rows = fetch_ohlcv_with_retry(exchange, market_symbol, "1d", limit=args.days + 10)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if market_rows and int(market_rows[-1][0]) + 86_400_000 > now_ms:
        market_rows = market_rows[:-1]
    market_by_timestamp = {int(row[0]): float(row[4]) for row in market_rows}
    for raw_symbol in (s.strip() for s in args.symbols.split(",") if s.strip()):
        symbol = normalize_derivative_symbol(exchange, raw_symbol)
        # A daily candle returned while the UTC trading day is still open is not
        # a valid close-to-close observation.  Keeping it would make the final
        # signal depend on information that was unavailable at a real daily
        # rebalance, so remove it before selecting the research window.
        rows = fetch_ohlcv_with_retry(exchange, symbol, "1d", limit=args.days + 10)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if rows and int(rows[-1][0]) + 86_400_000 > now_ms:
            rows = rows[:-1]
        rows = rows[-args.days:]
        if len(rows) < args.days * 0.9:
            raise RuntimeError(f"insufficient daily data for {raw_symbol}: {len(rows)} rows")
        market_closes = [market_by_timestamp.get(int(row[0])) for row in rows]
        if any(close is None for close in market_closes):
            raise RuntimeError(f"market state has missing dates for {raw_symbol}")
        split = min(args.train_days, len(rows) - 1)
        for spec in specs:
            train, holdout = _backtest(spec, rows, args.fee_bps / 10_000, split, market_closes=market_closes)
            all_results.append(Result(
                symbol=raw_symbol, spec=spec,
                train_return_pct=round(train["return_pct"], 4),
                holdout_return_pct=round(holdout["return_pct"], 4),
                holdout_pf=round(holdout["profit_factor"], 4),
                holdout_max_dd_pct=round(holdout["max_dd_pct"], 4),
                holdout_trades=holdout["trades"], holdout_turnover=holdout["turnover"],
            ))

    grouped: dict[str, list[Result]] = {}
    for result in all_results:
        grouped.setdefault(result.spec.label, []).append(result)
    ranked = []
    for label, results in grouped.items():
        trains = [r.train_return_pct for r in results]
        holdouts = [r.holdout_return_pct for r in results]
        train_positive_symbols = sum(r.train_return_pct > 0 for r in results)
        holdout_survivors = sum(r.holdout_return_pct > 0 and r.holdout_pf > 1 and r.holdout_trades >= 5 for r in results)
        ranked.append({
            "rule": label,
            "spec": asdict(results[0].spec),
            "median_train_return_pct": round(sorted(trains)[len(trains) // 2], 4),
            "mean_train_return_pct": round(_mean(trains), 4),
            "train_positive_symbols": train_positive_symbols,
            "median_holdout_return_pct": round(sorted(holdouts)[len(holdouts) // 2], 4),
            "mean_holdout_return_pct": round(_mean(holdouts), 4),
            "holdout_surviving_symbols": holdout_survivors,
            "symbols_tested": len(results),
        })
    # Ranking is based *only* on train data.  Hold-out fields are reported for
    # evaluation and must never decide which rule is selected.
    ranked.sort(key=lambda r: (r["train_positive_symbols"], r["median_train_return_pct"], r["mean_train_return_pct"]), reverse=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "days": args.days, "train_days": args.train_days,
            "holdout_days": args.days - args.train_days,
            "fee_bps_per_position_change": args.fee_bps,
            "incomplete_daily_tail": "dropped",
            "market_regime_proxy": args.market_symbol,
            "execution": "daily close-to-close; signal at close t earns t->t+1 only; long/flat; no leverage, stops or pyramiding",
            "selection_rule": "holdout return > 0, PF > 1, at least 5 position changes",
        },
        "ranked_rules": ranked,
        "per_symbol": [asdict(r) for r in all_results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"rules": len(ranked), "symbols": len(set(r.symbol for r in all_results)), "top": ranked[:10], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
