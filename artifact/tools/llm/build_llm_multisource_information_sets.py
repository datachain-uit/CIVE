"""Build causal multi-source daily inputs with deterministic historical-case retrieval."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
FOUR_HOURS_MS = 4 * 60 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000
FEATURE_SCALES = {
    "btc_return_24h": 0.05,
    "btc_return_72h": 0.10,
    "btc_return_168h": 0.20,
    "btc_realized_vol_daily_7d": 0.05,
    "btc_volume_zscore_30d": 2.0,
    "btc_funding_24h": 0.001,
    "btc_funding_72h": 0.003,
    "cross_asset_mean_return_24h": 0.05,
    "cross_asset_breadth_24h": 1.0,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def pct(value: float | None) -> str:
    return "unavailable" if value is None else f"{value * 100:+.3f}%"


def number(value: float | None, digits: int = 4) -> str:
    return "unavailable" if value is None else f"{value:+.{digits}f}"


class BarSeries:
    def __init__(self, rows: list[list[float]]) -> None:
        self.by_time = {int(row[0]): row for row in rows}

    def completed(self, cutoff_ms: int, count: int) -> list[list[float]] | None:
        end = cutoff_ms - FOUR_HOURS_MS
        rows = [self.by_time.get(end - index * FOUR_HOURS_MS) for index in range(count)]
        return None if any(row is None for row in rows) else list(reversed(rows))

    def open_at(self, timestamp_ms: int) -> float | None:
        row = self.by_time.get(timestamp_ms)
        return float(row[1]) if row else None


def market_features(series: BarSeries, cutoff_ms: int) -> dict[str, float] | None:
    rows = series.completed(cutoff_ms, 181)
    if rows is None:
        return None
    closes = [float(row[4]) for row in rows]
    quote_volumes = [float(row[6]) for row in rows]
    returns = [math.log(closes[index] / closes[index - 1]) for index in range(1, len(closes))]
    daily_volumes = [sum(quote_volumes[-6 * day:-6 * (day - 1) if day > 1 else None]) for day in range(30, 0, -1)]
    current_volume = daily_volumes[-1]
    prior_volumes = daily_volumes[:-1]
    volume_std = statistics.pstdev(prior_volumes)
    return {
        "btc_return_24h": closes[-1] / closes[-7] - 1,
        "btc_return_72h": closes[-1] / closes[-19] - 1,
        "btc_return_168h": closes[-1] / closes[-43] - 1,
        "btc_realized_vol_daily_7d": statistics.pstdev(returns[-42:]) * math.sqrt(6),
        "btc_volume_zscore_30d": (
            (current_volume - statistics.mean(prior_volumes)) / volume_std if volume_std else 0.0
        ),
    }


def funding_features(funding: dict[str, float], cutoff_ms: int) -> dict[str, float] | None:
    timestamps = sorted(int(timestamp) for timestamp in funding if int(timestamp) <= cutoff_ms)
    if not timestamps:
        return None

    def values_since(hours: int) -> list[float]:
        start = cutoff_ms - hours * 60 * 60 * 1000
        index = bisect_right(timestamps, start)
        return [float(funding[str(timestamp)]) for timestamp in timestamps[index:]]

    one_day = values_since(24)
    three_days = values_since(72)
    if not one_day or not three_days:
        return None
    return {
        "btc_funding_latest": float(funding[str(timestamps[-1])]),
        "btc_funding_24h": sum(one_day),
        "btc_funding_72h": sum(three_days),
    }


def cross_asset_features(series_by_symbol: dict[str, BarSeries], members: list[str], cutoff_ms: int) -> dict | None:
    returns: dict[str, float] = {}
    for symbol in members:
        series = series_by_symbol.get(symbol)
        rows = series.completed(cutoff_ms, 7) if series else None
        if rows:
            returns[symbol] = float(rows[-1][4]) / float(rows[0][4]) - 1
    if len(returns) < 3:
        return None
    values = list(returns.values())
    return {
        "cross_asset_members": sorted(returns),
        "cross_asset_returns_24h": {key: returns[key] for key in sorted(returns)},
        "cross_asset_mean_return_24h": statistics.mean(values),
        "cross_asset_breadth_24h": sum(value > 0 for value in values) / len(values),
        "cross_asset_dispersion_24h": statistics.pstdev(values),
    }


def outcome(series: BarSeries, available_ms: int, delay_hours: int, horizon_hours: int) -> dict | None:
    execution_ms = available_ms + delay_hours * 60 * 60 * 1000
    outcome_ms = execution_ms + horizon_hours * 60 * 60 * 1000
    entry, exit_price = series.open_at(execution_ms), series.open_at(outcome_ms)
    if entry is None or exit_price is None:
        return None
    return {"outcome_at_ms": outcome_ms, "forward_return": exit_price / entry - 1}


def feature_distance(left: dict, right: dict) -> float:
    terms = []
    for key, scale in FEATURE_SCALES.items():
        if key in left and key in right:
            terms.append(((float(left[key]) - float(right[key])) / scale) ** 2)
    return math.sqrt(sum(terms) / len(terms)) if terms else math.inf


def retrieve_cases(current: dict, history: list[dict], cutoff_ms: int, maximum: int) -> list[dict]:
    eligible = [item for item in history if item["outcome_at_ms"] <= cutoff_ms]
    ranked = sorted(eligible, key=lambda item: (feature_distance(current, item["features"]), item["information_date"]))
    return [{
        "information_date": item["information_date"],
        "distance": feature_distance(current, item["features"]),
        "known_at": datetime.fromtimestamp(item["outcome_at_ms"] / 1000, UTC).isoformat(),
        "forward_return": item["forward_return"],
        "headline_excerpt": item["headline_excerpt"],
    } for item in ranked[:maximum]]


def prompt_text(record: dict, cases: list[dict], delay_hours: int, horizon_hours: int) -> str:
    features = record["features"]
    members = ", ".join(features["cross_asset_members"])
    returns = ", ".join(
        f"{symbol}={pct(value)}" for symbol, value in features["cross_asset_returns_24h"].items()
    )
    memory = "\n".join(
        f"- {case['information_date']} | distance={case['distance']:.3f} | "
        f"known outcome={pct(case['forward_return'])} | headlines: {case['headline_excerpt']}"
        for case in cases
    ) or "- No eligible historical case yet."
    return (
        "FORECAST CONTRACT\n"
        f"- Data cutoff: {record['available_at']}\n"
        f"- Execution: BTCUSDT open {delay_hours} hours after cutoff.\n"
        f"- Target: BTCUSDT open-to-open return over the next {horizon_hours} hours.\n"
        "- Historical cases are analogies with outcomes already known at cutoff, not labels.\n\n"
        "MARKET STATE (completed data only)\n"
        f"- BTC return: 24h={pct(features['btc_return_24h'])}; 72h={pct(features['btc_return_72h'])}; "
        f"7d={pct(features['btc_return_168h'])}.\n"
        f"- BTC 7d realized daily volatility={pct(features['btc_realized_vol_daily_7d'])}; "
        f"24h quote-volume z-score={number(features['btc_volume_zscore_30d'])}.\n\n"
        "DERIVATIVES STATE\n"
        f"- BTC funding: latest={pct(features['btc_funding_latest'])}; "
        f"24h cumulative={pct(features['btc_funding_24h'])}; 72h cumulative={pct(features['btc_funding_72h'])}.\n\n"
        "POINT-IN-TIME CROSS-ASSET STATE\n"
        f"- Members: {members}.\n- 24h returns: {returns}.\n"
        f"- Mean={pct(features['cross_asset_mean_return_24h'])}; "
        f"positive breadth={features['cross_asset_breadth_24h']:.3f}; "
        f"dispersion={pct(features['cross_asset_dispersion_24h'])}.\n\n"
        "CAUSAL CASE MEMORY\n" + memory + "\n\n"
        "CURRENT COMPLETED-DAY HEADLINES\n" + record["headline_text"]
    )


def load_symbol_series(directory: Path) -> dict[str, BarSeries]:
    result: dict[str, BarSeries] = {}
    for path in directory.glob("*.json"):
        symbol = path.name.split("_", 1)[0]
        result[symbol] = BarSeries(json.loads(path.read_text(encoding="utf-8")))
    return result


def build(input_path: Path, bars_directory: Path, funding_path: Path, universe_path: Path,
          output_path: Path, memory_cases: int = 3, delay_hours: int = 4,
          horizon_hours: int = 24) -> dict:
    source = json.loads(input_path.read_text(encoding="utf-8"))
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    funding = json.loads(funding_path.read_text(encoding="utf-8"))
    series_by_symbol = load_symbol_series(bars_directory)
    btc = series_by_symbol.get("BTCUSDT")
    if btc is None:
        raise ValueError("BTCUSDT bars are required")

    prepared: list[dict] = []
    history: list[dict] = []
    skipped: dict[str, int] = {"market": 0, "funding": 0, "membership": 0, "outcome": 0}
    for source_record in source["records"]:
        available = datetime.fromisoformat(source_record["available_at"]).astimezone(UTC)
        available_ms = int(available.timestamp() * 1000)
        market = market_features(btc, available_ms)
        if market is None:
            skipped["market"] += 1
            continue
        derivatives = funding_features(funding, available_ms)
        if derivatives is None:
            skipped["funding"] += 1
            continue
        members = universe["daily_membership"].get(str(available_ms), [])
        cross_asset = cross_asset_features(series_by_symbol, members, available_ms)
        if cross_asset is None:
            skipped["membership"] += 1
            continue
        realized = outcome(btc, available_ms, delay_hours, horizon_hours)
        if realized is None:
            skipped["outcome"] += 1
            continue
        features = {**market, **derivatives, **cross_asset}
        cases = retrieve_cases(features, history, available_ms, memory_cases)
        record = {
            "information_date": source_record["information_date"],
            "available_at": source_record["available_at"],
            "source_snapshot_hash": source_record["source_snapshot_hash"],
            "article_count": source_record["article_count"],
            "selected_article_count": source_record["selected_article_count"],
            "selected_articles": source_record["selected_articles"],
            "headline_text": source_record["text"],
            "features": features,
            "retrieved_cases": cases,
        }
        record["text"] = prompt_text(record, cases, delay_hours, horizon_hours)
        del record["headline_text"]
        record["content_hash"] = canonical_hash({
            "information_date": record["information_date"], "available_at": record["available_at"],
            "text": record["text"], "features": features, "retrieved_cases": cases,
        })
        prepared.append(record)
        history.append({
            "information_date": record["information_date"], "features": features,
            "outcome_at_ms": realized["outcome_at_ms"], "forward_return": realized["forward_return"],
            "headline_excerpt": " | ".join(source_record["text"].splitlines()[:3]),
        })

    payload = {
        "schema_version": 2,
        "status": "development-not-frozen",
        "prompt_contract": "crypto-multisource-causal-memory-v2",
        "policy": {
            "cutoff": "00:00 UTC; only completed 4h bars and recorded funding at or before cutoff",
            "execution_delay_hours": delay_hours,
            "forward_horizon_hours": horizon_hours,
            "universe": "Bybit top-5 turnover point-in-time membership at cutoff",
            "memory": f"{memory_cases} nearest prior feature states with outcome_at <= current cutoff",
            "distance": "fixed predeclared feature scales; no full-sample normalization",
        },
        "sources": {
            "headline_information_sets": {"path": str(input_path), "sha256": sha256(input_path)},
            "bars_directory": str(bars_directory),
            "btc_funding": {"path": str(funding_path), "sha256": sha256(funding_path)},
            "lifecycle_universe": {"path": str(universe_path), "sha256": sha256(universe_path)},
        },
        "feature_scales": FEATURE_SCALES,
        "summary": {
            "source_records": len(source["records"]), "records": len(prepared),
            "coverage_start": prepared[0]["information_date"] if prepared else None,
            "coverage_end": prepared[-1]["information_date"] if prepared else None,
            "records_with_memory": sum(bool(item["retrieved_cases"]) for item in prepared),
            "skipped": skipped,
        },
        "records": prepared,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--bars-directory", type=Path, required=True)
    parser.add_argument("--btc-funding", type=Path, required=True)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--memory-cases", type=int, default=3)
    parser.add_argument("--delay-hours", type=int, default=4)
    parser.add_argument("--horizon-hours", type=int, default=24)
    args = parser.parse_args()
    payload = build(args.input, args.bars_directory, args.btc_funding, args.universe,
                    args.output, args.memory_cases, args.delay_hours, args.horizon_hours)
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
