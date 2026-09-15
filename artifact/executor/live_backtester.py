from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass

try:
    import redis
    real_redis_from_url = redis.Redis.from_url if redis is not None else None
except Exception:
    redis = None  # type: ignore[assignment]
    real_redis_from_url = None

from backtester import (
    Backtester,
    VibeTradingSignalGenerator,
    build_exchange,
    fetch_ohlcv_with_retry,
    to_candles,
)


class FakePubSub:
    def subscribe(self, *_: Any, **__: Any) -> None:
        return None

    def get_message(self, *_: Any, **__: Any) -> None:
        return None

    def close(self) -> None:
        return None


class FakeRedis:
    def pubsub(self, *_: Any, **__: Any) -> FakePubSub:
        return FakePubSub()

    def get(self, *_: Any, **__: Any) -> None:
        return None

    def set(self, *_: Any, **__: Any) -> bool:
        return True

    def smembers(self, *_: Any, **__: Any) -> set[str]:
        return set()

    def hgetall(self, *_: Any, **__: Any) -> dict[str, str]:
        return {}

    def lpush(self, *_: Any, **__: Any) -> int:
        return 1

    def ltrim(self, *_: Any, **__: Any) -> bool:
        return True

    def sadd(self, *_: Any, **__: Any) -> int:
        return 1

    def expire(self, *_: Any, **__: Any) -> bool:
        return True


class SliceExchange:
    def __init__(self, base_exchange: Any, raw_4h: list[list[float]], raw_1d: list[list[float]]) -> None:
        self.base_exchange = base_exchange
        self.raw_4h = raw_4h
        self.raw_1d = raw_1d
        self.id = getattr(base_exchange, "id", "")

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int | None = None, since: int | None = None) -> list[list[float]]:
        data = self.raw_4h if timeframe == "4h" else self.raw_1d
        return data[-limit:] if limit else data

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base_exchange, name)


def _normalize_symbol(exchange: Any, symbol: str) -> str:
    if getattr(exchange, "id", "") in {"okx", "bybit"} and "/" in symbol and ":" not in symbol:
        return f"{symbol}:{symbol.split('/')[-1]}"
    return symbol


def _patch_redis() -> None:
    if redis is not None:
        redis.Redis.from_url = lambda *_args, **_kwargs: FakeRedis()  # type: ignore[attr-defined]


def _build_live_executor(base_exchange: Any) -> Any:
    _patch_redis()
    from executor import TradingExecutor

    executor = TradingExecutor()
    executor.exchange = base_exchange
    executor.dry_run = True
    executor._get_open_position_info = lambda _symbol: None
    executor._has_active_trade = lambda: False
    executor._entry_already_processed_for_candle = lambda _symbol, _timestamp: False
    return executor


def _signal_matches_live(signal: dict[str, Any], live_decision: Any) -> tuple[bool, list[str]]:
    differences: list[str] = []
    if signal.get("action") != ("TRADE" if live_decision.should_trade else "WAIT"):
        differences.append(f"action backtester={signal.get('action')} live={'TRADE' if live_decision.should_trade else 'WAIT'}")
    if signal.get("action") == "TRADE":
        checks = [
            ("side", signal.get("side"), live_decision.side),
            ("entry", round(float(signal.get("entry_price", 0)), 8), round(float(live_decision.entry_price or 0), 8)),
            ("stop_loss", round(float(signal.get("stop_loss_price", 0)), 8), round(float(live_decision.stop_loss_price or 0), 8)),
            ("take_profit", round(float(signal.get("take_profit_price", 0)), 8), round(float(live_decision.take_profit_price or 0), 8)),
        ]
        for label, expected, actual in checks:
            if expected != actual:
                differences.append(f"{label} backtester={expected} live={actual}")
    return not differences, differences


