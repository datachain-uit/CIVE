"""Independent replay audit for frozen HYB-002.

This script does not alter the frozen policy or its canonical development result.
It reconstructs the shadow Tech-Control ledger from frozen OHLC/funding inputs,
then re-evaluates each one-bar intervention using the replayed quantities and
exit fills instead of quantities algebraically inferred from closed-trade PnL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUR_H_MS = 14_400_000
SEED = 20_260_909
DRAWS = 10_000
FEE_RATE = 0.0006
SLIP_RATE = 0.0005
STOP_ATR = 3.0
TRAIL_ATR = 4.0


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def trade_id(row: dict[str, Any]) -> str:
    return f"{int(row['entry_time'])}::{row['symbol']}"


def iso(stamp: int) -> str:
    return datetime.fromtimestamp(stamp / 1000, tz=timezone.utc).isoformat()


def atr(rows: list[list[float]], index: int, period: int = 14) -> float | None:
    if index < period:
        return None
    ranges = []
    for cursor in range(index - period + 1, index + 1):
        high, low = float(rows[cursor][2]), float(rows[cursor][3])
        previous_close = float(rows[cursor - 1][4])
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return sum(ranges) / len(ranges)


def stop_transition(row: list[float], position: dict[str, float]) -> tuple[float | None, float]:
    opening, high, low = map(float, row[1:4])
    active_stop = max(position["stop"], position["peak"] - TRAIL_ATR * position["atr"])
    if opening <= active_stop:
        return opening, position["peak"]
    if low <= active_stop:
        return active_stop, position["peak"]
    return None, max(position["peak"], high)


def verify_frozen_inputs(frozen: dict[str, Any]) -> None:
    for name, item in frozen["inputs"].items():
        checks = item if name == "market_and_funding" else [item]
        for check in checks:
            actual = sha256(Path(check["path"]))
            if actual != check["sha256"]:
                raise ValueError(f"frozen hash mismatch for {name}: {check['path']}")


def load_market(frozen: dict[str, Any]) -> tuple[
    dict[str, list[list[float]]], dict[str, dict[int, list[float]]], dict[str, dict[int, float]]
]:
    rows: dict[str, list[list[float]]] = {}
    bars: dict[str, dict[int, list[float]]] = {}
    funding: dict[str, dict[int, float]] = {}
    for item in frozen["inputs"]["market_and_funding"]:
        path = Path(item["path"])
        symbol = path.name.split("_")[0]
        payload = read_json(path)
        if "funding" in path.parent.name:
            funding[symbol] = {int(k): float(v) for k, v in payload.items()}
        else:
            series = [[float(x) for x in row] for row in payload]
            rows[symbol] = series
            bars[symbol] = {int(row[0]): row for row in series}
    return rows, bars, funding


def lifecycle(frozen: dict[str, Any], tech: dict[str, Any]) -> list[dict[str, Any]]:
    source = read_json(Path(frozen["inputs"]["lifecycle"]["path"]))
    expected = sorted(source["feature_audit"], key=lambda x: (int(x["entry_time"]), x["symbol"]))
    by_id = {trade_id(row): row for row in tech["closed_trades"]}
    output = []
    for row in expected:
        actual = by_id.get(trade_id(row))
        if actual is None:
            raise ValueError(f"missing Tech trade: {trade_id(row)}")
        if int(actual["exit_time"]) != int(row["exit_time"]) or actual["reason"] != row["exit_reason"]:
            raise ValueError(f"lifecycle mismatch: {trade_id(row)}")
        output.append(actual)
    return output


def replay_shadow(
    trades: list[dict[str, Any]], rows: dict[str, list[list[float]]],
    bars: dict[str, dict[int, list[float]]], funding: dict[str, dict[int, float]],
) -> dict[str, Any]:
    indexes = {symbol: {int(row[0]): i for i, row in enumerate(series)} for symbol, series in rows.items()}
    entries = {int(trade["entry_time"]): trade for trade in trades}
    expected_by_id = {trade_id(trade): trade for trade in trades}
    start, end = int(trades[0]["entry_time"]), int(trades[-1]["exit_time"])
    cash = 10_000.0
    position: dict[str, Any] | None = None
    replayed: list[dict[str, Any]] = []
    equity_points: list[list[float]] = []
    intrabar_points: list[list[float]] = []

    def close(raw_exit: float, reason: str, stamp: int) -> None:
        nonlocal cash, position
        assert position is not None
        exit_price = raw_exit * (1 - SLIP_RATE)
        exit_fee = position["qty"] * exit_price * FEE_RATE
        cash += position["qty"] * exit_price - exit_fee
        gross = position["qty"] * (raw_exit - position["raw_entry"])
        execution = position["qty"] * (
            position["entry"] - position["raw_entry"] + raw_exit - exit_price
        )
        fees = position["entry_fee"] + exit_fee
        net = gross - execution - fees - position["funding_paid"]
        replayed.append({
            "trade_id": position["trade_id"], "symbol": position["symbol"],
            "entry_time": position["entry_time"], "exit_time": stamp, "reason": reason,
            "quantity": position["qty"], "raw_entry": position["raw_entry"],
            "entry_price": position["entry"], "raw_exit": raw_exit,
            "exit_price": exit_price, "gross_price_pnl": gross,
            "execution_cost": execution, "fees": fees,
            "funding_paid": position["funding_paid"], "net_pnl": net,
        })
        position = None

    for stamp in range(start, end + FOUR_H_MS, FOUR_H_MS):
        if position is not None:
            expected = expected_by_id[position["trade_id"]]
            if stamp == int(expected["exit_time"]) and expected["reason"] == "rebalance":
                close(float(bars[position["symbol"]][stamp][1]), "rebalance", stamp)

        entering = entries.get(stamp)
        if entering is not None:
            if position is not None:
                raise ValueError(f"overlapping frozen lifecycle at {iso(stamp)}")
            symbol = entering["symbol"]
            row = bars[symbol][stamp]
            current_atr = atr(rows[symbol], indexes[symbol][stamp])
            if current_atr is None:
                raise ValueError(f"ATR unavailable at {trade_id(entering)}")
            raw_entry = float(row[1])
            entry_price = raw_entry * (1 + SLIP_RATE)
            quantity = cash / (entry_price * (1 + FEE_RATE))
            entry_fee = quantity * entry_price * FEE_RATE
            cash -= quantity * entry_price + entry_fee
            position = {
                "trade_id": trade_id(entering), "symbol": symbol, "entry_time": stamp,
                "qty": quantity, "atr": current_atr, "peak": entry_price,
                "stop": entry_price - STOP_ATR * current_atr,
                "raw_entry": raw_entry, "entry": entry_price,
                "entry_fee": entry_fee, "funding_paid": 0.0,
            }

        if position is not None:
            symbol = position["symbol"]
            rate = funding.get(symbol, {}).get(stamp)
            if rate is not None:
                payment = position["qty"] * float(bars[symbol][stamp][4]) * rate
                cash -= payment
                position["funding_paid"] += payment

            bar = bars[symbol][stamp]
            stop_fill, next_peak = stop_transition(bar, position)
            if stop_fill is not None:
                expected = expected_by_id[position["trade_id"]]
                if int(expected["exit_time"]) != stamp or expected["reason"] != "stop":
                    raise ValueError(f"unexpected replay stop at {iso(stamp)} for {position['trade_id']}")
                close(stop_fill, "stop", stamp)
            else:
                position["peak"] = next_peak

        close_equity = cash
        low_equity = cash
        if position is not None:
            symbol = position["symbol"]
            close_equity += position["qty"] * float(bars[symbol][stamp][4])
            low_equity += position["qty"] * float(bars[symbol][stamp][3])
        equity_points.append([stamp, close_equity])
        intrabar_points.append([stamp, min(close_equity, low_equity)])

    if position is not None:
        raise ValueError("position remained open after frozen lifecycle")

    comparisons = []
    fields = ("gross_price_pnl", "execution_cost", "fees", "funding_paid", "net_pnl")
    for replay, expected in zip(replayed, trades, strict=True):
        errors = {field: replay[field] - float(expected[field]) for field in fields}
        comparisons.append({
            "trade_id": replay["trade_id"], "errors": errors,
            "max_abs_error": max(abs(value) for value in errors.values()),
        })
    max_error = max(row["max_abs_error"] for row in comparisons)
    if max_error > 1e-6:
        raise ValueError(f"shadow ledger does not reconcile; max component error={max_error}")
    return {
        "initial_equity": 10_000.0, "final_equity": cash,
        "trades": replayed, "equity_points": equity_points,
        "intrabar_points": intrabar_points, "comparisons": comparisons,
        "max_abs_component_error": max_error,
    }


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def bootstrap(rows: list[dict[str, Any]]) -> list[float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row["trade_id"]].append(row["net_difference"])
    keys = sorted(grouped)
    rng = random.Random(SEED)
    return [
        statistics.fmean(value for key in (rng.choice(keys) for _ in keys) for value in grouped[key])
        for _ in range(DRAWS)
    ]


def audit_windows(
    actions: list[dict[str, Any]], replay: dict[str, Any],
    bars: dict[str, dict[int, list[float]]], funding: dict[str, dict[int, float]],
) -> dict[str, Any]:
    by_trade = {row["trade_id"]: row for row in replay["trades"]}
    start_equity: dict[str, float] = {}
    equity = replay["initial_equity"]
    for trade in replay["trades"]:
        start_equity[trade["trade_id"]] = equity
        equity += trade["net_pnl"]
    windows = []
    for action in actions:
        trade = by_trade[action["trade_id"]]
        symbol = trade["symbol"]
        start = int(action["action_time"])
        end = min(start + FOUR_H_MS, int(trade["exit_time"]))
        quantity = 0.5 * trade["quantity"]
        raw_sell = float(bars[symbol][start][1])
        sell_fill = raw_sell * (1 - SLIP_RATE)
        exits = end == int(trade["exit_time"])
        raw_end = trade["raw_exit"] if exits else float(bars[symbol][end][1])
        saved_funding = sum(
            quantity * float(bars[symbol][stamp][4]) * rate
            for stamp, rate in funding.get(symbol, {}).items() if start <= stamp < end
        )
        if exits:
            end_fill = raw_end * (1 - SLIP_RATE)
            dollars = quantity * (sell_fill - end_fill)
            dollars += -quantity * sell_fill * FEE_RATE + quantity * end_fill * FEE_RATE
            overlay_cost = quantity * sell_fill * FEE_RATE - quantity * end_fill * FEE_RATE
        else:
            end_fill = raw_end * (1 + SLIP_RATE)
            dollars = quantity * (sell_fill - end_fill)
            dollars -= quantity * (sell_fill + end_fill) * FEE_RATE
            overlay_cost = quantity * (raw_sell + raw_end) * (SLIP_RATE + FEE_RATE)
        dollars += saved_funding
        gross = quantity * (raw_sell - raw_end)
        denominator = start_equity[trade["trade_id"]]
        windows.append({
            **action, "window_end": end, "window_end_iso": iso(end),
            "replayed_quantity": trade["quantity"], "raw_start": raw_sell,
            "raw_end": raw_end, "exit_in_window": exits,
            "gross_difference": gross / denominator,
            "net_difference": dollars / denominator,
            "funding_saved": saved_funding / denominator,
            "overlay_cost": overlay_cost / denominator,
        })
    nets = [row["net_difference"] for row in windows]
    grosses = [row["gross_difference"] for row in windows]
    draws = bootstrap(windows)
    return {
        "interventions": len(windows),
        "trade_clusters": len({row["trade_id"] for row in windows}),
        "mean_paired_net_difference": statistics.fmean(nets),
        "mean_paired_gross_difference": statistics.fmean(grosses),
        "cluster_bootstrap_ci95": [quantile(draws, 0.025), quantile(draws, 0.975)],
        "total_overlay_cost_fraction": sum(row["overlay_cost"] for row in windows),
        "windows": windows,
    }


def semantic_diagnostic(frozen: dict[str, Any]) -> dict[str, Any]:
    event_payload = read_json(Path(frozen["inputs"]["events"]["path"]))
    input_payload = read_json(Path(frozen["inputs"]["extraction_inputs"]["path"]))
    events = {row["headline_id"]: row for row in event_payload["records"]}
    inputs = {row["headline_id"]: row for row in input_payload["records"]}
    long_terms = ("long liquidation", "longs liquidated", "long positions", "long traders")
    short_terms = ("short liquidation", "shorts liquidated", "short positions", "short squeeze")
    rows = []
    for action in frozen["assignments"]["primary"]:
        headlines = []
        labels = set()
        for headline_id in action["headline_ids"]:
            source = inputs[headline_id]
            event = events[headline_id]
            text = str(source.get("headline", "")).casefold()
            has_long = any(term in text for term in long_terms)
            has_short = any(term in text for term in short_terms)
            label = "both" if has_long and has_short else "long" if has_long else "short" if has_short else "ambiguous"
            labels.add(label)
            headlines.append({
                "headline_id": headline_id, "headline": source.get("headline"),
                "source_domain": source.get("source_domain"), "available_at": source.get("available_at"),
                "event_type": event.get("event_type"), "direction": event.get("direction"),
                "liquidation_side_lexical": label,
            })
        rows.append({
            "trade_id": action["trade_id"], "information_date": action["information_date"],
            "event_type": action["event_type"], "liquidation_side_labels": sorted(labels),
            "headlines": headlines,
        })
    liquidation = [row for row in rows if "liquidation_leverage" in row["event_type"]]
    counts = defaultdict(int)
    for row in liquidation:
        aggregate = "ambiguous"
        labels = set(row["liquidation_side_labels"])
        if labels <= {"long"}:
            aggregate = "long"
        elif labels <= {"short"}:
            aggregate = "short"
        elif "long" in labels and "short" in labels:
            aggregate = "mixed"
        counts[aggregate] += 1
        row["aggregate_liquidation_side"] = aggregate
    return {
        "method": "frozen deterministic headline lexicon; diagnostic only, no outcome labels used",
        "liquidation_action_counts": dict(sorted(counts.items())), "actions": rows,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--predeclared", type=Path, default=root / "paper/input/results/hybrid/tech_llm_intratrade_shock_shield_v2_predeclared.json")
    parser.add_argument("--canonical-result", type=Path, default=root / "paper/input/results/hybrid/tech_llm_intratrade_shock_shield_v2_development.json")
    parser.add_argument("--output", type=Path, default=root / "paper/input/results/hybrid/tech_llm_intratrade_shock_shield_v2_replay_audit.json")
    args = parser.parse_args()

    frozen = read_json(args.predeclared)
    verify_frozen_inputs(frozen)
    tech = read_json(Path(frozen["inputs"]["tech_result"]["path"]))
    trades = lifecycle(frozen, tech)
    rows, bars, funding = load_market(frozen)
    replay = replay_shadow(trades, rows, bars, funding)
    primary = audit_windows(frozen["assignments"]["primary"], replay, bars, funding)
    canonical = read_json(args.canonical_result)["arms"]["primary"]
    comparison = {
        "mean_net_difference": primary["mean_paired_net_difference"] - canonical["mean_paired_net_difference"],
        "mean_gross_difference": primary["mean_paired_gross_difference"] - canonical["mean_paired_gross_difference"],
        "ci95_lower_difference": primary["cluster_bootstrap_ci95"][0] - canonical["cluster_bootstrap_ci95"][0],
        "ci95_upper_difference": primary["cluster_bootstrap_ci95"][1] - canonical["cluster_bootstrap_ci95"][1],
    }
    payload = {
        "schema_version": "tech-llm-intratrade-shock-shield-v2-replay-audit-v1",
        "experiment_id": "HYB-002", "status": "post-outcome-replay-audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_role": "diagnostic audit only; not a new validation or policy search",
        "predeclared": {"path": str(args.predeclared.resolve()), "sha256": sha256(args.predeclared)},
        "audit_runner": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).resolve())},
        "shadow_reconciliation": replay,
        "primary_replayed": primary,
        "canonical_difference": comparison,
        "semantic_diagnostic": semantic_diagnostic(frozen),
        "limitations": [
            "The 24-trade lifecycle is frozen, but this audit was written after HYB-002 outcomes were observed.",
            "The primary estimand remains a one-bar paired intervention effect, not a claim of live performance.",
            "Intrabar equity uses observable 4H low marks and is retained as an audit series; the frozen gate needs a separately specified portfolio-level comparison.",
        ],
    }
    write_json(args.output, payload)
    print(json.dumps({
        "output": str(args.output), "shadow_trades": len(replay["trades"]),
        "max_abs_component_error": replay["max_abs_component_error"],
        "primary_mean_net": primary["mean_paired_net_difference"],
        "ci95": primary["cluster_bootstrap_ci95"], "canonical_difference": comparison,
        "liquidation_action_counts": payload["semantic_diagnostic"]["liquidation_action_counts"],
    }, indent=2))


if __name__ == "__main__":
    main()
