"""Evaluate pinned FinBERT sentiment against forward BTC returns before any backtest."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from audit_llm_outcome_calibration import pearson, percentile, ranks
from llm_causal_pipeline import write_json

UTC = timezone.utc


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def join_forward_returns(
    scores_payload: dict, bars: list[list[float]], delay_hours: int = 4,
    horizon_hours: int = 24,
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
    rows: list[dict], block_days: int = 7, samples: int = 10_000,
    seed: int = 20260816,
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
        correlation = pearson(
            [row["score"] for row in sampled],
            [row["forward_return"] for row in sampled],
        )
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
        "pearson_score_forward_return_95_ci": [
            percentile(correlations, 0.025), percentile(correlations, 0.975)
        ],
        "top_minus_bottom_tercile_mean_bps_95_ci": [
            percentile(differences, 0.025), percentile(differences, 0.975)
        ],
    }


def evaluate(config: dict, scores_payload: dict, bars: list[list[float]]) -> dict:
    candidate = config["candidate"]
    contract = config["frozen_input_contract"]
    if scores_payload.get("model_digest") != candidate["digest"]:
        raise ValueError("FinBERT revision does not match predeclaration")
    if scores_payload.get("contract_hash") != contract["contract_hash"]:
        raise ValueError("FinBERT contract does not match predeclaration")
    if scores_payload["summary"]["errors"] != 0:
        raise ValueError("full FinBERT inference contains errors")

    rows = join_forward_returns(scores_payload, bars)
    if not rows:
        raise ValueError("no FinBERT scores could be joined to forward returns")
    correlation = pearson(
        [row["score"] for row in rows],
        [row["forward_return"] for row in rows],
    )
    difference, top_count, bottom_count = tercile_difference_bps(rows)
    uncertainty = block_bootstrap(rows)
    pearson_ci = uncertainty["pearson_score_forward_return_95_ci"]
    tercile_ci = uncertainty["top_minus_bottom_tercile_mean_bps_95_ci"]
    passed = pearson_ci[0] > 0 and tercile_ci[0] > 0
    return {
        "schema_version": 1,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "experiment_id": config["experiment_id"],
        "model": candidate,
        "policy": {
            "execution_delay_hours": 4,
            "forward_horizon_hours": 24,
            "price_definition": "BTCUSDT open at 04:00 UTC to open exactly 24 hours later",
            "score_definition": contract["contract_version"],
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
            "pearson_ci_lower_gt_zero": {
                "observed": pearson_ci[0], "required": "> 0", "passed": pearson_ci[0] > 0,
            },
            "tercile_difference_ci_lower_gt_zero": {
                "observed": tercile_ci[0], "required": "> 0", "passed": tercile_ci[0] > 0,
            },
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
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--btc-bars", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = evaluate(
        json.loads(args.config.read_text(encoding="utf-8")),
        json.loads(args.scores.read_text(encoding="utf-8")),
        json.loads(args.btc_bars.read_text(encoding="utf-8")),
    )
    payload["inputs"] = {
        "config": str(args.config), "config_sha256": file_hash(args.config),
        "scores": str(args.scores), "scores_sha256": file_hash(args.scores),
        "btc_bars": str(args.btc_bars), "btc_bars_sha256": file_hash(args.btc_bars),
    }
    write_json(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
