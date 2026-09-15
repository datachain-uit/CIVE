"""Causal population and feature helpers for HYB-008."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SYMBOLS = ("ETHUSDT", "SOLUSDT")
BAR_MS = 4 * 60 * 60 * 1000


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selection_map(tech_rows):
    return {(date.fromisoformat(r["information_date"]) + timedelta(days=1)).isoformat(): list(r["selected"]) for r in tech_rows}


def open_returns(opens, ts, count):
    values = []
    for lag in range(count, 0, -1):
        a, b = ts - lag * BAR_MS, ts - (lag - 1) * BAR_MS
        if a not in opens or b not in opens:
            return None
        values.append(opens[b] / opens[a] - 1.0)
    return values


def tech_features(symbol, ts, selected, opens):
    history = open_returns(opens, ts, 18)
    if history is None:
        return None
    past = [opens[ts - lag * BAR_MS] for lag in range(18, -1, -1)]
    mean6 = sum(history[-6:]) / 6
    mean18 = sum(history) / 18
    vol6 = math.sqrt(sum((x - mean6) ** 2 for x in history[-6:]) / 6)
    vol18 = math.sqrt(sum((x - mean18) ** 2 for x in history) / 18)
    return {
        "tech_asset_sol": float(symbol == "SOLUSDT"),
        "tech_rank_first": float(selected.index(symbol) == 0),
        "tech_open_momentum_1": past[-1] / past[-2] - 1.0,
        "tech_open_momentum_6": past[-1] / past[-7] - 1.0,
        "tech_open_momentum_18": past[-1] / past[0] - 1.0,
        "tech_realized_vol_6": vol6,
        "tech_realized_vol_18": vol18,
        "tech_drawdown_18": past[-1] / max(past) - 1.0,
    }


def build_population(panel, tech, bars, include_target=False):
    selected = selection_map(tech["rows"])
    output = []
    for symbol in SYMBOLS:
        opens = {int(r[0]): float(r[1]) for r in bars[symbol]}
        for source in panel["assets"][symbol]["records"]:
            when = datetime.fromisoformat(source["decision_at"]).astimezone(timezone.utc)
            chosen = selected.get(when.date().isoformat(), [])
            if symbol not in chosen:
                continue
            tech_x = tech_features(symbol, int(when.timestamp() * 1000), chosen, opens)
            if tech_x is None:
                continue
            row = {
                "symbol": symbol,
                "decision_at": when.isoformat(),
                "utc_date": when.date().isoformat(),
                "tech": tech_x,
                "metadata": dict(source["features"]["metadata"]),
                "generic": dict(source["features"]["generic"]),
                "event": dict(source["features"]["event"]),
                "event_count": int(source["event_count"]),
            }
            if include_target:
                row["target_h4_return"] = float(source["target_h4_return"])
            output.append(row)
    return sorted(output, key=lambda r: (r["decision_at"], r["symbol"]))
