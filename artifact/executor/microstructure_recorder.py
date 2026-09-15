"""Point-in-time L2/order-flow recorder for future microstructure research.

Run explicitly during a paper-trading window.  It never sends an order and it
never starts itself from the live executor.  Historical OHLCV cannot recreate
this data without look-ahead, so only these recorded observations are valid
for an order-flow backtest.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from backtester import build_exchange, normalize_derivative_symbol


def _snapshot(exchange, symbol: str, levels: int, trade_since: int | None) -> tuple[dict, int | None]:
    book = exchange.fetch_order_book(symbol, limit=levels)
    bids, asks = book.get("bids", [])[:levels], book.get("asks", [])[:levels]
    if not bids or not asks:
        raise RuntimeError(f"empty book for {symbol}")
    bid_depth = sum(float(price) * float(size) for price, size in bids)
    ask_depth = sum(float(price) * float(size) for price, size in asks)
    mid = (float(bids[0][0]) + float(asks[0][0])) / 2
    trades = exchange.fetch_trades(symbol, since=trade_since, limit=1000)
    buy_notional = sum(float(t.get("amount", 0)) * float(t.get("price", 0)) for t in trades if t.get("side") == "buy")
    sell_notional = sum(float(t.get("amount", 0)) * float(t.get("price", 0)) for t in trades if t.get("side") == "sell")
    latest_trade_ts = max((int(t["timestamp"]) for t in trades if t.get("timestamp")), default=trade_since)
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    return {
        "timestamp_ms": timestamp,
        "symbol": symbol,
        "best_bid": float(bids[0][0]),
        "best_ask": float(asks[0][0]),
        "mid": mid,
        "spread_bps": (float(asks[0][0]) / float(bids[0][0]) - 1) * 10_000,
        "bid_depth_notional": bid_depth,
        "ask_depth_notional": ask_depth,
        "book_imbalance": (bid_depth - ask_depth) / (bid_depth + ask_depth) if bid_depth + ask_depth else 0.0,
        "taker_buy_notional": buy_notional,
        "taker_sell_notional": sell_notional,
        "taker_imbalance": (buy_notional - sell_notional) / (buy_notional + sell_notional) if buy_notional + sell_notional else 0.0,
        "levels": levels,
    }, latest_trade_ts


def main() -> None:
    parser = argparse.ArgumentParser(description="Record L2 book and taker-flow snapshots; never trades")
    parser.add_argument("--symbols", default="BTC/USDT,ETH/USDT,XRP/USDT,SOL/USDT,BNB/USDT")
    parser.add_argument("--exchange", default="binanceusdm")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--duration-minutes", type=int, default=60)
    parser.add_argument("--levels", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("data/microstructure/orderflow_l2.jsonl"))
    args = parser.parse_args()
    if min(args.interval_seconds, args.duration_minutes, args.levels) <= 0:
        raise ValueError("interval, duration and levels must be positive")
    exchange = build_exchange(args.exchange)
    symbols = [normalize_derivative_symbol(exchange, raw.strip()) for raw in args.symbols.split(",") if raw.strip()]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.duration_minutes * 60
    trade_since: dict[str, int | None] = {symbol: None for symbol in symbols}
    print(f"Recording {len(symbols)} symbols for {args.duration_minutes} minutes to {args.output}")
    with args.output.open("a", encoding="utf-8") as stream:
        while time.monotonic() < deadline:
            cycle_start = time.monotonic()
            for symbol in symbols:
                try:
                    record, trade_since[symbol] = _snapshot(exchange, symbol, args.levels, trade_since[symbol])
                    stream.write(json.dumps(record, separators=(",", ":")) + "\n")
                    stream.flush()
                except Exception as exc:
                    print(f"[WARN] {symbol}: {exc}")
            remaining = args.interval_seconds - (time.monotonic() - cycle_start)
            if remaining > 0:
                time.sleep(remaining)


if __name__ == "__main__":
    main()
