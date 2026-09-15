"""Audit two v3.5 event-extractor runs and its flagged-fallback Stage 1 gate."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def jaccard(left: list[str], right: list[str]) -> float:
    a, b = set(left), set(right)
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def evaluate(config: dict, left: dict, right: dict) -> dict:
    required = config["stage1_gate"]["required"]
    expected = config["frozen_contract"]["stage1_sample"]["records"]
    lrows, rrows = left["records"], right["records"]
    paired = [
        (a, b) for a, b in zip(lrows, rrows)
        if a.get("status") == "success" and b.get("status") == "success"
        and a.get("headline_id") == b.get("headline_id")
    ]
    categorical = {}
    for key in ("btc_relevance", "event_type", "direction", "expected_horizon"):
        categorical[key] = sum(a[key] == b[key] for a, b in paired)
    continuous = {}
    all_differences = []
    for key in ("severity", "reported_surprise", "confidence"):
        differences = [abs(float(a[key]) - float(b[key])) for a, b in paired]
        all_differences.extend(differences)
        continuous[key] = {"mean_absolute_difference": mean(differences),
                           "max_absolute_difference": max(differences, default=0.0)}
    observed = {
        "records_left": len(lrows), "records_right": len(rrows),
        "schema_success_left": left["summary"]["success"],
        "schema_success_right": right["summary"]["success"],
        "headline_count_match_left": len(lrows), "headline_count_match_right": len(rrows),
        "headline_id_and_order_match_left": sum(
            row.get("headline_id") == other.get("headline_id") for row, other in zip(lrows, rrows)
        ),
        "headline_id_and_order_match_right": sum(
            row.get("headline_id") == other.get("headline_id") for row, other in zip(rrows, lrows)
        ),
        "evidence_exact_substring_left": left["summary"]["success"],
        "evidence_exact_substring_right": right["summary"]["success"],
        "evidence_fallbacks_left": left["summary"].get("evidence_fallbacks", 0),
        "evidence_fallbacks_right": right["summary"].get("evidence_fallbacks", 0),
        "paired_success": len(paired), "categorical_exact_agreement": categorical,
        "affected_assets_mean_jaccard": mean([jaccard(a["affected_assets"], b["affected_assets"]) for a, b in paired]),
        "continuous": continuous,
        "continuous_field_max_absolute_difference": max(all_differences, default=0.0),
    }
    checks = {
        "record_count": len(lrows) == expected and len(rrows) == expected,
        "schema_success": left["summary"]["success"] == required["schema_success_each_run"]
        and right["summary"]["success"] == required["schema_success_each_run"],
        "headline_count_match": len(lrows) == required["headline_count_match_each_run"]
        and len(rrows) == required["headline_count_match_each_run"],
        "headline_id_and_order_match": observed["headline_id_and_order_match_left"]
        == required["headline_id_and_order_match_each_run"],
        "evidence_exact_substring": observed["evidence_exact_substring_left"]
        == required["evidence_exact_substring_each_run"]
        and observed["evidence_exact_substring_right"] == required["evidence_exact_substring_each_run"],
        "evidence_fallback_limit": observed["evidence_fallbacks_left"]
        <= required["evidence_fallback_max_each_run"]
        and observed["evidence_fallbacks_right"] <= required["evidence_fallback_max_each_run"],
        "btc_relevance_agreement": categorical["btc_relevance"] >= required["btc_relevance_exact_agreement_min"],
        "event_type_agreement": categorical["event_type"] >= required["event_type_exact_agreement_min"],
        "direction_agreement": categorical["direction"] >= required["direction_exact_agreement_min"],
        "expected_horizon_agreement": categorical["expected_horizon"] >= required["expected_horizon_exact_agreement_min"],
        "affected_assets_jaccard": observed["affected_assets_mean_jaccard"] >= required["affected_assets_mean_jaccard_min"],
        "severity_difference": continuous["severity"]["mean_absolute_difference"] <= required["severity_mean_absolute_difference_max"],
        "reported_surprise_difference": continuous["reported_surprise"]["mean_absolute_difference"] <= required["reported_surprise_mean_absolute_difference_max"],
        "confidence_difference": continuous["confidence"]["mean_absolute_difference"] <= required["confidence_mean_absolute_difference_max"],
        "continuous_max_difference": observed["continuous_field_max_absolute_difference"] <= required["continuous_field_max_absolute_difference_max"],
    }
    passed = all(checks.values())
    return {
        "schema_version": 1, "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"], "outcomes_consulted": False,
        "trading_backtest_consulted": False, "observed": observed, "checks": checks,
        "passed": passed,
        "status": "stage1-pass-full-extraction-authorized" if passed else "stage1-fail-stop-before-full-extraction",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    left = json.loads(args.left.read_text(encoding="utf-8"))
    right = json.loads(args.right.read_text(encoding="utf-8"))
    result = evaluate(config, left, right)
    result["inputs"] = {key: {"path": str(path), "sha256": sha256(path)} for key, path in {
        "config": args.config, "left": args.left, "right": args.right,
    }.items()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
