"""Shared causal construction for HYB-005 capital-neutral reallocation."""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DAY_MS = 86_400_000
SYMBOLS = ("BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT")
ALIASES = {
    "BTCUSDT": {"bitcoin", "btc"},
    "ETHUSDT": {"ethereum", "eth", "ether"},
    "XRPUSDT": {"xrp", "ripple"},
    "SOLUSDT": {"sol", "solana"},
    "BNBUSDT": {"bnb", "binance coin"},
}
SEED = 20_260_911


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_asset(value: object) -> str | None:
    normalized = " ".join(str(value).strip().lower().split())
    for symbol, aliases in ALIASES.items():
        if normalized in aliases:
            return symbol
    return None


def event_strength(event: dict[str, Any]) -> float:
    return (
        float(event.get("severity", 0.0))
        * float(event.get("confidence", 0.0))
        * (0.5 + 0.5 * float(event.get("reported_surprise", 0.0)))
    )


def daily_asset_scores(events_path: Path, inputs_path: Path) -> dict[str, dict[str, dict[str, float]]]:
    events = read_json(events_path)["records"]
    inputs = read_json(inputs_path)["records"]
    source_by_id = {row["headline_id"]: row for row in inputs}
    if len(source_by_id) != len(inputs) or len(events) != len(inputs):
        raise ValueError("frozen extractor/input identity mismatch")
    output: dict[str, dict[str, dict[str, float]]] = defaultdict(
        lambda: {symbol: {"positive": 0.0, "negative": 0.0, "headlines": 0.0} for symbol in SYMBOLS}
    )
    seen: set[str] = set()
    latest_by_date: dict[str, str] = {}
    for event in events:
        headline_id = str(event["headline_id"])
        source = source_by_id.get(headline_id)
        if source is None or source["information_date"] != event["information_date"]:
            raise ValueError(f"event/input mismatch: {headline_id}")
        if event.get("status") != "success" or event.get("error") is not None:
            raise ValueError(f"non-success frozen event: {headline_id}")
        seen.add(headline_id)
        date = str(event["information_date"])
        available_at = str(source["available_at"])
        latest_by_date[date] = max(latest_by_date.get(date, available_at), available_at)
        affected = {canonical_asset(value) for value in (event.get("affected_assets") or [])}
        affected.discard(None)
        direction = str(event.get("direction", "neutral"))
        if direction not in {"positive", "negative"}:
            continue
        strength = event_strength(event)
        for symbol in affected:
            row = output[date][symbol]
            row[direction] = max(row[direction], strength)
            row["headlines"] += 1.0
    if len(seen) != len(inputs):
        raise ValueError("frozen extractor coverage mismatch")
    for date, rows in output.items():
        for row in rows.values():
            row["signed"] = row["positive"] - row["negative"]
        rows["_meta"] = {"latest_available_at": latest_by_date[date]}  # type: ignore[assignment]
    return dict(output)


def load_daily(directory: Path) -> tuple[list[int], dict[str, list[list[float]]]]:
    data: dict[str, list[list[float]]] = {}
    for symbol in SYMBOLS:
        matches = sorted(directory.glob(f"{symbol}_*.json"))
        if len(matches) != 1:
            raise ValueError(f"expected one daily artifact for {symbol}, got {len(matches)}")
        rows = read_json(matches[0])
        if not isinstance(rows, list) or len(rows) < 1000:
            raise ValueError(f"invalid daily data for {symbol}")
        data[symbol] = rows
    timestamps = [int(row[0]) for row in data[SYMBOLS[0]]]
    if any([int(row[0]) for row in data[symbol]] != timestamps for symbol in SYMBOLS[1:]):
        raise ValueError("daily artifacts are not timestamp-aligned")
    return timestamps, data


def long_signal(closes: list[float], highs: list[float], lows: list[float], i: int) -> bool:
    start = i - 10
    if start < 0:
        return False
    prior_high = max(highs[start:i])
    prior_low = min(lows[start:i])
    return (prior_high / prior_low - 1) <= 0.10 and closes[i] > prior_high


def long_exit(closes: list[float], highs: list[float], lows: list[float], i: int) -> bool:
    start = i - 10
    if start < 0:
        return False
    prior_high = max(highs[start:i])
    prior_low = min(lows[start:i])
    return (prior_high / prior_low - 1) <= 0.10 and closes[i] < prior_low


