"""Build a delisting-aware, point-in-time Bybit USDT-perpetual liquidity universe."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DAY_MS = 86_400_000
API_ROOT = "https://api.bybit.com/v5/market"


def _request(endpoint: str, params: dict, attempts: int = 5) -> dict:
    request = Request(
        f"{API_ROOT}/{endpoint}?{urlencode(params)}",
        headers={"User-Agent": "auto-trading-research/1.0", "Accept": "application/json"},
    )
    error = None
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("retCode") == 0:
                return payload
            error = RuntimeError(payload.get("retMsg") or f"retCode={payload.get('retCode')}")
        except Exception as exc:  # network/API retry boundary
            error = exc
        time.sleep(min(8, 0.5 * 2**attempt))
    raise RuntimeError(f"Bybit {endpoint} failed after {attempts} attempts: {error}")


def _atomic_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, path)


def _instruments(start_ms: int, end_ms: int) -> list[dict]:
    selected: dict[str, dict] = {}
    for status in ("Trading", "Closed"):
        payload = _request("instruments-info", {"category": "linear", "status": status, "limit": 1000})
        for row in payload["result"]["list"]:
            launch = int(row.get("launchTime") or 0)
            delivery = int(row.get("deliveryTime") or 0)
            if (
                row.get("contractType") == "LinearPerpetual"
                and row.get("quoteCoin") == "USDT"
                and launch <= end_ms
                and (delivery == 0 or delivery >= start_ms)
            ):
                selected[row["symbol"]] = {
                    "symbol": row["symbol"], "status": row["status"],
                    "launch_ms": launch, "delivery_ms": delivery,
                }
    return sorted(selected.values(), key=lambda row: row["symbol"])


def _daily_rows(instrument: dict, start_ms: int, end_ms: int, cache_dir: Path) -> list[list[float]]:
    symbol = instrument["symbol"]
    effective_start = max(start_ms, instrument["launch_ms"])
    effective_end = min(end_ms, instrument["delivery_ms"] or end_ms)
    cache_path = cache_dir / f"{symbol}_{effective_start}_{effective_end}.json"
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached:
                return cached
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    observations: dict[int, list[float]] = {}
    page_end = effective_end
    while page_end >= effective_start:
        payload = _request("kline", {
            "category": "linear", "symbol": symbol, "interval": "D",
            "start": effective_start, "end": page_end, "limit": 1000,
        })
        rows = payload["result"].get("list", [])
        if not rows:
            break
        timestamps = []
        for row in rows:
            timestamp = int(row[0])
            timestamps.append(timestamp)
            if effective_start <= timestamp <= effective_end:
                observations[timestamp] = [
                    timestamp, float(row[1]), float(row[2]), float(row[3]),
                    float(row[4]), float(row[5]), float(row[6]),
                ]
        oldest = min(timestamps)
        if len(rows) < 1000 or oldest <= effective_start:
            break
        page_end = oldest - 1
    ordered = [observations[timestamp] for timestamp in sorted(observations)]
    _atomic_json(cache_path, ordered)
    return ordered


def _membership(
    data: dict[str, list[list[float]]], start_ms: int, end_ms: int,
    lookback_days: int, universe_size: int,
) -> tuple[dict[int, list[str]], Counter]:
    by_symbol = {symbol: {int(row[0]): row for row in rows} for symbol, rows in data.items()}
    schedule: dict[int, list[str]] = {}
    counts: Counter[str] = Counter()
    for timestamp in range(start_ms, end_ms + 1, DAY_MS):
        liquidity = {}
        window = [timestamp - offset * DAY_MS for offset in range(lookback_days - 1, -1, -1)]
        for symbol, rows in by_symbol.items():
            history = [rows.get(day) for day in window]
            if any(row is None for row in history):
                continue
            liquidity[symbol] = sum(float(row[6]) for row in history)
        selected = sorted(liquidity, key=lambda symbol: (-liquidity[symbol], symbol))[:universe_size]
        schedule[timestamp] = selected
        counts.update(selected)
    return schedule, counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Build point-in-time Bybit lifecycle universe")
    parser.add_argument("--days", type=int, default=1460)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--universe-size", type=int, default=5)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--cache-dir", type=Path, default=Path("results/bybit_lifecycle_daily"))
    parser.add_argument("--output", type=Path, default=Path("results/bybit_lifecycle_universe.json"))
    args = parser.parse_args()
    if args.days < args.lookback_days + 2:
        raise ValueError("days must exceed the liquidity lookback")
    if not 1 <= args.workers <= 12:
        raise ValueError("workers must be in [1, 12]")
    today = datetime.now(timezone.utc).date()
    end_ms = int(datetime(today.year, today.month, today.day, tzinfo=timezone.utc).timestamp() * 1000) - DAY_MS
    start_ms = end_ms - (args.days - 1) * DAY_MS
    instruments = _instruments(start_ms, end_ms)
    data: dict[str, list[list[float]]] = {}
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(_daily_rows, instrument, start_ms, end_ms, args.cache_dir): instrument
            for instrument in instruments
        }
        for number, future in enumerate(as_completed(futures), 1):
            instrument = futures[future]
            try:
                rows = future.result()
                if rows:
                    data[instrument["symbol"]] = rows
            except Exception as exc:
                failures[instrument["symbol"]] = str(exc)
            if number % 50 == 0 or number == len(futures):
                print(f"daily {number}/{len(futures)}; usable={len(data)}; failures={len(failures)}", flush=True)
    schedule, counts = _membership(data, start_ms, end_ms, args.lookback_days, args.universe_size)
    metadata = {row["symbol"]: row for row in instruments}
    ever_selected = sorted(counts, key=lambda symbol: (-counts[symbol], symbol))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "venue": "Bybit", "category": "linear USDT perpetual",
            "statuses": ["Trading", "Closed"], "start_ms": start_ms, "end_ms": end_ms,
            "lookback_days": args.lookback_days, "universe_size": args.universe_size,
            "liquidity_measure": "sum of exchange-reported daily turnover",
            "minimum_history": f"{args.lookback_days} consecutive daily candles",
        },
        "instruments_intersecting_window": len(instruments),
        "instruments_with_daily_data": len(data),
        "download_failures": failures,
        "ever_selected": [
            {**metadata[symbol], "membership_days": counts[symbol], "daily_rows": len(data[symbol])}
            for symbol in ever_selected
        ],
        "delisted_ever_selected": sum(metadata[symbol]["status"] == "Closed" for symbol in ever_selected),
        "daily_membership": {str(timestamp): symbols for timestamp, symbols in schedule.items()},
        "membership_days_median": statistics.median(counts.values()) if counts else 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(args.output, payload)
    print(json.dumps({
        "intersecting": len(instruments), "with_data": len(data), "failures": len(failures),
        "ever_selected": len(ever_selected), "delisted_ever_selected": payload["delisted_ever_selected"],
        "top_membership": payload["ever_selected"][:20], "output": str(args.output),
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
