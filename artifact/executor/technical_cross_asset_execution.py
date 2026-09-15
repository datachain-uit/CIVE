"""4H execution simulation for the locked cross-asset Technical candidate.

Daily selection is causal: a signal at the close of day D may first trade at
the open of day D+1.  This runner is deliberately separate from live trading.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backtester import build_exchange, fetch_ohlcv_with_retry, normalize_derivative_symbol
from technical_cross_asset_research import CHANNEL_EVENT, _closed_rows
from technical_rule_research import RuleSpec, _long_exit, _long_signal

DAY_MS = 86_400_000
FOUR_H_MS = 14_400_000


def _point_in_time_liquid_universe(
    quote_volumes: dict[str, list[float]],
    index: int,
    lookback_days: int,
    universe_size: int,
) -> set[str]:
    """Rank only closed observations ending at ``index``; never use future volume."""
    liquidity = {
        symbol: sum(values[index - lookback_days + 1:index + 1])
        for symbol, values in quote_volumes.items()
    }
    return set(sorted(liquidity, key=lambda symbol: (-liquidity[symbol], symbol))[:universe_size])


def _atr(rows: list[list[float]], i: int, period: int = 14) -> float | None:
    if i < period:
        return None
    ranges = []
    for t in range(i - period + 1, i + 1):
        high, low = float(rows[t][2]), float(rows[t][3])
        previous_close = float(rows[t - 1][4])
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return sum(ranges) / len(ranges)


def _oscillator_values(
    closes: list[float], highs: list[float], lows: list[float], index: int,
) -> tuple[float, float, float] | None:
    """Causal RSI(14), stochastic %K(14), and CCI(20) trend signals."""
    if index < 20:
        return None
    changes = [closes[t] - closes[t - 1] for t in range(index - 13, index + 1)]
    gains = sum(max(change, 0.0) for change in changes) / 14
    losses = sum(max(-change, 0.0) for change in changes) / 14
    rsi = 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)
    high14 = max(highs[index - 13:index + 1])
    low14 = min(lows[index - 13:index + 1])
    stochastic = 50.0 if high14 == low14 else 100 * (closes[index] - low14) / (high14 - low14)
    typical = [(highs[t] + lows[t] + closes[t]) / 3 for t in range(index - 19, index + 1)]
    mean_typical = sum(typical) / len(typical)
    mean_deviation = sum(abs(value - mean_typical) for value in typical) / len(typical)
    cci = 0.0 if mean_deviation == 0 else (typical[-1] - mean_typical) / (0.015 * mean_deviation)
    return rsi, stochastic, cci


def _oscillator_ensemble_ranks(
    symbols: set[str], closes: dict[str, list[float]], highs: dict[str, list[float]],
    lows: dict[str, list[float]], index: int,
) -> dict[str, float]:
    values = {
        symbol: _oscillator_values(closes[symbol], highs[symbol], lows[symbol], index)
        for symbol in symbols
    }
    values = {symbol: value for symbol, value in values.items() if value is not None}
    scores = {symbol: 0.0 for symbol in values}
    for feature in range(3):
        ordered = sorted(values, key=lambda symbol: (values[symbol][feature], symbol), reverse=True)
        for rank, symbol in enumerate(ordered):
            scores[symbol] += rank
    return scores


def _amihud_shock_ratios(
    closes: dict[str, list[float]], quote_volumes: dict[str, list[float]],
    symbols: set[str], index: int, lookback_days: int,
) -> dict[str, float]:
    """Current closed-day Amihud illiquidity divided by its trailing median."""
    ratios: dict[str, float] = {}
    for symbol in symbols:
        series = []
        for t in range(index - lookback_days, index):
            if t < 1:
                continue
            daily_return = abs(closes[symbol][t] / closes[symbol][t - 1] - 1)
            series.append(daily_return / max(quote_volumes[symbol][t], 1e-12))
        if not series:
            continue
        current_return = abs(closes[symbol][index] / closes[symbol][index - 1] - 1)
        current = current_return / max(quote_volumes[symbol][index], 1e-12)
        baseline = statistics.median(series)
        ratios[symbol] = current / max(baseline, 1e-18)
    return ratios


def _daily_targets(
    data: dict[str, list[list[float]]],
    market: list[float],
    top_n: int,
    rank_days: int,
    volume_veto: str = "off",
    oi_gate: str = "off",
    oi_history: dict[str, dict[int, float]] | None = None,
    funding_crowding_veto: str = "off",
    funding_history: dict[str, dict[int, float]] | None = None,
    basis_gate: str = "off",
    bybit_basis_history: dict[str, dict[int, float]] | None = None,
    okx_basis_history: dict[str, dict[int, float]] | None = None,
    flow_mode: str = "off",
    flow_history: dict[str, dict[int, float]] | None = None,
    universe_mode: str = "fixed",
    liquidity_universe_size: int = 5,
    liquidity_lookback_days: int = 30,
    event: RuleSpec = CHANNEL_EVENT,
    rank_mode: str = "momentum",
    selection_mode: str = "breakout",
    rebalance_days: int = 7,
    market_regime_gate: bool = True,
    liquidity_shock_gate: str = "off",
    liquidity_shock_lookback: int = 60,
    liquidity_shock_threshold: float = 3.0,
) -> tuple[dict[int, set[str]], dict[str, int]]:
    closes = {s: [float(r[4]) for r in rows] for s, rows in data.items()}
    highs = {s: [float(r[2]) for r in rows] for s, rows in data.items()}
    lows = {s: [float(r[3]) for r in rows] for s, rows in data.items()}
    volumes = {s: [float(r[5]) for r in rows] for s, rows in data.items()}
    quote_volumes = {
        s: [float(row[5]) * float(row[4]) for row in rows]
        for s, rows in data.items()
    }
    active: set[str] = set()
    schedule: dict[int, set[str]] = {}
    oi_history = oi_history or {}
    funding_history = funding_history or {}
    bybit_basis_history = bybit_basis_history or {}
    okx_basis_history = okx_basis_history or {}
    flow_history = flow_history or {}
    oi_times = {symbol: sorted(history) for symbol, history in oi_history.items()}
    funding_times = {symbol: sorted(history) for symbol, history in funding_history.items()}
    bybit_basis_times = {symbol: sorted(history) for symbol, history in bybit_basis_history.items()}
    okx_basis_times = {symbol: sorted(history) for symbol, history in okx_basis_history.items()}
    flow_times = {symbol: sorted(history) for symbol, history in flow_history.items()}
    universe_membership_days = {symbol: 0 for symbol in data}

    def latest_at_or_before(history: dict[int, float], times: list[int], timestamp: int) -> float | None:
        position = bisect.bisect_right(times, timestamp) - 1
        return history[times[position]] if position >= 0 else None

    warmup = max(
        30 if volume_veto != "off" else 20,
        rank_days,
        event.lookback,
        liquidity_lookback_days if universe_mode == "point-in-time-liquidity" else 0,
        liquidity_shock_lookback if liquidity_shock_gate != "off" else 0,
    )
    for i in range(warmup, len(market) - 1):
        if universe_mode == "point-in-time-liquidity":
            current_universe = _point_in_time_liquid_universe(
                quote_volumes, i, liquidity_lookback_days, liquidity_universe_size,
            )
        else:
            current_universe = set(data)
        for symbol in current_universe:
            universe_membership_days[symbol] += 1
        active.intersection_update(current_universe)
        regime_up = market[i] >= market[i - 7] >= market[i - 14]
        if selection_mode == "weekly-oscillator":
            if market_regime_gate and not regime_up:
                active.clear()
            elif (i - warmup) % rebalance_days == 0:
                oscillator_scores = _oscillator_ensemble_ranks(
                    current_universe, closes, highs, lows, i,
                )
                active = set(sorted(
                    current_universe,
                    key=lambda symbol: (oscillator_scores.get(symbol, math.inf), symbol),
                )[:top_n])
            schedule[int(next(iter(data.values()))[i][0]) + DAY_MS] = set(active)
            continue
        if market_regime_gate and not regime_up:
            active.clear()
        else:
            active = {s for s in active if not _long_exit(event, closes[s], highs[s], lows[s], i)}
            entrants = [
                s for s in current_universe
                if s not in active and _long_signal(event, closes[s], highs[s], lows[s], i)
            ]
            if liquidity_shock_gate != "off" and entrants:
                shock_ratios = _amihud_shock_ratios(
                    closes, quote_volumes, current_universe, i, liquidity_shock_lookback,
                )
                if liquidity_shock_gate in {"asset-veto", "combined-veto"}:
                    entrants = [
                        symbol for symbol in entrants
                        if shock_ratios.get(symbol, math.inf) <= liquidity_shock_threshold
                    ]
                if liquidity_shock_gate in {"market-veto", "combined-veto"}:
                    market_shock = statistics.median(shock_ratios.values()) if shock_ratios else math.inf
                    if market_shock > liquidity_shock_threshold:
                        entrants = []
            if volume_veto == "top-quintile" and entrants:
                disagree = {}
                for symbol in current_universe:
                    history = volumes[symbol][i - 30:i]
                    mean = sum(history) / len(history)
                    variance = sum((value - mean) ** 2 for value in history) / len(history)
                    disagree[symbol] = (volumes[symbol][i] - mean) / max(math.sqrt(variance), 1e-12)
                veto_count = max(1, math.ceil(len(current_universe) * 0.20))
                vetoed = set(sorted(current_universe, key=lambda symbol: disagree[symbol], reverse=True)[:veto_count])
                entrants = [symbol for symbol in entrants if symbol not in vetoed]
            decision_time = int(next(iter(data.values()))[i][0]) + DAY_MS
            flow_values: dict[str, float] = {}
            if flow_mode != "off" and entrants:
                for symbol in data:
                    value = latest_at_or_before(
                        flow_history.get(symbol, {}), flow_times.get(symbol, []), decision_time,
                    )
                    if value is not None:
                        flow_values[symbol] = value
                if flow_mode == "positive-confirmation":
                    entrants = [symbol for symbol in entrants if flow_values.get(symbol, -math.inf) > 0]
                elif flow_mode == "divergence-veto":
                    entrants = [
                        symbol for symbol in entrants
                        if not (closes[symbol][i] > closes[symbol][i - 1] and flow_values.get(symbol, -math.inf) < 0)
                    ]
            if basis_gate != "off" and entrants:
                venue_values: dict[str, dict[str, float]] = {}
                if basis_gate in {"bybit-high-tercile", "consensus-high-tercile"}:
                    venue_values["bybit"] = {}
                    for symbol in data:
                        value = latest_at_or_before(
                            bybit_basis_history.get(symbol, {}),
                            bybit_basis_times.get(symbol, []), decision_time,
                        )
                        if value is not None:
                            venue_values["bybit"][symbol] = value
                if basis_gate in {"okx-high-tercile", "consensus-high-tercile"}:
                    venue_values["okx"] = {}
                    for symbol in data:
                        value = latest_at_or_before(
                            okx_basis_history.get(symbol, {}),
                            okx_basis_times.get(symbol, []), decision_time,
                        )
                        if value is not None:
                            venue_values["okx"][symbol] = value
                eligible_symbols = set(current_universe)
                for values in venue_values.values():
                    eligible_symbols &= set(values)
                if eligible_symbols:
                    # The paper's basis is spot minus futures, so a lower
                    # perpetual premium is a higher paper-basis observation.
                    # Average ordinal ranks prevent venue scale differences
                    # from dominating the cross-exchange consensus.
                    ranks = {symbol: 0.0 for symbol in eligible_symbols}
                    for values in venue_values.values():
                        ordered = sorted(eligible_symbols, key=lambda symbol: values[symbol])
                        for rank, symbol in enumerate(ordered):
                            ranks[symbol] += rank
                    high_count = max(1, math.ceil(len(current_universe) / 3))
                    high_basis = set(sorted(eligible_symbols, key=lambda symbol: ranks[symbol])[:high_count])
                    entrants = [symbol for symbol in entrants if symbol in high_basis]
                else:
                    entrants = []
            if oi_gate == "rising-7d" and entrants:
                confirmed = []
                for symbol in entrants:
                    history = oi_history.get(symbol, {})
                    times = oi_times.get(symbol, [])
                    current = latest_at_or_before(history, times, decision_time)
                    previous = latest_at_or_before(history, times, decision_time - 7 * DAY_MS)
                    if current is not None and previous is not None and current > previous:
                        confirmed.append(symbol)
                entrants = confirmed
            if funding_crowding_veto == "top-positive-3d" and entrants:
                crowding = {}
                window_start = decision_time - 3 * DAY_MS
                for symbol in current_universe:
                    history = funding_history.get(symbol, {})
                    times = funding_times.get(symbol, [])
                    left = bisect.bisect_right(times, window_start)
                    right = bisect.bisect_right(times, decision_time)
                    crowding[symbol] = sum(history[timestamp] for timestamp in times[left:right])
                most_crowded = max(crowding, key=crowding.get)
                if crowding[most_crowded] > 0:
                    entrants = [symbol for symbol in entrants if symbol != most_crowded]
            if flow_mode == "momentum-flow-rank" and entrants:
                available = [symbol for symbol in current_universe if symbol in flow_values]
                momentum_order = sorted(
                    available, key=lambda symbol: closes[symbol][i] / closes[symbol][i - rank_days] - 1,
                    reverse=True,
                )
                flow_order = sorted(available, key=lambda symbol: flow_values[symbol], reverse=True)
                momentum_rank = {symbol: rank for rank, symbol in enumerate(momentum_order)}
                flow_rank = {symbol: rank for rank, symbol in enumerate(flow_order)}
                entrants.sort(
                    key=lambda symbol: momentum_rank.get(symbol, len(data)) + flow_rank.get(symbol, len(data))
                )
            elif rank_mode == "oscillator-ensemble":
                oscillator_scores = _oscillator_ensemble_ranks(
                    current_universe, closes, highs, lows, i,
                )
                entrants.sort(key=lambda symbol: (oscillator_scores.get(symbol, math.inf), symbol))
            else:
                entrants.sort(key=lambda s: closes[s][i] / closes[s][i - rank_days] - 1, reverse=True)
            active.update(entrants[:max(0, top_n - len(active))])
        # Decision at daily close; only next day's first 4H bar may fill.
        schedule[int(next(iter(data.values()))[i][0]) + DAY_MS] = set(active)
    return schedule, universe_membership_days


def _bybit_funding_history(symbol: str, start_ms: int, end_ms: int) -> dict[int, float]:
    """Download public settled funding rates in bounded API windows."""
    rates: dict[int, float] = {}
    cursor = start_ms
    # Funding intervals can change from 8h to 4h/2h. Therefore each bounded
    # calendar window is paged backwards by timestamp instead of assuming the
    # API's 200-row limit covers the entire window.
    window_ms = 60 * DAY_MS
    while cursor <= end_ms:
        window_end = min(cursor + window_ms - 1, end_ms)
        page_end = window_end
        while page_end >= cursor:
            params = urlencode({
                "category": "linear", "symbol": symbol.replace("/", ""),
                "startTime": cursor, "endTime": page_end, "limit": 200,
            })
            with urlopen(f"https://api.bybit.com/v5/market/funding/history?{params}", timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("retCode") != 0:
                raise RuntimeError(f"Bybit funding history failed for {symbol}: {payload.get('retMsg')}")
            rows = payload.get("result", {}).get("list", [])
            if not rows:
                break
            timestamps = []
            for row in rows:
                timestamp = int(row["fundingRateTimestamp"])
                timestamps.append(timestamp)
                rates[timestamp] = float(row["fundingRate"])
            oldest = min(timestamps)
            if len(rows) < 200 or oldest <= cursor:
                break
            page_end = oldest - 1
        cursor = window_end + 1
    return rates


def _bybit_open_interest_history(symbol: str, start_ms: int, end_ms: int) -> dict[int, float]:
    """Download public daily open-interest snapshots using cursor pagination."""
    observations: dict[int, float] = {}
    cursor = ""
    seen_cursors: set[str] = set()
    while True:
        query = {
            "category": "linear", "symbol": symbol.replace("/", ""),
            "intervalTime": "1d", "startTime": start_ms, "endTime": end_ms, "limit": 200,
        }
        if cursor:
            query["cursor"] = cursor
        with urlopen(f"https://api.bybit.com/v5/market/open-interest?{urlencode(query)}", timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("retCode") != 0:
            raise RuntimeError(f"Bybit open interest failed for {symbol}: {payload.get('retMsg')}")
        result = payload.get("result", {})
        rows = result.get("list", [])
        for row in rows:
            observations[int(row["timestamp"])] = float(row["openInterest"])
        next_cursor = result.get("nextPageCursor", "")
        if not rows or not next_cursor or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return observations


def _bybit_premium_history(symbol: str, start_ms: int, end_ms: int) -> dict[int, float]:
    """Download daily Bybit premium closes, timestamped when the candle closes."""
    observations: dict[int, float] = {}
    cursor = start_ms
    window_ms = 700 * DAY_MS
    while cursor <= end_ms:
        window_end = min(cursor + window_ms - 1, end_ms)
        params = urlencode({
            "category": "linear", "symbol": symbol.replace("/", ""),
            "interval": "D", "start": cursor, "end": window_end, "limit": 1000,
        })
        with urlopen(f"https://api.bybit.com/v5/market/premium-index-price-kline?{params}", timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("retCode") != 0:
            raise RuntimeError(f"Bybit premium history failed for {symbol}: {payload.get('retMsg')}")
        for row in payload.get("result", {}).get("list", []):
            candle_start = int(row[0])
            observations[candle_start + DAY_MS] = float(row[4])
        cursor = window_end + 1
    return observations


def _okx_history_closes(endpoint: str, instrument: str, start_ms: int, end_ms: int) -> dict[int, float]:
    """Download daily UTC OKX history backwards; values become known at close."""
    observations: dict[int, float] = {}
    page_end = end_ms + DAY_MS
    while page_end >= start_ms:
        params = urlencode({"instId": instrument, "bar": "1Dutc", "after": page_end, "limit": 100})
        request = Request(
            f"https://www.okx.com/api/v5/market/{endpoint}?{params}",
            headers={"User-Agent": "auto-trading-research/1.0", "Accept": "application/json"},
        )
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("code") != "0":
            raise RuntimeError(f"OKX {endpoint} failed for {instrument}: {payload.get('msg')}")
        rows = payload.get("data", [])
        if not rows:
            break
        timestamps = []
        for row in rows:
            candle_start = int(row[0])
            timestamps.append(candle_start)
            if start_ms <= candle_start <= end_ms:
                observations[candle_start + DAY_MS] = float(row[4])
        oldest = min(timestamps)
        if oldest <= start_ms:
            break
        page_end = oldest
    return observations


def _okx_basis_history(symbol: str, start_ms: int, end_ms: int) -> dict[int, float]:
    base = symbol.split("/")[0]
    mark = _okx_history_closes("history-mark-price-candles", f"{base}-USDT-SWAP", start_ms, end_ms)
    index = _okx_history_closes("history-index-candles", f"{base}-USDT", start_ms, end_ms)
    return {timestamp: mark[timestamp] / index[timestamp] - 1 for timestamp in mark.keys() & index.keys()}


def _binance_signed_flow_history(symbol: str, start_ms: int, end_ms: int) -> dict[int, float]:
    """Download daily USD-M klines and compute log taker-buy/taker-sell flow."""
    observations: dict[int, float] = {}
    cursor = start_ms
    while cursor <= end_ms:
        params = urlencode({
            "symbol": symbol.replace("/", ""), "interval": "1d",
            "startTime": cursor, "endTime": end_ms, "limit": 1500,
        })
        request = Request(
            f"https://fapi.binance.com/fapi/v1/klines?{params}",
            headers={"User-Agent": "auto-trading-research/1.0", "Accept": "application/json"},
        )
        with urlopen(request, timeout=20) as response:
            rows = json.loads(response.read().decode("utf-8"))
        if not rows:
            break
        for row in rows:
            candle_start = int(row[0])
            quote_volume = float(row[7])
            taker_buy_quote = float(row[10])
            taker_sell_quote = max(0.0, quote_volume - taker_buy_quote)
            observations[candle_start + DAY_MS] = math.log(
                max(taker_buy_quote, 1e-12) / max(taker_sell_quote, 1e-12)
            )
        next_cursor = int(rows[-1][0]) + DAY_MS
        if next_cursor <= cursor:
            break
        cursor = next_cursor
    return observations


def _bybit_risk_limit_tiers(symbol: str) -> list[dict[str, float]]:
    """Download the current public Bybit linear-contract risk-limit table."""
    params = urlencode({"category": "linear", "symbol": symbol.replace("/", "")})
    request = Request(
        f"https://api.bybit.com/v5/market/risk-limit?{params}",
        headers={"User-Agent": "auto-trading-research/1.0", "Accept": "application/json"},
    )
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("retCode") != 0:
        raise RuntimeError(f"Bybit risk limit failed for {symbol}: {payload.get('retMsg')}")
    tiers = [
        {
            "risk_limit_value": float(row["riskLimitValue"]),
            "maintenance_margin_rate": float(row["maintenanceMargin"]),
            "maintenance_margin_deduction": float(row.get("mmDeduction") or 0),
        }
        for row in payload.get("result", {}).get("list", [])
    ]
    if not tiers:
        raise RuntimeError(f"Bybit returned no risk-limit tiers for {symbol}")
    return sorted(tiers, key=lambda tier: tier["risk_limit_value"])


def _tiered_maintenance_margin(notional: float, tiers: list[dict[str, float]]) -> float:
    """Bybit position MM: position value * tier MMR - tier MM deduction."""
    if notional <= 0:
        return 0.0
    tier = next((item for item in tiers if notional <= item["risk_limit_value"]), None)
    if tier is None:
        raise ValueError(
            f"position notional {notional:.2f} exceeds the largest published risk tier "
            f"{tiers[-1]['risk_limit_value']:.2f}"
        )
    return max(
        0.0,
        notional * tier["maintenance_margin_rate"] - tier["maintenance_margin_deduction"],
    )


def _cached_closed_rows(
    exchange, raw_symbol: str, timeframe: str, limit: int, cache_dir: Path,
) -> list[list[float]]:
    """Freeze closed exchange bars per UTC run date for fast reproducible grids."""
    safe_symbol = raw_symbol.replace("/", "_").replace(":", "_")
    end_date = datetime.now(timezone.utc).date().isoformat()
    cache_path = cache_dir / f"{exchange.id}_{safe_symbol}_{timeframe}_{limit}_{end_date}.json"
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached:
                return cached
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    symbol = normalize_derivative_symbol(exchange, raw_symbol)
    if timeframe == "1d":
        rows = _closed_rows(exchange, symbol, limit)
    else:
        rows = fetch_ohlcv_with_retry(exchange, symbol, timeframe, limit=limit)
        timeframe_ms = FOUR_H_MS if timeframe == "4h" else exchange.parse_timeframe(timeframe) * 1000
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if rows and int(rows[-1][0]) + timeframe_ms > now_ms:
            rows = rows[:-1]
    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary_path = cache_path.with_suffix(f"{cache_path.suffix}.{os.getpid()}.tmp")
    temporary_path.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary_path, cache_path)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="4H execution simulation for cross-asset Technical portfolio")
    parser.add_argument(
        "--symbols",
        default="BTC/USDT,ETH/USDT,XRP/USDT,SOL/USDT,BNB/USDT,DOGE/USDT,ADA/USDT,AVAX/USDT,LINK/USDT,LTC/USDT",
    )
    parser.add_argument("--market-symbol", default="BTC/USDT")
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--top-n", type=int, default=1)
    parser.add_argument("--rank-days", type=int, default=20)
    parser.add_argument("--rank-mode", choices=("momentum", "oscillator-ensemble"), default="momentum")
    parser.add_argument("--selection-mode", choices=("breakout", "weekly-oscillator"), default="breakout")
    parser.add_argument("--rebalance-days", type=int, default=7)
    parser.add_argument("--market-regime", choices=("on", "off"), default="on")
    parser.add_argument("--event-family", choices=("channel", "sr"), default="channel")
    parser.add_argument("--event-lookback", type=int, default=10)
    parser.add_argument("--channel-width", type=float, default=0.10)
    parser.add_argument("--breakout-threshold", type=float, default=0.0)
    parser.add_argument(
        "--universe-mode", choices=("fixed", "point-in-time-liquidity"),
        default="point-in-time-liquidity",
    )
    parser.add_argument("--liquidity-universe-size", type=int, default=5)
    parser.add_argument("--liquidity-lookback-days", type=int, default=30)
    parser.add_argument(
        "--liquidity-shock-gate",
        choices=("off", "asset-veto", "market-veto", "combined-veto"), default="off",
    )
    parser.add_argument("--liquidity-shock-lookback", type=int, default=60)
    parser.add_argument("--liquidity-shock-threshold", type=float, default=3.0)
    parser.add_argument("--volume-veto", choices=("off", "top-quintile"), default="off")
    parser.add_argument("--oi-gate", choices=("off", "rising-7d"), default="off")
    parser.add_argument("--oi-cache-dir", type=Path, default=Path("results/open_interest_cache"))
    parser.add_argument("--funding-crowding-veto", choices=("off", "top-positive-3d"), default="off")
    parser.add_argument("--basis-gate", choices=("off", "bybit-high-tercile", "okx-high-tercile", "consensus-high-tercile"), default="off")
    parser.add_argument("--basis-cache-dir", type=Path, default=Path("results/basis_cache"))
    parser.add_argument("--flow-mode", choices=("off", "positive-confirmation", "divergence-veto", "momentum-flow-rank"), default="off")
    parser.add_argument("--flow-cache-dir", type=Path, default=Path("results/order_flow_cache"))
    parser.add_argument("--balance", type=float, default=10_000)
    parser.add_argument("--gross-leverage", type=float, default=1.0)
    parser.add_argument("--maintenance-margin-rate", type=float, default=0.01)
    parser.add_argument(
        "--margin-model", choices=("flat", "bybit-current-tiered"),
        default="bybit-current-tiered",
    )
    parser.add_argument("--risk-limit-cache-dir", type=Path, default=Path("results/risk_limit_cache"))
    parser.add_argument("--market-data-cache-dir", type=Path, default=Path("results/market_data_cache"))
    parser.add_argument("--liquidation-fee-bps", type=float, default=50.0)
    parser.add_argument("--fee-bps", type=float, default=6.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--spread-bps", type=float, default=0.0)
    parser.add_argument("--impact-bps", type=float, default=0.0)
    parser.add_argument("--funding-bps-8h", type=float, default=1.0)
    parser.add_argument("--funding-source", choices=("proxy", "bybit-history"), default="proxy")
    parser.add_argument("--funding-cache-dir", type=Path, default=Path("results/funding_cache"))
    parser.add_argument("--stop-atr", type=float, default=2.5)
    parser.add_argument("--trail-atr", type=float, default=3.0)
    parser.add_argument("--pyramid-mode", choices=("off", "winner-only"), default="off")
    parser.add_argument("--max-pyramid-layers", type=int, default=3)
    parser.add_argument("--pyramid-step-atr", type=float, default=1.0)
    parser.add_argument("--fold-days", type=int, default=180)
    parser.add_argument("--include-equity-curve", action="store_true")
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--output", type=Path, default=Path("results/technical_cross_asset_execution.json"))
    args = parser.parse_args()
    if args.gross_leverage <= 0:
        raise ValueError("gross-leverage must be positive")
    if not 0 <= args.maintenance_margin_rate < 1:
        raise ValueError("maintenance-margin-rate must be in [0, 1)")
    raw_symbols = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
    if not 1 <= args.liquidity_universe_size <= len(raw_symbols):
        raise ValueError("liquidity-universe-size must be between 1 and the candidate-pool size")
    if args.liquidity_lookback_days < 2:
        raise ValueError("liquidity-lookback-days must be at least 2")
    if args.liquidity_shock_lookback < 10:
        raise ValueError("liquidity-shock-lookback must be at least 10")
    if args.liquidity_shock_threshold <= 0:
        raise ValueError("liquidity-shock-threshold must be positive")
    if args.event_lookback < 2:
        raise ValueError("event-lookback must be at least 2")
    if args.rebalance_days < 1:
        raise ValueError("rebalance-days must be positive")
    if args.channel_width <= 0:
        raise ValueError("channel-width must be positive")
    if args.margin_model == "bybit-current-tiered" and args.exchange != "bybit":
        raise ValueError("bybit-current-tiered margin requires --exchange bybit")
    exchange = build_exchange(args.exchange)

    market_rows = _cached_closed_rows(
        exchange, args.market_symbol, "1d", args.days, args.market_data_cache_dir,
    )
    market_by_time = {int(r[0]): float(r[4]) for r in market_rows}
    daily: dict[str, list[list[float]]] = {}
    four_h: dict[str, list[list[float]]] = {}
    for raw in raw_symbols:
        daily[raw] = _cached_closed_rows(
            exchange, raw, "1d", args.days, args.market_data_cache_dir,
        )
        four_h[raw] = _cached_closed_rows(
            exchange, raw, "4h", args.days * 6 + 50, args.market_data_cache_dir,
        )
    timestamps = [int(r[0]) for r in next(iter(daily.values()))]
    if any([int(r[0]) for r in rows] != timestamps for rows in daily.values()):
        raise RuntimeError("daily universe is not aligned")
    market = [market_by_time.get(ts) for ts in timestamps]
    if any(v is None for v in market):
        raise RuntimeError("market proxy is not aligned")
    common_times = set.intersection(*(set(int(r[0]) for r in rows) for rows in four_h.values()))
    ordered_times = sorted(common_times)
    bars = {s: {int(r[0]): r for r in rows} for s, rows in four_h.items()}
    index_by_time = {s: {int(r[0]): i for i, r in enumerate(rows)} for s, rows in four_h.items()}
    cash = args.balance
    positions: dict[str, dict] = {}
    desired: set[str] = set()
    equity_curve = [cash]
    equity_points: list[tuple[int, float]] = []
    trade_count = 0
    fee_rate = args.fee_bps / 10_000
    # OHLC opens are treated as reference prices. A marketable fill pays one
    # half of the quoted spread plus adverse slippage and market impact.
    execution_bps = args.slippage_bps + args.spread_bps / 2 + args.impact_bps
    slip_rate = execution_bps / 10_000
    funding_history = {}
    if args.funding_source == "bybit-history" or args.funding_crowding_veto != "off":
        start_ms, end_ms = ordered_times[0], ordered_times[-1]
        args.funding_cache_dir.mkdir(parents=True, exist_ok=True)
        for symbol in raw_symbols:
            safe_symbol = symbol.replace("/", "_")
            cache_path = args.funding_cache_dir / f"bybit_v2_{safe_symbol}_{start_ms}_{end_ms}.json"
            if cache_path.exists():
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                funding_history[symbol] = {int(timestamp): float(rate) for timestamp, rate in cached.items()}
            else:
                rates = _bybit_funding_history(symbol, start_ms, end_ms)
                cache_path.write_text(json.dumps(rates, separators=(",", ":")), encoding="utf-8")
                funding_history[symbol] = rates
    oi_history = {}
    if args.oi_gate != "off":
        start_ms, end_ms = timestamps[0], timestamps[-1] + DAY_MS
        args.oi_cache_dir.mkdir(parents=True, exist_ok=True)
        for symbol in raw_symbols:
            safe_symbol = symbol.replace("/", "_")
            cache_path = args.oi_cache_dir / f"bybit_v1_{safe_symbol}_{start_ms}_{end_ms}.json"
            if cache_path.exists():
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                oi_history[symbol] = {int(timestamp): float(value) for timestamp, value in cached.items()}
            else:
                observations = _bybit_open_interest_history(symbol, start_ms, end_ms)
                cache_path.write_text(json.dumps(observations, separators=(",", ":")), encoding="utf-8")
                oi_history[symbol] = observations
    bybit_basis_history = {}
    okx_basis_history = {}
    if args.basis_gate != "off":
        start_ms, end_ms = timestamps[0], timestamps[-1]
        args.basis_cache_dir.mkdir(parents=True, exist_ok=True)
        for symbol in raw_symbols:
            safe_symbol = symbol.replace("/", "_")
            if args.basis_gate in {"bybit-high-tercile", "consensus-high-tercile"}:
                cache_path = args.basis_cache_dir / f"bybit_v1_{safe_symbol}_{start_ms}_{end_ms}.json"
                if cache_path.exists():
                    cached = json.loads(cache_path.read_text(encoding="utf-8"))
                    bybit_basis_history[symbol] = {int(timestamp): float(value) for timestamp, value in cached.items()}
                else:
                    observations = _bybit_premium_history(symbol, start_ms, end_ms)
                    cache_path.write_text(json.dumps(observations, separators=(",", ":")), encoding="utf-8")
                    bybit_basis_history[symbol] = observations
            if args.basis_gate in {"okx-high-tercile", "consensus-high-tercile"}:
                cache_path = args.basis_cache_dir / f"okx_v1_{safe_symbol}_{start_ms}_{end_ms}.json"
                if cache_path.exists():
                    cached = json.loads(cache_path.read_text(encoding="utf-8"))
                    okx_basis_history[symbol] = {int(timestamp): float(value) for timestamp, value in cached.items()}
                else:
                    observations = _okx_basis_history(symbol, start_ms, end_ms)
                    cache_path.write_text(json.dumps(observations, separators=(",", ":")), encoding="utf-8")
                    okx_basis_history[symbol] = observations
    flow_history = {}
    if args.flow_mode != "off":
        start_ms, end_ms = timestamps[0], timestamps[-1]
        args.flow_cache_dir.mkdir(parents=True, exist_ok=True)
        for symbol in raw_symbols:
            safe_symbol = symbol.replace("/", "_")
            cache_path = args.flow_cache_dir / f"binance_um_v1_{safe_symbol}_{start_ms}_{end_ms}.json"
            if cache_path.exists():
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                flow_history[symbol] = {int(timestamp): float(value) for timestamp, value in cached.items()}
            else:
                observations = _binance_signed_flow_history(symbol, start_ms, end_ms)
                cache_path.write_text(json.dumps(observations, separators=(",", ":")), encoding="utf-8")
                flow_history[symbol] = observations
    event = RuleSpec(
        family=args.event_family.upper(), lookback=args.event_lookback,
        threshold=args.breakout_threshold, persistence=1,
        channel_width=args.channel_width if args.event_family == "channel" else 0.0,
        holding=0, side="long",
    )
    targets, universe_membership_days = _daily_targets(
        daily, market, args.top_n, args.rank_days, args.volume_veto,
        args.oi_gate, oi_history, args.funding_crowding_veto, funding_history,
        args.basis_gate, bybit_basis_history, okx_basis_history,
        args.flow_mode, flow_history,
        args.universe_mode, args.liquidity_universe_size, args.liquidity_lookback_days,
        event, args.rank_mode, args.selection_mode, args.rebalance_days,
        args.market_regime == "on", args.liquidity_shock_gate,
        args.liquidity_shock_lookback, args.liquidity_shock_threshold,
    )
    risk_limit_tiers: dict[str, list[dict[str, float]]] = {}
    risk_limit_snapshot_at = None
    if args.gross_leverage > 1 and args.margin_model == "bybit-current-tiered":
        args.risk_limit_cache_dir.mkdir(parents=True, exist_ok=True)
        for symbol in raw_symbols:
            safe_symbol = symbol.replace("/", "_")
            cache_path = args.risk_limit_cache_dir / f"bybit_current_v1_{safe_symbol}.json"
            if cache_path.exists():
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
            else:
                cached = {
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "tiers": _bybit_risk_limit_tiers(symbol),
                }
                cache_path.write_text(json.dumps(cached, indent=2), encoding="utf-8")
            risk_limit_tiers[symbol] = cached["tiers"]
            retrieved_at = cached.get("retrieved_at")
            if retrieved_at and (risk_limit_snapshot_at is None or retrieved_at > risk_limit_snapshot_at):
                risk_limit_snapshot_at = retrieved_at
    applied_funding_events = 0
    missing_funding_events = 0
    liquidation_events = 0
    if args.funding_source == "bybit-history":
        # Audit the downloaded settlement series itself. Do not count ordinary
        # non-settlement 4H bars as missing funding events.
        for rates in funding_history.values():
            times = sorted(rates)
            gaps = [right - left for left, right in zip(times, times[1:]) if right > left]
            if not gaps:
                continue
            normal_interval = int(statistics.median(gaps))
            if normal_interval > 0:
                missing_funding_events += sum(max(0, round(gap / normal_interval) - 1) for gap in gaps)

    def mark_equity(time: int) -> float:
        return cash + sum(p["qty"] * float(bars[s][time][4]) for s, p in positions.items())

    def close(symbol: str, raw_price: float) -> None:
        nonlocal cash, trade_count
        position = positions.pop(symbol)
        price = raw_price * (1 - slip_rate)
        notional = position["qty"] * price
        cash += notional * (1 - fee_rate)
        trade_count += 1

    def liquidate_all(time: int) -> None:
        nonlocal cash, trade_count, liquidation_events
        liquidation_fee_rate = args.liquidation_fee_bps / 10_000
        for symbol in list(positions):
            position = positions.pop(symbol)
            price = float(bars[symbol][time][3]) * (1 - slip_rate)
            notional = position["qty"] * price
            cash += notional * (1 - fee_rate - liquidation_fee_rate)
            trade_count += 1
        liquidation_events += 1

    def maintenance_margin_at(time: int, price_index: int) -> float:
        required = 0.0
        for symbol, position in positions.items():
            notional = position["qty"] * float(bars[symbol][time][price_index])
            if args.margin_model == "bybit-current-tiered":
                required += _tiered_maintenance_margin(notional, risk_limit_tiers[symbol])
            else:
                required += args.maintenance_margin_rate * notional
        return required

    for time in ordered_times:
        if time not in targets and not positions:
            continue
        if positions and args.gross_leverage > 1:
            low_equity = cash + sum(
                position["qty"] * float(bars[symbol][time][3]) for symbol, position in positions.items()
            )
            required_maintenance_margin = maintenance_margin_at(time, 3)
            if low_equity <= required_maintenance_margin:
                liquidate_all(time)
                desired = set()
                equity_curve.append(cash)
                equity_points.append((time, cash))
                if cash <= 0:
                    break
                continue
        # Stops/trailing are evaluated from the current 4H OHLC before a new
        # daily target is acted upon; if both could trigger, the adverse stop is used.
        stopped_this_bar: set[str] = set()
        for symbol in list(positions):
            row = bars[symbol][time]
            position = positions[symbol]
            position["peak"] = max(position["peak"], float(row[2]))
            trailing = position["peak"] - args.trail_atr * position["atr"] if args.trail_atr > 0 else -math.inf
            stop = max(position["stop"], trailing)
            if math.isfinite(stop) and float(row[3]) <= stop:
                close(symbol, stop)
                stopped_this_bar.add(symbol)

        if time in targets:
            desired = targets[time]
            for symbol in list(positions):
                if symbol not in desired:
                    close(symbol, float(bars[symbol][time][1]))
            equity = mark_equity(time)
            allocation = equity * args.gross_leverage / max(1, len(desired))
            for symbol in desired:
                if symbol in positions or symbol in stopped_this_bar:
                    continue
                idx = index_by_time[symbol][time]
                current_atr = _atr(four_h[symbol], idx)
                if current_atr is None:
                    continue
                raw_open = float(bars[symbol][time][1])
                entry = raw_open * (1 + slip_rate)
                initial_allocation = allocation / args.max_pyramid_layers if args.pyramid_mode == "winner-only" else allocation
                qty = initial_allocation / entry
                cost = qty * entry * (1 + fee_rate)
                if args.gross_leverage <= 1 and cost > cash:
                    qty = cash / (entry * (1 + fee_rate))
                    cost = qty * entry * (1 + fee_rate)
                cash -= cost
                positions[symbol] = {
                    "qty": qty,
                    "stop": entry - args.stop_atr * current_atr if args.stop_atr > 0 else -math.inf,
                    "atr": current_atr,
                    "peak": entry,
                    "layers": 1,
                    "last_add_price": entry,
                }
                trade_count += 1

        # Add only after a favorable move observable at this 4H open. The
        # complete position remains capped by the daily equal-weight budget.
        if args.pyramid_mode == "winner-only" and desired:
            equity = mark_equity(time)
            for symbol in list(positions):
                position = positions[symbol]
                if symbol not in desired or position["layers"] >= args.max_pyramid_layers:
                    continue
                raw_open = float(bars[symbol][time][1])
                if raw_open < position["last_add_price"] + args.pyramid_step_atr * position["atr"]:
                    continue
                allocation = equity * args.gross_leverage / max(1, len(desired)) / args.max_pyramid_layers
                entry = raw_open * (1 + slip_rate)
                qty = allocation / entry
                if args.gross_leverage <= 1:
                    qty = min(qty, cash / (entry * (1 + fee_rate)))
                if qty <= 0:
                    continue
                cash -= qty * entry * (1 + fee_rate)
                position["qty"] += qty
                position["last_add_price"] = entry
                position["layers"] += 1
                position["stop"] = max(position["stop"], entry - args.stop_atr * position["atr"]) if args.stop_atr > 0 else -math.inf
                trade_count += 1

        # Funding is charged only at actual settlement timestamps. For the
        # proxy mode this remains a conservative 8H fixed rate.
        for symbol, position in positions.items():
            if args.funding_source == "bybit-history":
                rate = funding_history[symbol].get(time)
                if rate is None:
                    continue
                cash -= position["qty"] * float(bars[symbol][time][4]) * rate
                applied_funding_events += 1
            elif time % (8 * 60 * 60 * 1000) == 0:
                cash -= position["qty"] * float(bars[symbol][time][4]) * args.funding_bps_8h / 10_000
                applied_funding_events += 1
        equity_curve.append(mark_equity(time))
        equity_points.append((time, equity_curve[-1]))

    final_time = ordered_times[-1]
    for symbol in list(positions):
        close(symbol, float(bars[symbol][final_time][4]))
    final_equity = cash
    equity_curve.append(final_equity)
    if equity_points and equity_points[-1][0] == final_time:
        equity_points[-1] = (final_time, final_equity)
    else:
        equity_points.append((final_time, final_equity))
    peak = args.balance
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        max_dd = max(max_dd, 1 - value / peak)
    fold_ms = args.fold_days * DAY_MS
    folds = []
    if equity_points:
        first_time, last_time = equity_points[0][0], equity_points[-1][0]
        for start in range(first_time, last_time, fold_ms):
            values = [value for time, value in equity_points if start <= time < start + fold_ms]
            if len(values) < 2:
                continue
            fold_peak = values[0]
            fold_dd = 0.0
            for value in values:
                fold_peak = max(fold_peak, value)
                fold_dd = max(fold_dd, 1 - value / fold_peak)
            folds.append({
                "start": datetime.fromtimestamp(start / 1000, tz=timezone.utc).date().isoformat(),
                "return_pct": round((values[-1] / values[0] - 1) * 100, 4),
                "max_drawdown_pct": round(fold_dd * 100, 4),
            })
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {"candidate_pool": raw_symbols, "candidate_pool_survivorship_free": False, "universe_mode": args.universe_mode, "liquidity_universe_size": args.liquidity_universe_size if args.universe_mode == "point-in-time-liquidity" else None, "liquidity_lookback_days": args.liquidity_lookback_days if args.universe_mode == "point-in-time-liquidity" else None, "liquidity_measure": "trailing closed daily base volume * close", "selection_mode": args.selection_mode, "rebalance_days": args.rebalance_days if args.selection_mode == "weekly-oscillator" else None, "market_regime": args.market_regime, "event_family": args.event_family if args.selection_mode == "breakout" else None, "event_lookback": args.event_lookback if args.selection_mode == "breakout" else None, "channel_width": args.channel_width if args.selection_mode == "breakout" and args.event_family == "channel" else None, "breakout_threshold": args.breakout_threshold if args.selection_mode == "breakout" else None, "rank_mode": args.rank_mode, "daily_selection": f"market regime={args.market_regime} + {args.selection_mode} + top-N {args.rank_days}d {args.rank_mode}", "volume_veto": args.volume_veto, "oi_gate": args.oi_gate, "funding_crowding_veto": args.funding_crowding_veto, "basis_gate": args.basis_gate, "flow_mode": args.flow_mode, "gross_leverage": args.gross_leverage, "margin_model": args.margin_model if args.gross_leverage > 1 else None, "maintenance_margin_rate": args.maintenance_margin_rate if args.gross_leverage > 1 and args.margin_model == "flat" else None, "risk_limit_snapshot_at": risk_limit_snapshot_at, "risk_limit_history_available": False if args.gross_leverage > 1 and args.margin_model == "bybit-current-tiered" else None, "liquidation_fee_bps": args.liquidation_fee_bps if args.gross_leverage > 1 else None, "fill": "next daily 4H open", "stops": "4H ATR fixed plus trailing, adverse OHLC stop", "pyramiding": args.pyramid_mode, "max_pyramid_layers": args.max_pyramid_layers if args.pyramid_mode == "winner-only" else 1, "pyramid_step_atr": args.pyramid_step_atr if args.pyramid_mode == "winner-only" else None, "fee_bps": args.fee_bps, "slippage_bps": args.slippage_bps, "spread_bps": args.spread_bps, "impact_bps": args.impact_bps, "effective_adverse_execution_bps": execution_bps, "funding_source": args.funding_source, "funding_bps_8h": args.funding_bps_8h if args.funding_source == "proxy" else None},
        "result": {"starting_balance": args.balance, "final_equity": round(final_equity, 2), "return_pct": round((final_equity / args.balance - 1) * 100, 4), "max_drawdown_pct": round(max_dd * 100, 4), "fills": trade_count},
        "walk_forward_folds": folds,
        "positive_folds": sum(fold["return_pct"] > 0 for fold in folds),
        "folds_tested": len(folds),
        "applied_funding_events": applied_funding_events,
        "missing_funding_events": missing_funding_events,
        "liquidation_events": liquidation_events,
        "universe_membership_days": universe_membership_days,
    }
    payload["protocol"]["execution_semantics"] = "no_same_bar_reentry_v1"
    payload["protocol"]["liquidity_shock_gate"] = args.liquidity_shock_gate
    payload["protocol"]["liquidity_shock_lookback"] = (
        args.liquidity_shock_lookback if args.liquidity_shock_gate != "off" else None
    )
    payload["protocol"]["liquidity_shock_threshold"] = (
        args.liquidity_shock_threshold if args.liquidity_shock_gate != "off" else None
    )
    if args.include_equity_curve:
        payload["equity_points"] = [[time, round(value, 8)] for time, value in equity_points]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
