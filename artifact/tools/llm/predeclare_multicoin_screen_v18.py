"""Freeze the outcome-free v18 multi-coin coverage screen."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from eth_transfer_v17_common import FOLDS, sha256, write_json
from multicoin_transfer_v18_common import ASSETS


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    output = root / "paper/input/results/llm/v18/llm_only_multicoin_screen_v18_predeclared.json"
    inputs = root / "paper/input/results/llm/v3/llm_event_extraction_inputs_v3_development.json"
    extraction = root / "paper/input/results/llm/v3/llm_event_extractor_v3_9_full_development.json"
    information_sets = root / "paper/input/results/llm/llm_daily_information_sets_multisource_v2_development.json"
    protocol = root / "paper/working/protocols/LLM_Only_Multicoin_Transfer_Protocol_v18.md"
    scripts = [
        root / "tools/llm/multicoin_transfer_v18_common.py",
        root / "tools/llm/audit_llm_only_multicoin_transfer_v18.py",
    ]
    payload = {
        "schema_version": 1,
        "family_id": "LLM-073--LLM-076-multicoin-transfer-v18",
        "stage": "PREDECLARED_BEFORE_OUTCOME_FREE_SCREEN",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "outcomes_consulted": False,
        "assets": {symbol: {"experiment_id": spec["experiment_id"], "aliases": sorted(spec["aliases"])} for symbol, spec in ASSETS.items()},
        "folds": FOLDS,
        "thresholds": {
            "minimum_direct_event_records": 1000,
            "minimum_direct_event_dates": 700,
            "minimum_event_dates_each_oos_fold": 100,
            "maximum_evidence_fallback_fraction": 0.05,
        },
        "sources": {
            "extraction_inputs": {"path": str(inputs), "sha256": sha256(inputs)},
            "extraction": {"path": str(extraction), "sha256": sha256(extraction)},
            "information_sets": {"path": str(information_sets), "sha256": sha256(information_sets)},
            "protocol": {"path": str(protocol), "sha256": sha256(protocol)},
            "scripts": [{"path": str(path), "sha256": sha256(path)} for path in scripts],
        },
        "next_authorized_action": "Run coverage/sample audit without price targets.",
    }
    write_json(output, payload)
    print(output)


if __name__ == "__main__":
    main()