def compare_live_to_backtester(exchange: Any, symbol: str, days: int, balance: float, candles_to_compare: int) -> dict[str, Any]:
    raw_4h = fetch_ohlcv_with_retry(exchange, symbol, "4h", limit=max(days * 6, 250))
    raw_1d = fetch_ohlcv_with_retry(exchange, symbol, "1d", limit=max(days + 60, 120))
    candles_4h = to_candles(raw_4h)
    candles_1d = to_candles(raw_1d)
    generator = VibeTradingSignalGenerator(exchange, publisher=None)
    live_executor = _build_live_executor(exchange)
    live_executor.auto_trade_symbol = symbol

    max_compound_balance = float(os.getenv("MAX_COMPOUND_BALANCE", "1000.0"))
    rows: list[dict[str, Any]] = []
    start = max(80, len(raw_4h) - candles_to_compare - 1)
    stop = len(raw_4h) - 1

    for index in range(start, stop):
        window_4h = candles_4h[: index + 1]
        window_1d = [candle for candle in candles_1d if candle.timestamp + 86_400_000 <= window_4h[-1].timestamp]
        if len(window_1d) < 60:
            continue

        effective_balance = min(balance, max_compound_balance)
        signal = generator.generate(symbol, window_1d[-120:], window_4h[-200:], effective_balance)

        sliced_4h = raw_4h[: index + 2]
        last_1d_index = max(i for i, row in enumerate(raw_1d) if int(row[0]) + 86_400_000 <= window_4h[-1].timestamp)
        sliced_1d = raw_1d[: last_1d_index + 2]
        sliced_exchange = SliceExchange(exchange, sliced_4h, sliced_1d)
        live_executor.exchange = sliced_exchange
        live_executor.market_data_exchange = sliced_exchange
        live_decision = live_executor._build_vibe_decision()
        matched, differences = _signal_matches_live(signal, live_decision)

        rows.append(
            {
                "timestamp": signal["timestamp"],
                "backtester_action": signal.get("action"),
                "backtester_side": signal.get("side") if signal.get("action") == "TRADE" else None,
                "live_action": "TRADE" if live_decision.should_trade else "WAIT",
                "live_side": live_decision.side,
                "match": matched,
                "differences": differences,
            }
        )

    return {
        "symbol": symbol,
        "compared_candles": len(rows),
        "matches": sum(1 for row in rows if row["match"]),
        "mismatches": [row for row in rows if not row["match"]],
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare live Vibe decision logic with backtester logic.")
    parser.add_argument("--symbol", default=os.getenv("AUTO_TRADE_SYMBOL", os.getenv("BACKTEST_SYMBOL", "BTC/USDT")))
    parser.add_argument("--exchange", default=os.getenv("EXCHANGE_PLATFORM", os.getenv("CCXT_EXCHANGE", "okx")))
    parser.add_argument("--days", type=int, default=int(os.getenv("BACKTEST_DAYS", "30")))
    parser.add_argument("--balance", type=float, default=float(os.getenv("BACKTEST_BALANCE", "100")))
    parser.add_argument("--compare-candles", type=int, default=60)
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--write-redis", action="store_true", help="Write comparison result to Redis")
    args = parser.parse_args()

    exchange = build_exchange(args.exchange)
    symbol = _normalize_symbol(exchange, args.symbol)

    generator = VibeTradingSignalGenerator(exchange, publisher=None)
    backtester = Backtester(exchange, generator, starting_balance=args.balance)
    result = backtester.run(symbol, days=args.days)
    comparison = compare_live_to_backtester(exchange, symbol, args.days, args.balance, args.compare_candles)

    output = {
        "backtest": {
            "starting_balance": result.starting_balance,
            "ending_balance": result.ending_balance,
            "total_return_pct": result.total_return_pct,
            "trades": len(result.trades),
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "max_drawdown_pct": result.max_drawdown_pct,
            "signals_generated": result.signals_generated,
            "skipped_signals": result.skipped_signals,
        },
        "live_parity": {
            "compared_candles": comparison["compared_candles"],
            "matches": comparison["matches"],
            "mismatch_count": len(comparison["mismatches"]),
            "mismatches": comparison["mismatches"],
        },
    }
    if not args.summary_only:
        output["live_parity"]["rows"] = comparison["rows"]

    if args.write_redis:
        if redis is not None and real_redis_from_url is not None:
            try:
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                client = real_redis_from_url(redis_url, decode_responses=True)
                client.set("live_parity:latest", json.dumps(output, ensure_ascii=False))
                print(f"[INFO] Successfully wrote live parity report to Redis key 'live_parity:latest'")
            except Exception as e:
                print(f"[WARNING] Failed to write live parity report to Redis: {e}", file=sys.stderr)
        else:
            print("[WARNING] Redis module not available, cannot write live parity report", file=sys.stderr)

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