def tilted_pair_weights(selected: set[str], signed: dict[str, float]) -> dict[str, float]:
    if len(selected) != 2:
        return {symbol: (1.0 if symbol in selected else 0.0) for symbol in SYMBOLS}
    first, second = sorted(selected)
    first_weight = min(0.75, max(0.25, 0.5 + 0.25 * (signed[first] - signed[second])))
    return {symbol: first_weight if symbol == first else (1.0 - first_weight if symbol == second else 0.0) for symbol in SYMBOLS}


def construct_assignments(daily_dir: Path, events_path: Path, inputs_path: Path) -> dict[str, Any]:
    timestamps, data = load_daily(daily_dir)
    scores = daily_asset_scores(events_path, inputs_path)
    coverage_start, coverage_end = min(scores), max(scores)
    closes = {symbol: [float(row[4]) for row in data[symbol]] for symbol in SYMBOLS}
    highs = {symbol: [float(row[2]) for row in data[symbol]] for symbol in SYMBOLS}
    lows = {symbol: [float(row[3]) for row in data[symbol]] for symbol in SYMBOLS}
    positions: set[str] = set()
    rows: list[dict[str, Any]] = []
    for i in range(20, len(timestamps) - 1):
        market_up_up = closes["BTCUSDT"][i] >= closes["BTCUSDT"][i - 7] >= closes["BTCUSDT"][i - 14]
        if not market_up_up:
            positions.clear()
        else:
            positions = {symbol for symbol in positions if not long_exit(closes[symbol], highs[symbol], lows[symbol], i)}
            entrants = [symbol for symbol in SYMBOLS if symbol not in positions and long_signal(closes[symbol], highs[symbol], lows[symbol], i)]
            entrants.sort(key=lambda symbol: closes[symbol][i] / closes[symbol][i - 20] - 1, reverse=True)
            positions.update(entrants[: max(0, 2 - len(positions))])
        information_date = datetime.fromtimestamp(timestamps[i] / 1000, tz=timezone.utc).date().isoformat()
        if not coverage_start <= information_date <= coverage_end:
            continue
        decision_time = timestamps[i] + DAY_MS
        daily = scores.get(information_date)
        if daily:
            available = datetime.fromisoformat(str(daily["_meta"]["latest_available_at"])).astimezone(timezone.utc)
            if int(available.timestamp() * 1000) > decision_time:
                raise ValueError(f"look-ahead text availability on {information_date}")
        signed = {symbol: float(daily[symbol]["signed"]) if daily else 0.0 for symbol in SYMBOLS}
        headlines = {symbol: int(daily[symbol]["headlines"]) if daily else 0 for symbol in SYMBOLS}
        base = {symbol: (1.0 / len(positions) if symbol in positions else 0.0) for symbol in SYMBOLS}
        primary = tilted_pair_weights(positions, signed)
        opposite = tilted_pair_weights(positions, {symbol: -signed[symbol] for symbol in SYMBOLS})
        delayed_date = datetime.fromtimestamp((timestamps[i] - DAY_MS) / 1000, tz=timezone.utc).date().isoformat()
        delayed = scores.get(delayed_date)
        delayed_signed = {symbol: float(delayed[symbol]["signed"]) if delayed else 0.0 for symbol in SYMBOLS}
        delayed_weights = tilted_pair_weights(positions, delayed_signed)
        rows.append({
            "index": i, "timestamp": timestamps[i], "decision_time": decision_time,
            "information_date": information_date, "selected": sorted(positions),
            "base_weights": base, "primary_weights": primary, "opposite_weights": opposite,
            "delayed_weights": delayed_weights, "signed_scores": signed, "headline_counts": headlines,
            "active": any(abs(primary[symbol] - base[symbol]) > 1e-12 for symbol in SYMBOLS),
        })
    pair_rows = [row for row in rows if len(row["selected"]) == 2]
    tilts = [row["primary_weights"][sorted(row["selected"])[0]] - 0.5 for row in pair_rows]
    random.Random(SEED).shuffle(tilts)
    tilt_by_timestamp = {row["timestamp"]: tilt for row, tilt in zip(pair_rows, tilts, strict=True)}
    for row in rows:
        if len(row["selected"]) == 2:
            ordered = sorted(row["selected"])
            row["shuffled_weights"] = {symbol: 0.0 for symbol in SYMBOLS}
            tilt = tilt_by_timestamp[row["timestamp"]]
            row["shuffled_weights"][ordered[0]] = 0.5 + tilt
            row["shuffled_weights"][ordered[1]] = 0.5 - tilt
        else:
            row["shuffled_weights"] = dict(row["base_weights"])
    return {"timestamps": timestamps, "rows": rows, "coverage": [coverage_start, coverage_end]}


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction
