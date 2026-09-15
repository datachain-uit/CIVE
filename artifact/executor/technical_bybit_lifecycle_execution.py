"""4H execution for a delisting-aware Bybit point-in-time liquidity universe."""
from __future__ import annotations

import argparse
import json
import math
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from technical_bybit_lifecycle_universe import API_ROOT, DAY_MS, _atomic_json, _request
from technical_cross_asset_execution import FOUR_H_MS, _atr, _bybit_funding_history
from technical_cross_asset_research import CHANNEL_EVENT
from technical_execution_semantics import (
    EVENT_ORDER,
    EXECUTION_SEMANTICS,
    funding_payment,
    long_stop_transition,
)
from technical_experiment_manifest import build_experiment_manifest, write_manifest
from technical_rule_research import _long_exit, _long_signal


def _long_stop_fill(
    row: list[float], position: dict, trail_atr: float,
) -> tuple[float | None, float]:
    """Evaluate a long stop without using the current bar's future high.

    The trailing level effective during this bar is derived only from the peak
    observed through the preceding bar.  A gap through that level fills at the
    adverse open; otherwise an intrabar breach fills at the stop.  The current
    high becomes eligible to tighten the stop only for the next bar.
    """
    result = long_stop_transition(row, position, trail_atr)
    return result.fill_price, result.next_peak


