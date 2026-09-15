"""Walk-forward optimizer for the Vibe technical strategy.

It intentionally reuses Backtester and its adverse fill/fee model.  Parameters
are selected only on the earlier train period, then evaluated once on a held-out
period.  This is a research gate, not an order-execution program.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtester import (
    Backtester,
    VibeTradingSignalGenerator,
    build_exchange,
    fetch_ohlcv_with_retry,
    normalize_derivative_symbol,
)


PARAMETERS: dict[str, tuple[float, ...]] = {
    # Coarse first pass: 32 combinations.  A narrower second pass is only
    # justified around parameters that also survive the sealed hold-out period.
    'VIBE_TREND_ADX': (18, 25),
    'VIBE_CHOP_ADX': (12, 18),
    'VIBE_HIGH_ATR_PCT': (0.03, 0.05),
    'VIBE_ATR_SL_MULTIPLIER': (1.0, 1.5),
    'VIBE_ATR_TP_MULTIPLIER': (2.0, 3.0),
}


def _metrics(result: Any) -> dict[str, float | int]:
    wins = [trade.pnl for trade in result.trades if trade.pnl > 0]
    losses = [-trade.pnl for trade in result.trades if trade.pnl <= 0]
    profit_factor = sum(wins) / sum(losses) if losses and sum(losses) else float('inf')
    # Penalize both unprofitable variants and variants whose result is entirely
    # explained by a drawdown that would be impractical to trade.
    score = result.total_return_pct - 0.75 * result.max_drawdown_pct
    return {
        'return_pct': round(result.total_return_pct, 4),
        'max_drawdown_pct': round(result.max_drawdown_pct, 4),
        'profit_factor': round(profit_factor, 4),
        'trades': len(result.trades),
        'win_rate_pct': round(result.win_rate, 4),
        'score': round(score, 4),
    }


def _run_with_data(
    exchange: Any,
    symbol: str,
    raw_4h: list[list[float]],
    raw_1d: list[list[float]],
    days: int,
    balance: float,
    fee: float,
    slippage_bps: float,
) -> Any:
    # Backtester normally fetches inside run().  Supplying immutable cached rows
    # ensures every candidate sees the exact same candles and cannot differ due
    # to a partially formed/latest candle returned by the exchange.
    import backtester as module

    original_fetch = module.fetch_ohlcv_with_retry

    def cached_fetch(_: Any, __: str, timeframe: str, **___: Any) -> list[list[float]]:
        if timeframe == '4h':
            return list(raw_4h)
        if timeframe == '1d':
            return list(raw_1d)
        raise ValueError(f'unexpected timeframe {timeframe}')

    module.fetch_ohlcv_with_retry = cached_fetch
    try:
        generator = VibeTradingSignalGenerator(exchange, publisher=None)
        return Backtester(
            exchange,
            generator,
            starting_balance=balance,
            fee_rate=fee,
            slippage_bps=slippage_bps,
            fill_mode='signal_close',
        ).run(symbol, days=days)
    finally:
        module.fetch_ohlcv_with_retry = original_fetch


def _set_parameters(values: dict[str, float]) -> dict[str, str | None]:
    previous = {key: os.environ.get(key) for key in PARAMETERS}
    for key, value in values.items():
        os.environ[key] = str(value)
    return previous


def _restore_parameters(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _window(rows: list[list[float]], start_ms: int | None, end_ms: int) -> list[list[float]]:
    return [row for row in rows if (start_ms is None or int(row[0]) >= start_ms) and int(row[0]) <= end_ms]


def main() -> None:
    parser = argparse.ArgumentParser(description='Train/hold-out optimizer for Vibe Tech')
    parser.add_argument('--symbol', default='XRP/USDT')
    parser.add_argument('--exchange', default='bybit')
    parser.add_argument('--days', type=int, default=365)
    parser.add_argument('--train-days', type=int, default=240)
    parser.add_argument('--balance', type=float, default=50.0)
    parser.add_argument('--fee', type=float, default=0.0004)
    parser.add_argument('--slippage-bps', type=float, default=5.0)
    parser.add_argument('--top', type=int, default=15)
    parser.add_argument('--min-train-trades', type=int, default=12,
                        help='Minimum completed train trades for a candidate to be ranked.')
    parser.add_argument('--min-holdout-trades', type=int, default=8,
                        help='Minimum completed hold-out trades for a candidate to pass.')
    parser.add_argument('--output', type=Path, default=Path('results/tech_walk_forward.json'))
    args = parser.parse_args()
    if not 120 <= args.train_days < args.days:
        raise ValueError('train-days must be at least 120 and less than days')

    exchange = build_exchange(args.exchange)
    symbol = normalize_derivative_symbol(exchange, args.symbol)
    raw_4h = fetch_ohlcv_with_retry(exchange, symbol, '4h', limit=max(args.days * 6, 250))
    raw_1d = fetch_ohlcv_with_retry(exchange, symbol, '1d', limit=max(args.days + 60, 120))
    if not raw_4h or not raw_1d:
        raise RuntimeError('no OHLCV data returned')

    end_ms = int(raw_4h[-1][0])
    test_days = args.days - args.train_days
    split_ms = end_ms - test_days * 86_400_000
    train_4h = _window(raw_4h, None, split_ms)
    train_1d = _window(raw_1d, None, split_ms)
    # Prepend 60 days of history solely for indicator warm-up; run(days=...) keeps
    # metrics restricted to the later hold-out interval.
    test_4h = _window(raw_4h, split_ms - 60 * 86_400_000, end_ms)
    test_1d = _window(raw_1d, split_ms - 60 * 86_400_000, end_ms)

    names = tuple(PARAMETERS)
    trials: list[dict[str, Any]] = []
    for combo in itertools.product(*(PARAMETERS[name] for name in names)):
        params = dict(zip(names, combo))
        if params['VIBE_CHOP_ADX'] >= params['VIBE_TREND_ADX']:
            continue
        previous = _set_parameters(params)
        try:
            result = _run_with_data(exchange, symbol, train_4h, train_1d, args.train_days, args.balance, args.fee, args.slippage_bps)
            metrics = _metrics(result)
            if metrics['trades'] >= args.min_train_trades:
                trials.append({'parameters': params, 'train': metrics})
        finally:
            _restore_parameters(previous)

    finalists = sorted(trials, key=lambda item: item['train']['score'], reverse=True)[:args.top]
    for item in finalists:
        previous = _set_parameters(item['parameters'])
        try:
            result = _run_with_data(exchange, symbol, test_4h, test_1d, test_days, args.balance, args.fee, args.slippage_bps)
            item['holdout'] = _metrics(result)
        finally:
            _restore_parameters(previous)

    passed = [item for item in finalists if item['holdout']['return_pct'] > 0 and item['holdout']['profit_factor'] > 1 and item['holdout']['trades'] >= args.min_holdout_trades]
    output = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'symbol': symbol,
        'exchange': exchange.id,
        'assumptions': {
            'days': args.days,
            'train_days': args.train_days,
            'holdout_days': test_days,
            'balance': args.balance,
            'fee_rate_per_fill': args.fee,
            'adverse_slippage_bps_per_fill': args.slippage_bps,
            'fill_mode': 'signal_close',
            'pyramiding_layers': os.getenv('MAX_PYRAMID_LAYERS', os.getenv('MAX_PYRAMID_CONTRACTS', '4')),
            'min_train_trades': args.min_train_trades,
            'min_holdout_trades': args.min_holdout_trades,
        },
        'trials_considered': len(trials),
        'holdout_passed': passed,
        'top_train_candidates': finalists,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps({
        'trials_considered': len(trials),
        'top_train_candidates': len(finalists),
        'holdout_passed': len(passed),
        'output': str(args.output),
        'passed': passed,
    }, indent=2))


if __name__ == '__main__':
    main()
