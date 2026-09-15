"""Compare repeated pinned-model scoring runs without consulting market outcomes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from llm_causal_pipeline import write_json


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_long(record: dict, long_threshold: float, minimum_confidence: float) -> bool:
    return (
        record.get("status") == "success"
        and float(record["score"]) >= long_threshold
        and float(record["confidence"]) >= minimum_confidence
    )


def audit(
    left: dict,
    right: dict,
    long_threshold: float = 0.30,
    minimum_confidence: float = 0.70,
) -> dict:
    for field in ("model_digest", "prompt_version", "prompt_hash"):
        if left.get(field) != right.get(field):
            raise ValueError(f"runs do not share pinned {field}")

    left_by_hash = {record["content_hash"]: record for record in left["records"]}
    right_by_hash = {record["content_hash"]: record for record in right["records"]}
    if len(left_by_hash) != len(left["records"]):
        raise ValueError("left run contains duplicate content hashes")
    if len(right_by_hash) != len(right["records"]):
        raise ValueError("right run contains duplicate content hashes")
    if set(left_by_hash) != set(right_by_hash):
        raise ValueError("runs do not contain identical information sets")

    pairs = [(left_by_hash[key], right_by_hash[key]) for key in sorted(left_by_hash)]
    successful_pairs = [
        (first, second)
        for first, second in pairs
        if first.get("status") == second.get("status") == "success"
    ]
    score_differences = [
        abs(float(first["score"]) - float(second["score"]))
        for first, second in successful_pairs
    ]
    confidence_differences = [
        abs(float(first["confidence"]) - float(second["confidence"]))
        for first, second in successful_pairs
    ]
    action_agreements = sum(
        is_long(first, long_threshold, minimum_confidence)
        == is_long(second, long_threshold, minimum_confidence)
        for first, second in pairs
    )
    action_disagreements = len(pairs) - action_agreements

    return {
        "schema_version": 2,
        "model": left["model"],
        "model_digest": left["model_digest"],
        "prompt_version": left["prompt_version"],
        "prompt_hash": left["prompt_hash"],
        "policy": {
            "long_threshold": long_threshold,
            "minimum_confidence": minimum_confidence,
            "market_outcomes_consulted": False,
        },
        "information_sets": len(pairs),
        "identical_information_set_hashes": True,
        "both_success": len(successful_pairs),
        "status_failures": len(pairs) - len(successful_pairs),
        "exact_score_agreement": sum(difference == 0 for difference in score_differences),
        "mean_absolute_score_difference": (
            sum(score_differences) / len(score_differences) if score_differences else None
        ),
        "max_absolute_score_difference": max(score_differences) if score_differences else None,
        "exact_confidence_agreement": sum(
            difference == 0 for difference in confidence_differences
        ),
        "mean_absolute_confidence_difference": (
            sum(confidence_differences) / len(confidence_differences)
            if confidence_differences
            else None
        ),
        "max_absolute_confidence_difference": (
            max(confidence_differences) if confidence_differences else None
        ),
        "long_flat_action_agreements": action_agreements,
        "long_flat_action_disagreements": action_disagreements,
        "long_flat_action_agreement_rate": (
            action_agreements / len(pairs) if pairs else None
        ),
        "score_deterministic": bool(score_differences) and max(score_differences) == 0,
        "action_deterministic": bool(pairs) and action_disagreements == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--long-threshold", type=float, default=0.30)
    parser.add_argument("--minimum-confidence", type=float, default=0.70)
    args = parser.parse_args()

    payload = audit(
        json.loads(args.left.read_text(encoding="utf-8")),
        json.loads(args.right.read_text(encoding="utf-8")),
        args.long_threshold,
        args.minimum_confidence,
    )
    payload["inputs"] = {
        "left": str(args.left),
        "left_sha256": file_hash(args.left),
        "right": str(args.right),
        "right_sha256": file_hash(args.right),
    }
    write_json(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
