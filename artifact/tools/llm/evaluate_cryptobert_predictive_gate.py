"""Evaluate CryptoBERT daily scores against forward BTC returns before backtesting.

This gate is deliberately narrow: it consumes the frozen daily CryptoBERT score
artifact and timestamped BTCUSDT 4h bars, joins by a fixed delay/horizon policy,
and tests whether the score has positive out-of-sample directional evidence.
It does not search thresholds and does not run a trading backtest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path


UTC = timezone.utc
MODEL_ID = "ElKulako/cryptobert"
MODEL_REVISION = "9e37c910fe87727cb842a9ac55c6388256fe0f15"
CONTRACT_HASH = "c5aadbb2587e6c69fbe0b32f9c3fa774546be306ebf9b4814c5c48320d53ac48"
CONTRACT_VERSION = "cryptobert-social-sentiment-transfer-v1"


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denominator_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denominator_x == 0 or denominator_y == 0:
        return None
    return numerator / (denominator_x * denominator_y)


def ranks(values: list[float]) -> list[float]:
    ordered = sorted((value, index) for index, value in enumerate(values))
    result = [0.0] * len(values)
    position = 0
    while position < len(ordered):
        end = position + 1
        while end < len(ordered) and ordered[end][0] == ordered[position][0]:
            end += 1
        rank = (position + 1 + end) / 2
        for _, index in ordered[position:end]:
            result[index] = rank
        position = end
    return result


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def join_forward_returns(
    scores_payload: dict, bars: list[list[float]], delay_hours: int = 4, horizon_hours: int = 24,
) -> list[dict]:
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
            "score": float(record["score"]),
            "confidence": float(record["confidence"]),
            "forward_return": outcome_open / entry_open - 1,
            "execution_at": datetime.fromtimestamp(execution_ms / 1000, tz=UTC).isoformat(),
            "outcome_at": datetime.fromtimestamp(outcome_ms / 1000, tz=UTC).isoformat(),
        })
    return rows


def tercile_difference_bps(rows: list[dict]) -> tuple[float | None, int, int]:
    if len(rows) < 6:
        return None, 0, 0
    ordered = sorted(rows, key=lambda row: (row["score"], row["information_date"]))
    group_size = len(ordered) // 3
    bottom = ordered[:group_size]
    top = ordered[-group_size:]
    difference = (
        statistics.mean(row["forward_return"] for row in top)
        - statistics.mean(row["forward_return"] for row in bottom)
    ) * 10_000
    return difference, len(top), len(bottom)


def block_bootstrap(
    rows: list[dict], block_days: int = 7, samples: int = 10_000, seed: int = 20260816,
) -> dict:
    generator = random.Random(seed)
    starts = list(range(max(1, len(rows) - block_days + 1)))
    correlations: list[float] = []
    differences: list[float] = []
    for _ in range(samples):
        sampled: list[dict] = []
        while len(sampled) < len(rows):
            start = generator.choice(starts)
            sampled.extend(rows[start:start + block_days])
        sampled = sampled[:len(rows)]
        correlation = pearson([row["score"] for row in sampled], [row["forward_return"] for row in sampled])
        if correlation is not None:
            correlations.append(correlation)
        difference, _, _ = tercile_difference_bps(sampled)
        if difference is not None:
            differences.append(difference)
    return {
        "method": "moving-block percentile bootstrap",
        "block_days": block_days,
        "samples": samples,
        "seed": seed,
        "pearson_score_forward_return_95_ci": [percentile(correlations, 0.025), percentile(correlations, 0.975)],
        "top_minus_bottom_tercile_mean_bps_95_ci": [percentile(differences, 0.025), percentile(differences, 0.975)],
    }


def validate_scores(scores_payload: dict) -> None:
    model = scores_payload.get("model", {})
    summary = scores_payload.get("summary", {})
    if model.get("model_id") != MODEL_ID:
        raise ValueError("CryptoBERT model id does not match gate declaration")
    if model.get("revision") != MODEL_REVISION:
        raise ValueError("CryptoBERT revision does not match gate declaration")
    if scores_payload.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("CryptoBERT contract version does not match gate declaration")
    if scores_payload.get("contract_hash") != CONTRACT_HASH:
        raise ValueError("CryptoBERT contract hash does not match gate declaration")
    if scores_payload.get("status") != "full-inference-complete-predictive-gate-authorized":
        raise ValueError("CryptoBERT full inference has not authorized the predictive gate")
    if int(summary.get("errors", -1)) != 0:
        raise ValueError("full CryptoBERT inference contains errors")


def evaluate(scores_payload: dict, bars: list[list[float]]) -> dict:
    validate_scores(scores_payload)
    rows = join_forward_returns(scores_payload, bars)
    if not rows:
        raise ValueError("no CryptoBERT scores could be joined to forward returns")
    correlation = pearson([row["score"] for row in rows], [row["forward_return"] for row in rows])
    difference, top_count, bottom_count = tercile_difference_bps(rows)
    uncertainty = block_bootstrap(rows)
    pearson_ci = uncertainty["pearson_score_forward_return_95_ci"]
    tercile_ci = uncertainty["top_minus_bottom_tercile_mean_bps_95_ci"]
    passed = pearson_ci[0] > 0 and tercile_ci[0] > 0
    return {
        "schema_version": 1,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "experiment_id": "llm-cryptobert-predictive-gate-v1-development",
        "paper": scores_payload.get("paper"),
        "model": scores_payload.get("model"),
        "policy": {
            "execution_delay_hours": 4,
            "forward_horizon_hours": 24,
            "price_definition": "BTCUSDT open at available_at + 4h to open exactly 24 hours later",
            "score_definition": CONTRACT_VERSION,
            "parameter_search": False,
            "trading_backtest_consulted": False,
        },
        "observations": len(rows),
        "pearson_score_forward_return": correlation,
        "spearman_score_forward_return": pearson(
            ranks([row["score"] for row in rows]),
            ranks([row["forward_return"] for row in rows]),
        ),
        "top_minus_bottom_tercile_mean_bps": difference,
        "top_tercile_observations": top_count,
        "bottom_tercile_observations": bottom_count,
        "uncertainty": uncertainty,
        "checks": {
            "pearson_ci_lower_gt_zero": {"observed": pearson_ci[0], "required": "> 0", "passed": pearson_ci[0] > 0},
            "tercile_difference_ci_lower_gt_zero": {"observed": tercile_ci[0], "required": "> 0", "passed": tercile_ci[0] > 0},
        },
        "passed": passed,
        "status": (
            "stage2-pass-trading-rule-design-authorized"
            if passed
            else "stage2-fail-stop-before-threshold-selection-or-backtest"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--btc-bars", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scores_payload = json.loads(args.scores.read_text(encoding="utf-8"))
    bars = json.loads(args.btc_bars.read_text(encoding="utf-8"))
    payload = evaluate(scores_payload, bars)
    payload["inputs"] = {
        "scores": str(args.scores),
        "scores_sha256": file_hash(args.scores),
        "btc_bars": str(args.btc_bars),
        "btc_bars_sha256": file_hash(args.btc_bars),
    }
    write_atomic(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload.get("passed") else 2)


if __name__ == "__main__":
    main()
