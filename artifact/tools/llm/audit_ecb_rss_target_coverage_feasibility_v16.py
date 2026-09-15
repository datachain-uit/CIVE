#!/usr/bin/env python3
"""Outcome-free feasibility gate before downloading target values for ECB RSS v16."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREDECLARED = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_predictive_v16/predeclared.json"
EXTRACTION = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_predictive_v16/extraction/extraction.json"
EXTRACTION_GATE = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_predictive_v16/extraction_gate.json"
SOURCE_SCREEN = ROOT / "paper/input/references/source_artifacts/binance_vision_btcusdt_4h_v16/source_screen.json"
OUTPUT = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_predictive_v16/target_coverage_feasibility_gate.json"

ELIGIBLE_RELEVANCE = frozenset(("direct", "systemic"))
ELIGIBLE_EVENT_TYPES = frozenset((
    "macro_liquidity", "regulation", "etf_institutional_flow", "exchange_security",
    "liquidation_leverage", "network_protocol", "fraud_legal", "adoption_business",
))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    predeclared = json.loads(PREDECLARED.read_text(encoding="utf-8"))
    extraction = json.loads(EXTRACTION.read_text(encoding="utf-8"))
    extraction_gate = json.loads(EXTRACTION_GATE.read_text(encoding="utf-8"))
    source = json.loads(SOURCE_SCREEN.read_text(encoding="utf-8"))
    if extraction_gate.get("status") != "DATA_GATE_PASS_TARGET_JOIN_AUTHORIZED":
        raise ValueError("extraction gate has not authorized target join")
    if source.get("status") != "SOURCE_START_SCREEN_PASS" or source.get("first_available_month") != "2017-08":
        raise ValueError("Binance target source-start screen is not frozen as expected")
    eligible = [
        row for row in extraction["records"]
        if row["btc_relevance"] in ELIGIBLE_RELEVANCE and row["event_type"] in ELIGIBLE_EVENT_TYPES
    ]
    information_times = sorted({row["archive_capture_at"] for row in eligible})
    earliest_possible = "2017-08-01T00:00:00+00:00"
    potentially_targetable = [value for value in information_times if value >= earliest_possible]
    minimum = int(predeclared["data_gate"]["minimum_eligible_information_sets"])
    required_oos = int(predeclared["data_gate"]["required_oos_records"])
    feasible = len(potentially_targetable) >= minimum and len(potentially_targetable) >= required_oos
    checks = {
        "target_join_authorized": True,
        "source_start_frozen_without_market_values": source.get("market_values_downloaded") is False,
        "eligible_count_matches_extraction_gate": len(information_times) == extraction_gate["counts"]["eligible_information_sets"],
        "maximum_potential_target_sets_meet_minimum": len(potentially_targetable) >= minimum,
        "maximum_potential_target_sets_meet_required_oos": len(potentially_targetable) >= required_oos,
        "no_market_values_downloaded": True,
        "no_predictive_metric_or_backtest_run": True,
    }
    status = "TARGET_COVERAGE_FEASIBILITY_PASS_CANDLE_DOWNLOAD_AUTHORIZED" if feasible else "TARGET_COVERAGE_FEASIBILITY_FAIL_STOP_BEFORE_CANDLE_DOWNLOAD"
    result = {
        "schema_version": "ecb-rss-binance-target-coverage-feasibility-v16",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "passed": feasible,
        "candle_download_authorized": feasible,
        "target_panel_authorized": feasible,
        "predictive_gate_authorized": False,
        "counts": {
            "eligible_information_sets": len(information_times),
            "before_first_available_month": len(information_times) - len(potentially_targetable),
            "maximum_potentially_targetable_information_sets": len(potentially_targetable),
            "minimum_information_sets": minimum,
            "shortfall_to_minimum": max(0, minimum - len(potentially_targetable)),
            "required_oos_predictions": required_oos,
            "shortfall_to_required_oos": max(0, required_oos - len(potentially_targetable)),
        },
        "source_start": {"first_available_month": source["first_available_month"], "lower_bound_utc": earliest_possible},
        "checks": checks,
        "inputs": {
            name: {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(path)}
            for name, path in (("predeclared", PREDECLARED), ("extraction", EXTRACTION), ("extraction_gate", EXTRACTION_GATE), ("source_screen", SOURCE_SCREEN), ("auditor", Path(__file__)))
        },
        "interpretation": (
            "This is an optimistic upper-bound feasibility test: every eligible information set on or after the first available month is treated as targetable. "
            "Failure therefore cannot be repaired by downloading candle values and requires stopping before target construction and predictive evaluation."
        ),
        "outcomes_consulted": False,
        "market_values_downloaded": False,
        "trading_backtest_consulted": False,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if feasible:
        return
    raise SystemExit(2)


if __name__ == "__main__":
    main()