def _load_daily(symbol: str, cache_dir: Path) -> list[list[float]]:
    matches = sorted(cache_dir.glob(f"{symbol}_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(f"no lifecycle daily cache for {symbol}")
    return json.loads(matches[0].read_text(encoding="utf-8"))


def _intraday_rows(
    symbol: str, start_ms: int, end_ms: int, cache_dir: Path,
) -> list[list[float]]:
    cache_path = cache_dir / f"{symbol}_{start_ms}_{end_ms}.json"
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached:
                return cached
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    observations: dict[int, list[float]] = {}
    page_end = end_ms
    while page_end >= start_ms:
        payload = _request("kline", {
            "category": "linear", "symbol": symbol, "interval": "240",
            "start": start_ms, "end": page_end, "limit": 1000,
        })
        rows = payload["result"].get("list", [])
        if not rows:
            break
        timestamps = []
        for row in rows:
            timestamp = int(row[0])
            timestamps.append(timestamp)
            if start_ms <= timestamp <= end_ms:
                observations[timestamp] = [
                    timestamp, float(row[1]), float(row[2]), float(row[3]),
                    float(row[4]), float(row[5]), float(row[6]),
                ]
        oldest = min(timestamps)
        if len(rows) < 1000 or oldest <= start_ms:
            break
        page_end = oldest - 1
    ordered = [observations[timestamp] for timestamp in sorted(observations)]
    _atomic_json(cache_path, ordered)
    return ordered


def _targets(
    manifest: dict, daily: dict[str, list[list[float]]], top_n: int, rank_days: int,
    excluded_symbols: set[str] | None = None,
) -> dict[int, set[str]]:
    excluded_symbols = excluded_symbols or set()
    rows_by_time = {
        symbol: {int(row[0]): row for row in rows}
        for symbol, rows in daily.items()
    }
    index_by_time = {
        symbol: {int(row[0]): index for index, row in enumerate(rows)}
        for symbol, rows in daily.items()
    }
    closes = {symbol: [float(row[4]) for row in rows] for symbol, rows in daily.items()}
    highs = {symbol: [float(row[2]) for row in rows] for symbol, rows in daily.items()}
    lows = {symbol: [float(row[3]) for row in rows] for symbol, rows in daily.items()}
    btc = rows_by_time["BTCUSDT"]
    active: set[str] = set()
    schedule: dict[int, set[str]] = {}
    membership = {int(timestamp): set(symbols) for timestamp, symbols in manifest["daily_membership"].items()}
    for timestamp in sorted(membership):
        current_universe = {
            symbol for symbol in membership[timestamp]
            if timestamp in rows_by_time.get(symbol, {}) and symbol not in excluded_symbols
        }
        active.intersection_update(current_universe)
        regime_up = all(
            time in btc for time in (timestamp, timestamp - 7 * DAY_MS, timestamp - 14 * DAY_MS)
        ) and (
            float(btc[timestamp][4]) >= float(btc[timestamp - 7 * DAY_MS][4])
            >= float(btc[timestamp - 14 * DAY_MS][4])
        )
        if not regime_up:
            active.clear()
        else:
            surviving = set()
            for symbol in active:
                index = index_by_time[symbol][timestamp]
                if not _long_exit(CHANNEL_EVENT, closes[symbol], highs[symbol], lows[symbol], index):
                    surviving.add(symbol)
            active = surviving
            entrants = []
            for symbol in current_universe - active:
                index = index_by_time[symbol][timestamp]
                if index < max(CHANNEL_EVENT.lookback, rank_days):
                    continue
                if _long_signal(CHANNEL_EVENT, closes[symbol], highs[symbol], lows[symbol], index):
                    entrants.append(symbol)
            entrants.sort(
                key=lambda symbol: closes[symbol][index_by_time[symbol][timestamp]]
                / closes[symbol][index_by_time[symbol][timestamp] - rank_days] - 1,
                reverse=True,
            )
            active.update(entrants[:max(0, top_n - len(active))])
        schedule[timestamp + DAY_MS] = set(active)
    return schedule


def main() -> None:
    parser = argparse.ArgumentParser(description="Lifecycle-aware Bybit 4H Technical execution")
    parser.add_argument("--manifest", type=Path, default=Path("results/bybit_lifecycle_universe.json"))
    parser.add_argument("--daily-cache-dir", type=Path, default=Path("results/bybit_lifecycle_daily"))
    parser.add_argument("--four-h-cache-dir", type=Path, default=Path("results/bybit_lifecycle_4h"))
    parser.add_argument("--funding-cache-dir", type=Path, default=Path("results/bybit_lifecycle_funding"))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--top-n", type=int, default=1)
    parser.add_argument("--rank-days", type=int, default=20)
    parser.add_argument("--balance", type=float, default=10_000)
    parser.add_argument("--gross-leverage", type=float, default=1.0)
    parser.add_argument("--fee-bps", type=float, default=6.0)
    parser.add_argument("--slippage-bps", type=float, default=3.0)
    parser.add_argument("--spread-bps", type=float, default=2.0)
    parser.add_argument("--impact-bps", type=float, default=1.0)
    parser.add_argument("--stop-atr", type=float, default=2.5)
    parser.add_argument("--trail-atr", type=float, default=3.0)
    parser.add_argument("--fold-days", type=int, default=180)
    parser.add_argument("--output", type=Path, default=Path("results/technical_bybit_lifecycle_execution.json"))
    parser.add_argument("--experiment-manifest", type=Path)
    parser.add_argument(
        "--exclude-symbols", default="",
        help="Comma-separated symbols excluded from trading; market-reference data remain available.",
    )
    args = parser.parse_args()
    if args.gross_leverage <= 0:
        raise ValueError("gross-leverage must be positive")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    start_ms = int(manifest["protocol"]["start_ms"])
    end_ms = int(manifest["protocol"]["end_ms"])
    selected_metadata = {row["symbol"]: row for row in manifest["ever_selected"]}
    symbols = tuple(selected_metadata)
    daily = {symbol: _load_daily(symbol, args.daily_cache_dir) for symbol in symbols}
    excluded_symbols = {
        symbol.strip().upper() for symbol in args.exclude_symbols.split(",") if symbol.strip()
    }
    unknown_exclusions = excluded_symbols - set(symbols)
    if unknown_exclusions:
        raise ValueError(f"excluded symbols are outside the lifecycle set: {sorted(unknown_exclusions)}")
    targets = _targets(manifest, daily, args.top_n, args.rank_days, excluded_symbols)

    four_h: dict[str, list[list[float]]] = {}
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for symbol, metadata in selected_metadata.items():
            symbol_start = max(start_ms, int(metadata["launch_ms"]))
            symbol_end = min(end_ms + DAY_MS, int(metadata["delivery_ms"]) or end_ms + DAY_MS)
            futures[executor.submit(_intraday_rows, symbol, symbol_start, symbol_end, args.four_h_cache_dir)] = symbol
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                rows = future.result()
                if rows:
                    four_h[symbol] = rows
            except Exception as exc:
                failures[symbol] = str(exc)
    if failures:
        raise RuntimeError(f"4H lifecycle download failures: {failures}")

    args.funding_cache_dir.mkdir(parents=True, exist_ok=True)
    funding: dict[str, dict[int, float]] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for symbol, metadata in selected_metadata.items():
            symbol_start = max(start_ms, int(metadata["launch_ms"]))
            symbol_end = min(end_ms + DAY_MS, int(metadata["delivery_ms"]) or end_ms + DAY_MS)
            cache_path = args.funding_cache_dir / f"{symbol}_{symbol_start}_{symbol_end}.json"
            if cache_path.exists():
                funding[symbol] = {int(time): float(rate) for time, rate in json.loads(cache_path.read_text(encoding="utf-8")).items()}
            else:
                futures[executor.submit(_bybit_funding_history, symbol, symbol_start, symbol_end)] = (symbol, cache_path)
        for future in as_completed(futures):
            symbol, cache_path = futures[future]
            rates = future.result()
            funding[symbol] = rates
            _atomic_json(cache_path, rates)

    bars = {symbol: {int(row[0]): row for row in rows} for symbol, rows in four_h.items()}
    indexes = {symbol: {int(row[0]): index for index, row in enumerate(rows)} for symbol, rows in four_h.items()}
    last_time = {symbol: max(symbol_bars) for symbol, symbol_bars in bars.items()}
    ordered_times = list(range(start_ms, end_ms + DAY_MS, FOUR_H_MS))
    cash = args.balance
    positions: dict[str, dict] = {}
    desired: set[str] = set()
    trade_count = 0
    delisting_exits = 0
    applied_funding = 0
    funding_paid = 0.0
    funding_by_symbol: dict[str, float] = {}
    closed_trades: list[dict] = []
    equity_points: list[tuple[int, float]] = []
    fee_rate = args.fee_bps / 10_000
    execution_bps = args.slippage_bps + args.spread_bps / 2 + args.impact_bps
    slip_rate = execution_bps / 10_000

    def price_at(symbol: str, time: int, field: int = 4) -> float:
        row = bars[symbol].get(time)
        if row is not None:
            return float(row[field])
        prior = max((timestamp for timestamp in bars[symbol] if timestamp < time), default=None)
        if prior is None:
            raise RuntimeError(f"no price at or before {time} for {symbol}")
        return float(bars[symbol][prior][4])

    def equity(time: int) -> float:
        return cash + sum(position["qty"] * price_at(symbol, time) for symbol, position in positions.items())

    def close(symbol: str, raw_price: float, reason: str) -> None:
        nonlocal cash, trade_count
        position = positions.pop(symbol)
        price = raw_price * (1 - slip_rate)
        exit_fee = position["qty"] * price * fee_rate
        cash += position["qty"] * price - exit_fee
        gross_price_pnl = position["qty"] * (raw_price - position["raw_entry"])
        execution_cost = position["qty"] * (
            (position["entry"] - position["raw_entry"]) + (raw_price - price)
        )
        fees = position["entry_fee"] + exit_fee
        symbol_funding = position["funding_paid"]
        net_pnl = gross_price_pnl - execution_cost - fees - symbol_funding
        closed_trades.append({
            "symbol": symbol, "entry_time": position["entry_time"],
            "exit_time": current_time, "reason": reason,
            "gross_price_pnl": round(gross_price_pnl, 8),
            "execution_cost": round(execution_cost, 8),
            "fees": round(fees, 8), "funding_paid": round(symbol_funding, 8),
            "net_pnl": round(net_pnl, 8),
        })
        trade_count += 1

    for time in ordered_times:
        current_time = time
        # A delisted contract has no next bar; exit at its final observable close.
        for symbol in list(positions):
            if time > last_time[symbol]:
                close(symbol, float(bars[symbol][last_time[symbol]][4]), "delisting")
                delisting_exits += 1

        # A target decided from the preceding closed daily candle is acted on
        # at this bar's open before any high/low from this bar is observable.
        if time in targets:
            desired = targets[time]
            for symbol in list(positions):
                if symbol not in desired:
                    close(symbol, price_at(symbol, time, 1), "rebalance")
            portfolio_equity = equity(time)
            allocation = portfolio_equity * args.gross_leverage / max(1, len(desired))
            for symbol in desired:
                if symbol in positions or time not in bars.get(symbol, {}):
                    continue
                index = indexes[symbol][time]
                current_atr = _atr(four_h[symbol], index)
                if current_atr is None:
                    continue
                raw_entry = float(bars[symbol][time][1])
                entry = raw_entry * (1 + slip_rate)
                quantity = allocation / entry
                cost = quantity * entry * (1 + fee_rate)
                if args.gross_leverage <= 1 and cost > cash:
                    quantity = cash / (entry * (1 + fee_rate))
                    cost = quantity * entry * (1 + fee_rate)
                cash -= cost
                positions[symbol] = {
                    "qty": quantity, "atr": current_atr, "peak": entry,
                    "stop": entry - args.stop_atr * current_atr,
                    "raw_entry": raw_entry, "entry": entry,
                    "entry_fee": quantity * entry * fee_rate,
                    "entry_time": time, "funding_paid": 0.0,
                }
                trade_count += 1

        # Funding is settled for the portfolio held at this timestamp.  It is
        # deliberately processed before intrabar stops, whose exact path after
        # the timestamp is unknown in OHLC data.
        for symbol, position in positions.items():
            rate = funding.get(symbol, {}).get(time)
            if rate is not None:
                payment = funding_payment(position["qty"], price_at(symbol, time), rate)
                cash -= payment
                position["funding_paid"] += payment
                funding_paid += payment
                funding_by_symbol[symbol] = funding_by_symbol.get(symbol, 0.0) + payment
                applied_funding += 1

        # Only now may this bar's high/low affect risk.  A surviving high can
        # tighten the trailing level for the following bar, never retroactively
        # for the current bar.
        for symbol in list(positions):
            row = bars[symbol].get(time)
            if row is None:
                continue
            position = positions[symbol]
            stop_fill, next_peak = _long_stop_fill(row, position, args.trail_atr)
            if stop_fill is not None:
                close(symbol, stop_fill, "stop")
            else:
                position["peak"] = next_peak
        equity_points.append((time, equity(time)))
    for symbol in list(positions):
        current_time = ordered_times[-1]
        close(symbol, price_at(symbol, ordered_times[-1]), "end_of_test")
    final_equity = cash
    equity_points[-1] = (equity_points[-1][0], final_equity)
    peak = args.balance
    max_drawdown = 0.0
    for _, value in equity_points:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, 1 - value / peak)
    fold_ms = args.fold_days * DAY_MS
    folds = []
    for fold_start in range(equity_points[0][0], equity_points[-1][0], fold_ms):
        fold_points = [
            (time, value) for time, value in equity_points
            if fold_start <= time < fold_start + fold_ms
        ]
        # Report only complete OOS windows; a short calendar tail is not a fold.
        if len(fold_points) < 2 or fold_points[-1][0] < fold_start + fold_ms - FOUR_H_MS:
            continue
        values = [value for _, value in fold_points]
        fold_peak = values[0]
        fold_drawdown = 0.0
        for value in values:
            fold_peak = max(fold_peak, value)
            fold_drawdown = max(fold_drawdown, 1 - value / fold_peak)
        folds.append({
            "start": datetime.fromtimestamp(fold_start / 1000, tz=timezone.utc).date().isoformat(),
            "return_pct": round((values[-1] / values[0] - 1) * 100, 4),
            "max_drawdown_pct": round(fold_drawdown * 100, 4),
        })
    daily_equity: list[list[float]] = []
    for timestamp, value in equity_points:
        day = timestamp - timestamp % DAY_MS
        if daily_equity and daily_equity[-1][0] == day:
            daily_equity[-1][1] = value
        else:
            daily_equity.append([day, value])
    daily_returns = [
        [daily_equity[index][0], daily_equity[index][1] / daily_equity[index - 1][1] - 1]
        for index in range(1, len(daily_equity))
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "execution_semantics": EXECUTION_SEMANTICS,
            "event_order": " -> ".join(EVENT_ORDER),
            "stop_fill": "long gap fills at adverse open; otherwise at active stop",
            "trailing_semantics": "current-bar high tightens stop from the next bar",
            "universe": "Bybit Trading + Closed USDT perpetual lifecycle manifest",
            "instruments_scanned": manifest["instruments_with_daily_data"],
            "ever_top_liquidity": len(symbols), "delisted_ever_top": manifest["delisted_ever_selected"],
            "top_n": args.top_n, "rank_days": args.rank_days, "gross_leverage": args.gross_leverage,
            "excluded_symbols": sorted(excluded_symbols),
            "stop_atr": args.stop_atr, "trail_atr": args.trail_atr,
            "fee_bps": args.fee_bps, "effective_adverse_execution_bps": execution_bps,
            "funding_source": "Bybit history", "delisting_exit": "last observable 4H close with exit costs",
        },
        "result": {
            "starting_balance": args.balance, "final_equity": round(final_equity, 2),
            "return_pct": round((final_equity / args.balance - 1) * 100, 4),
            "max_drawdown_pct": round(max_drawdown * 100, 4), "fills": trade_count,
        },
        "walk_forward_folds": folds,
        "positive_folds": sum(fold["return_pct"] > 0 for fold in folds),
        "folds_tested": len(folds), "applied_funding_events": applied_funding,
        "delisting_exits": delisting_exits, "four_h_download_failures": failures,
        "pnl_decomposition": {
            "gross_price_pnl": round(sum(t["gross_price_pnl"] for t in closed_trades), 6),
            "execution_cost": round(sum(t["execution_cost"] for t in closed_trades), 6),
            "fees": round(sum(t["fees"] for t in closed_trades), 6),
            "funding_paid": round(funding_paid, 6),
            "net_pnl": round(sum(t["net_pnl"] for t in closed_trades), 6),
            "equity_change": round(final_equity - args.balance, 6),
            "reconciliation_error": round(
                sum(t["net_pnl"] for t in closed_trades) - (final_equity - args.balance), 8
            ),
        },
        "symbol_contribution": {
            symbol: round(sum(t["net_pnl"] for t in closed_trades if t["symbol"] == symbol), 6)
            for symbol in sorted({t["symbol"] for t in closed_trades})
        },
        "exit_reasons": {
            reason: sum(t["reason"] == reason for t in closed_trades)
            for reason in sorted({t["reason"] for t in closed_trades})
        },
        "closed_trades": closed_trades,
        "daily_returns": daily_returns,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(args.output, payload)
    experiment_manifest = args.experiment_manifest or args.output.with_suffix(".manifest.json")
    data_paths = [args.manifest]
    data_paths.extend(
        max(args.daily_cache_dir.glob(f"{symbol}_*.json"), key=lambda path: path.stat().st_mtime)
        for symbol in symbols
    )
    data_paths.extend(
        args.four_h_cache_dir / f"{symbol}_{max(start_ms, int(metadata['launch_ms']))}_{min(end_ms + DAY_MS, int(metadata['delivery_ms']) or end_ms + DAY_MS)}.json"
        for symbol, metadata in selected_metadata.items()
    )
    data_paths.extend(
        args.funding_cache_dir / f"{symbol}_{max(start_ms, int(metadata['launch_ms']))}_{min(end_ms + DAY_MS, int(metadata['delivery_ms']) or end_ms + DAY_MS)}.json"
        for symbol, metadata in selected_metadata.items()
    )
    configuration = {
        key: value for key, value in vars(args).items()
        if key not in {"output", "experiment_manifest"}
    }
    configuration = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in configuration.items()
    }
    write_manifest(experiment_manifest, build_experiment_manifest(
        repo_root=Path(__file__).resolve().parents[1],
        result_path=args.output,
        configuration=configuration,
        data_paths=data_paths,
        source_paths=[
            Path(__file__), Path(long_stop_transition.__code__.co_filename),
            Path(build_experiment_manifest.__code__.co_filename),
            Path(__file__).with_name("technical_bybit_lifecycle_universe.py"),
            Path(__file__).with_name("technical_cross_asset_execution.py"),
            Path(__file__).with_name("technical_cross_asset_research.py"),
            Path(__file__).with_name("technical_rule_research.py"),
        ],
        execution_semantics=EXECUTION_SEMANTICS,
        event_order=EVENT_ORDER,
    ))
    payload["experiment_manifest"] = str(experiment_manifest)
    print(json.dumps(payload, indent=2), flush=True)


if __name__ == "__main__":
    main()
