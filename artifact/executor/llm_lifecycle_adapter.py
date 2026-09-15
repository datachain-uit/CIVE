"""Translate causal daily LLM assessments into lifecycle-engine target schedules."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from llm_causal_pipeline import write_json

UTC = timezone.utc


def build_targets(
    scored_payload: dict,
    lifecycle_manifest: dict,
    long_threshold: float = 0.30,
    minimum_confidence: float = 0.70,
    decision_delay_hours: int = 4,
) -> dict:
    if decision_delay_hours < 0:
        raise ValueError("decision delay must be non-negative")
    membership = {
        int(timestamp): set(symbols)
        for timestamp, symbols in lifecycle_manifest["daily_membership"].items()
    }
    records = sorted(scored_payload["records"], key=lambda item: item["available_at"])
    records_by_day = {
        int(datetime.fromisoformat(item["available_at"]).astimezone(UTC).timestamp() * 1000): item
        for item in records
    }
    targets: dict[str, list[str]] = {}
    decisions: list[dict] = []
    for day_ms in sorted(membership):
        available = datetime.fromtimestamp(day_ms / 1000, tz=UTC)
        record = records_by_day.get(day_ms)
        execution = available + timedelta(hours=decision_delay_hours)
        execution_ms = int(execution.timestamp() * 1000)
        successful = record is not None and record.get("status") == "success"
        score = record.get("score") if record else None
        confidence = record.get("confidence") if record else None
        eligible = (
            successful and score is not None and confidence is not None
            and float(score) >= long_threshold
            and float(confidence) >= minimum_confidence
            and "BTCUSDT" in membership.get(day_ms, set())
        )
        symbols = ["BTCUSDT"] if eligible else []
        targets[str(execution_ms)] = symbols
        decisions.append({
            "information_date": record.get("information_date") if record else None,
            "available_at": available.isoformat(),
            "execution_at": execution.isoformat(),
            "score": score,
            "confidence": confidence,
            "status": record.get("status") if record else "missing",
            "targets": symbols,
            "content_hash": record.get("content_hash") if record else None,
        })
    return {
        "schema_version": 1,
        "strategy": "llm-only-btc-long-flat-v1-development",
        "status": "development-not-frozen",
        "model": scored_payload.get("model"),
        "model_digest": scored_payload.get("model_digest"),
        "prompt_version": scored_payload.get("prompt_version"),
        "policy": {
            "instrument": "BTCUSDT",
            "long_threshold": long_threshold,
            "minimum_confidence": minimum_confidence,
            "decision_delay_hours": decision_delay_hours,
            "missing_or_error": "flat",
            "positioning": "long-or-flat; no technical entry filter",
            "threshold_selection": "predeclared before outcome backtest; not optimized on returns",
        },
        "summary": {
            "decisions": len(decisions),
            "long_decisions": sum(bool(item["targets"]) for item in decisions),
            "flat_decisions": sum(not item["targets"] for item in decisions),
        },
        "targets": targets,
        "decisions": decisions,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--lifecycle-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--long-threshold", type=float, default=0.30)
    parser.add_argument("--minimum-confidence", type=float, default=0.70)
    parser.add_argument("--decision-delay-hours", type=int, default=4)
    args = parser.parse_args()
    payload = build_targets(
        json.loads(args.scores.read_text(encoding="utf-8")),
        json.loads(args.lifecycle_manifest.read_text(encoding="utf-8")),
        args.long_threshold,
        args.minimum_confidence,
        args.decision_delay_hours,
    )
    write_json(args.output, payload)
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
