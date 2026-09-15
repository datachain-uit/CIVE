"""Outcome-blind completion audit for HYB-003 full text-state extraction."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


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
    paired = list(zip(records, source))
    success = sum(row.get("status") == "success" for row in records)
    errors = sum(row.get("status") == "error" for row in records)
    context_order = sum(a.get("context_id") == b.get("context_id") for a, b in paired)
    headline_order = sum(a.get("headline_id") == b.get("headline_id") for a, b in paired)
    evidence_exact = sum(
        a.get("status") == "success"
        and isinstance(a.get("evidence_span"), str)
        and a["evidence_span"] in b["headline"]
        for a, b in paired
    )
    fallbacks = sum(row.get("evidence_fallback") is True for row in records)
    observed = {
        "records": len(records), "schema_success": success, "errors": errors,
        "context_id_and_order_match": context_order,
        "headline_id_and_order_match": headline_order,
        "evidence_exact_substring": evidence_exact,
        "evidence_fallbacks": fallbacks,
    }
    checks = {
        "record_count": len(records) == len(source) == required["records"],
        "schema_success": success == required["schema_success"],
        "errors": errors == 0,
        "context_id_and_order": context_order == required["context_id_match"],
        "headline_id_and_order": headline_order == required["headline_id_match"],
        "evidence_exact_substring": evidence_exact == required["evidence_exact_substring"],
        "evidence_fallback_limit": fallbacks <= required["evidence_fallback_max"],
        "input_hash": sha256(args.input) == config["frozen_contract"]["full_input"]["sha256"],
        "outcomes_not_consulted": extraction.get("outcomes_consulted") is False,
    }
    passed = all(checks.values())
    write_json(args.output, {
        "schema_version": "tech-llm-text-state-full-gate-v3",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "outcomes_consulted": False,
        "trading_backtest_consulted": False,
        "observed": observed, "checks": checks, "passed": passed,
        "status": "full-extraction-pass-power-freeze-authorized" if passed
                  else "full-extraction-fail-stop-before-model-fit",
        "inputs": {
            "config": {"path": str(args.config.resolve()), "sha256": sha256(args.config)},
            "input": {"path": str(args.input.resolve()), "sha256": sha256(args.input)},
            "extraction": {"path": str(args.extraction.resolve()), "sha256": sha256(args.extraction)},
        },
    })
    print(json.dumps(json.loads(args.output.read_text(encoding="utf-8")), indent=2))
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
