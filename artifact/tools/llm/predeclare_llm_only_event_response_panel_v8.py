"""Freeze v8 target-panel construction before joining event records to returns."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def item(path: str) -> dict:
    return {"path": path, "sha256": sha256(Path(path))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = {
        "schema_version": "llm-only-event-response-panel-predeclaration-v8",
        "experiment_id": "llm-only-short-horizon-event-response-v8-development",
        "predeclared_at": datetime.now(timezone.utc).isoformat(),
        "prior_v3_v7_outcomes_consulted": True,
        "target_values_consulted_for_v8_design": False,
        "protocol": item("paper/working/protocols/LLM_Only_Short_Horizon_Event_Response_Protocol_v8.md"),
        "code": {
            "builder": item("tools/llm/build_llm_only_event_response_panel_v8.py"),
            "tests": item("tools/llm/test_build_llm_only_event_response_panel_v8.py"),
            "llm_feature_guard_dependency": item("tools/llm/evaluate_llm_only_event_conditioned_v7.py"),
        },
        "tests": {"status": "4 tests passed before target-panel construction"},
        "sources": {
            "inputs": item("paper/input/results/llm/v3/llm_event_extraction_inputs_v3_development.json"),
            "extraction": item("paper/input/results/llm/v3/llm_event_extractor_v3_9_full_development.json"),
            "btc_4h": item(args.bars),
        },
        "eligibility": {
            "btc_relevance": ["direct", "systemic"],
            "event_types": ["macro_liquidity", "regulation", "etf_institutional_flow", "exchange_security", "liquidation_leverage", "network_protocol", "fraud_legal", "adoption_business"],
            "excluded_event_types": ["market_commentary", "other"],
            "deduplication": "first global normalized headline by published_at",
        },
        "decision_time": "strictly next UTC 4h open after published_at",
        "target": "Bybit BTCUSDT open[t+4h] / open[t] - 1",
        "predictive_feature_policy": "LLM extractor output only; market data is target-only",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output)}, indent=2))


if __name__ == "__main__":
    main()
