"""Build a conservative two-run LLM consensus without consulting market outcomes."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from llm_causal_pipeline import write_json


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(left: dict, right: dict, long_threshold: float = 0.30,
          minimum_confidence: float = 0.70) -> dict:
    for field in ("model_digest", "prompt_version", "prompt_hash"):
        if left.get(field) != right.get(field):
            raise ValueError(f"component runs disagree on {field}")
    left_by_hash = {item["content_hash"]: item for item in left["records"]}
    right_by_hash = {item["content_hash"]: item for item in right["records"]}
    if set(left_by_hash) != set(right_by_hash):
        raise ValueError("component runs do not contain identical information sets")

    records: list[dict] = []
    component_action_agreements = 0
    component_action_disagreements = 0
    for digest in sorted(left_by_hash, key=lambda key: left_by_hash[key]["available_at"]):
        first, second = left_by_hash[digest], right_by_hash[digest]
        if first["available_at"] != second["available_at"]:
            raise ValueError(f"availability mismatch for {digest}")
        both_success = first.get("status") == second.get("status") == "success"
        first_action = (
            first.get("status") == "success" and float(first["score"]) >= long_threshold
            and float(first["confidence"]) >= minimum_confidence
        )
        second_action = (
            second.get("status") == "success" and float(second["score"]) >= long_threshold
            and float(second["confidence"]) >= minimum_confidence
        )
        if first_action == second_action:
            component_action_agreements += 1
        else:
            component_action_disagreements += 1
        if both_success:
            score = min(float(first["score"]), float(second["score"]))
            confidence = min(float(first["confidence"]), float(second["confidence"]))
            status, error = "success", None
        else:
            score, confidence, status = None, None, "error"
            error = "one-or-more-component-runs-failed"
        records.append({
            "content_hash": digest,
            "information_date": first["information_date"],
            "available_at": first["available_at"],
            "source_snapshot_hash": first["source_snapshot_hash"],
            "article_count": first["article_count"],
            "selected_article_count": first["selected_article_count"],
            "status": status,
            "score": score,
            "confidence": confidence,
            "reason_code": "dual-run-minimum-consensus" if both_success else None,
            "error": error,
            "component_scores": [first.get("score"), second.get("score")],
            "component_confidences": [first.get("confidence"), second.get("confidence")],
            "component_actions": [first_action, second_action],
        })
    model_digest = hashlib.sha256(
        f"dual-run-minimum|{left['model_digest']}|{left['prompt_hash']}".encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": "dual-run-consensus-v1-development",
        "model": f"dual-run-minimum:{left['model']}",
        "model_digest": model_digest,
        "component_model_digest": left["model_digest"],
        "prompt_version": left["prompt_version"],
        "prompt_hash": left["prompt_hash"],
        "policy": {
            "long_threshold": long_threshold,
            "minimum_confidence": minimum_confidence,
            "combination": "minimum score and minimum confidence",
            "disagreement_missing_or_error": "flat",
            "return_optimized": False,
        },
        "records": records,
        "summary": {
            "records": len(records),
            "success": sum(item["status"] == "success" for item in records),
            "errors": sum(item["status"] == "error" for item in records),
            "component_action_agreements": component_action_agreements,
            "component_action_disagreements": component_action_disagreements,
            "consensus_long": sum(
                item["status"] == "success" and item["score"] >= long_threshold
                and item["confidence"] >= minimum_confidence for item in records
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build(
        json.loads(args.left.read_text(encoding="utf-8")),
        json.loads(args.right.read_text(encoding="utf-8")),
    )
    payload["inputs"] = {
        "left": str(args.left), "left_sha256": file_hash(args.left),
        "right": str(args.right), "right_sha256": file_hash(args.right),
    }
    write_json(args.output, payload)
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
