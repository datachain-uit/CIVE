"""Audit the completed v3.3 full extraction without consulting outcomes."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from score_llm_event_extractor_v3 import sha256, write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--extraction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    source = json.loads(args.input.read_text(encoding="utf-8"))["records"]
    extraction = json.loads(args.extraction.read_text(encoding="utf-8"))
    records = extraction.get("records", [])
    required = config["completion_gate"]["required"]
    success = sum(item.get("status") == "success" for item in records)
    errors = sum(item.get("status") == "error" for item in records)
    count_match = min(len(records), len(source)) if len(records) == len(source) else 0
    id_order_match = sum(
        result.get("headline_id") == expected["headline_id"]
        for result, expected in zip(records, source)
    )
    evidence_match = sum(
        result.get("status") == "success"
        and isinstance(result.get("evidence_span"), str)
        and result["evidence_span"] in expected["headline"]
        for result, expected in zip(records, source)
    )
    observed = {
        "records": len(records), "schema_success": success, "errors": errors,
        "headline_count_match": count_match,
        "headline_id_and_order_match": id_order_match,
        "evidence_exact_substring": evidence_match,
    }
    checks = {
        "schema_success": success == required["schema_success"],
        "errors": errors == required["errors"],
        "headline_count_match": count_match == required["headline_count_match"],
        "headline_id_and_order_match": id_order_match == required["headline_id_and_order_match"],
        "evidence_exact_substring": evidence_match == required["evidence_exact_substring"],
        "outcomes_not_consulted": extraction.get("outcomes_consulted") is False,
        "backtest_not_consulted": extraction.get("trading_backtest_consulted") is False,
    }
    passed = all(checks.values())
    write_json(args.output, {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "outcomes_consulted": False,
        "trading_backtest_consulted": False,
        "observed": observed,
        "checks": checks,
        "passed": passed,
        "status": "full-extraction-pass-downstream-design-authorized" if passed
                  else "full-extraction-fail-stop-before-downstream-design",
        "inputs": {
            "config": {"path": str(args.config.resolve()), "sha256": sha256(args.config)},
            "input": {"path": str(args.input.resolve()), "sha256": sha256(args.input)},
            "extraction": {"path": str(args.extraction.resolve()), "sha256": sha256(args.extraction)},
        },
    })
    print(json.dumps(json.loads(args.output.read_text(encoding="utf-8")), indent=2))


if __name__ == "__main__":
    main()
