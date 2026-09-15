"""Audit fixed LLM scores against subsequent BTC returns without parameter search."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from llm_causal_pipeline import write_json

UTC = timezone.utc


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2:
        return None
    lm, rm = statistics.mean(left), statistics.mean(right)
    numerator = sum((a - lm) * (b - rm) for a, b in zip(left, right))
    denominator = math.sqrt(sum((a - lm) ** 2 for a in left) * sum((b - rm) ** 2 for b in right))
    return numerator / denominator if denominator else None


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        average_rank = (start + end - 1) / 2 + 1
        for index in order[start:end]:
            result[index] = average_rank
        start = end
    return result


def summarize(rows: list[dict], long_threshold: float, minimum_confidence: float) -> dict:
    scores = [row["score"] for row in rows]
    returns = [row["forward_return"] for row in rows]
    long_rows = [row for row in rows if row["score"] >= long_threshold and row["confidence"] >= minimum_confidence]
    flat_rows = [row for row in rows if row not in long_rows]
    signed = [row for row in rows if row["score"] != 0]

    def group(items: list[dict]) -> dict:
        values = [item["forward_return"] for item in items]
        return {
            "observations": len(values),
            "mean_forward_return_pct": statistics.mean(values) * 100 if values else None,
            "median_forward_return_pct": statistics.median(values) * 100 if values else None,
            "positive_rate": sum(value > 0 for value in values) / len(values) if values else None,
        }

    long_summary, flat_summary = group(long_rows), group(flat_rows)
    long_mean = long_summary["mean_forward_return_pct"]
    flat_mean = flat_summary["mean_forward_return_pct"]
    return {
        "observations": len(rows),
        "pearson_score_forward_return": pearson(scores, returns),
        "spearman_score_forward_return": pearson(ranks(scores), ranks(returns)),
        "signed_direction_accuracy": (
            sum((row["score"] > 0) == (row["forward_return"] > 0) for row in signed) / len(signed)
            if signed else None
        ),
        "long_rule": long_summary,
        "flat_rule": flat_summary,
        "long_minus_flat_mean_bps": (long_mean - flat_mean) * 100 if long_mean is not None and flat_mean is not None else None,
    }


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def block_bootstrap(rows: list[dict], long_threshold: float, minimum_confidence: float,
                    block_days: int = 7, samples: int = 10_000, seed: int = 20260814) -> dict:
    generator = random.Random(seed)
    starts = list(range(max(1, len(rows) - block_days + 1)))
    differences: list[float] = []
    correlations: list[float] = []
    for _ in range(samples):
        sampled: list[dict] = []
        while len(sampled) < len(rows):
            start = generator.choice(starts)
            sampled.extend(rows[start:start + block_days])
        sampled = sampled[:len(rows)]
        long_returns = [item["forward_return"] for item in sampled
                        if item["score"] >= long_threshold and item["confidence"] >= minimum_confidence]
        flat_returns = [item["forward_return"] for item in sampled
                        if not (item["score"] >= long_threshold and item["confidence"] >= minimum_confidence)]
        if long_returns and flat_returns:
            differences.append((statistics.mean(long_returns) - statistics.mean(flat_returns)) * 10_000)
        correlation = pearson([item["score"] for item in sampled], [item["forward_return"] for item in sampled])
        if correlation is not None:
            correlations.append(correlation)
    return {
        "method": "moving-block percentile bootstrap",
        "block_days": block_days,
        "samples": samples,
        "seed": seed,
        "long_minus_flat_mean_bps_95_ci": (
            [percentile(differences, 0.025), percentile(differences, 0.975)] if differences else None
        ),
        "pearson_score_forward_return_95_ci": (
            [percentile(correlations, 0.025), percentile(correlations, 0.975)] if correlations else None
        ),
    }


def audit(scores_payload: dict, bars: list[list[float]], long_threshold: float = 0.30,
          minimum_confidence: float = 0.70, delay_hours: int = 4, horizon_hours: int = 24) -> dict:
    by_time = {int(row[0]): row for row in bars}
    rows: list[dict] = []
    for record in scores_payload["records"]:
        if record.get("status") != "success":
            continue
        available = datetime.fromisoformat(record["available_at"]).astimezone(UTC)
        execution_ms = int((available + timedelta(hours=delay_hours)).timestamp() * 1000)
        outcome_ms = execution_ms + horizon_hours * 60 * 60 * 1000
        if execution_ms not in by_time or outcome_ms not in by_time:
            continue
        entry_open = float(by_time[execution_ms][1])
        outcome_open = float(by_time[outcome_ms][1])
        rows.append({
            "information_date": record["information_date"],
            "execution_at": datetime.fromtimestamp(execution_ms / 1000, tz=UTC).isoformat(),
            "outcome_at": datetime.fromtimestamp(outcome_ms / 1000, tz=UTC).isoformat(),
            "score": float(record["score"]),
            "confidence": float(record["confidence"]),
            "forward_return": outcome_open / entry_open - 1,
        })
    by_year: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_year[row["execution_at"][:4]].append(row)
    result = {
        "schema_version": 1,
        "status": "development-calibration-not-freeze-evidence",
        "policy": {
            "execution_delay_hours": delay_hours,
            "forward_horizon_hours": horizon_hours,
            "price_definition": "BTCUSDT open at execution timestamp to open exactly 24h later",
            "long_threshold": long_threshold,
            "minimum_confidence": minimum_confidence,
            "parameter_search": False,
        },
        "coverage_start": rows[0]["execution_at"] if rows else None,
        "coverage_end": rows[-1]["outcome_at"] if rows else None,
        "overall": summarize(rows, long_threshold, minimum_confidence),
        "by_year": {year: summarize(items, long_threshold, minimum_confidence) for year, items in sorted(by_year.items())},
    }
    result["uncertainty"] = block_bootstrap(rows, long_threshold, minimum_confidence)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--btc-bars", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = audit(
        json.loads(args.scores.read_text(encoding="utf-8")),
        json.loads(args.btc_bars.read_text(encoding="utf-8")),
    )
    payload["inputs"] = {
        "scores": str(args.scores), "scores_sha256": file_hash(args.scores),
        "btc_bars": str(args.btc_bars), "btc_bars_sha256": file_hash(args.btc_bars),
    }
    write_json(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
