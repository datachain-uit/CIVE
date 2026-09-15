"""Causal construction shared by HYB-006 rank-pair reallocation stages."""
from __future__ import annotations

import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hyb005_cross_asset_common import DAY_MS, SEED, SYMBOLS, daily_asset_scores, load_daily


def pair_weights(selected: tuple[str, str], signed: dict[str, float]) -> dict[str, float]:
    first, second = sorted(selected)
    first_weight = min(0.75, max(0.25, 0.5 + 0.25 * (signed[first] - signed[second])))
    return {
        symbol: first_weight if symbol == first else (1.0 - first_weight if symbol == second else 0.0)
        for symbol in SYMBOLS
    }


def construct_assignments(daily_dir: Path, events_path: Path, inputs_path: Path) -> dict[str, Any]:
    timestamps, data = load_daily(daily_dir)
    scores = daily_asset_scores(events_path, inputs_path)
    coverage_start, coverage_end = min(scores), max(scores)
    closes = {symbol: [float(row[4]) for row in data[symbol]] for symbol in SYMBOLS}
    rows: list[dict[str, Any]] = []
    for i in range(20, len(timestamps) - 1):
        information_date = datetime.fromtimestamp(timestamps[i] / 1000, tz=timezone.utc).date().isoformat()
        if not coverage_start <= information_date <= coverage_end:
            continue
        decision_time = timestamps[i] + DAY_MS
        daily = scores.get(information_date)
        if daily:
            available = datetime.fromisoformat(str(daily["_meta"]["latest_available_at"])).astimezone(timezone.utc)
            if int(available.timestamp() * 1000) > decision_time:
                raise ValueError(f"look-ahead text availability on {information_date}")
        momentum = {symbol: closes[symbol][i] / closes[symbol][i - 20] - 1.0 for symbol in SYMBOLS}
        selected = tuple(sorted(SYMBOLS, key=lambda symbol: (-momentum[symbol], symbol))[:2])
        signed = {symbol: float(daily[symbol]["signed"]) if daily else 0.0 for symbol in SYMBOLS}
        headlines = {symbol: int(daily[symbol]["headlines"]) if daily else 0 for symbol in SYMBOLS}
        base = {symbol: (0.5 if symbol in selected else 0.0) for symbol in SYMBOLS}
        primary = pair_weights(selected, signed)
        opposite = pair_weights(selected, {symbol: -signed[symbol] for symbol in SYMBOLS})
        delayed_date = datetime.fromtimestamp((timestamps[i] - DAY_MS) / 1000, tz=timezone.utc).date().isoformat()
        delayed_daily = scores.get(delayed_date)
        delayed_signed = {symbol: float(delayed_daily[symbol]["signed"]) if delayed_daily else 0.0 for symbol in SYMBOLS}
        delayed = pair_weights(selected, delayed_signed)
        rows.append({
            "index": i,
            "timestamp": timestamps[i],
            "decision_time": decision_time,
            "information_date": information_date,
            "selected": list(selected),
            "momentum_20d": momentum,
            "base_weights": base,
            "primary_weights": primary,
            "opposite_weights": opposite,
            "delayed_weights": delayed,
            "signed_scores": signed,
            "headline_counts": headlines,
            "active": any(abs(primary[symbol] - base[symbol]) > 1e-12 for symbol in SYMBOLS),
        })
    tilts = [row["primary_weights"][sorted(row["selected"])[0]] - 0.5 for row in rows]
    random.Random(SEED + 1).shuffle(tilts)
    for row, tilt in zip(rows, tilts, strict=True):
        first, second = sorted(row["selected"])
        row["shuffled_weights"] = {
            symbol: 0.5 + tilt if symbol == first else (0.5 - tilt if symbol == second else 0.0)
            for symbol in SYMBOLS
        }
    return {"timestamps": timestamps, "closes": closes, "rows": rows, "coverage": [coverage_start, coverage_end]}
