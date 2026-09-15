"""HYB-003 v3.1 scorer: exact-decimal repair for the frozen horizon tolerance."""
from __future__ import annotations

import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import score_tech_llm_text_state_v3 as v3


def validate_item(item: Any, expected: dict[str, Any], ordinal: int) -> dict[str, Any]:
    if not isinstance(item, dict) or set(item) != v3.OUTPUT_KEYS:
        raise ValueError("output keys do not match frozen text-state contract")
    if item["item_id"] != ordinal:
        raise ValueError("item_id/order mismatch")
    if item["affected_asset_scope"] not in v3.SCOPES:
        raise ValueError("invalid affected_asset_scope")
    if item["held_long_pressure"] not in v3.PRESSURES:
        raise ValueError("invalid held_long_pressure")
    if item["mechanism"] not in v3.MECHANISMS:
        raise ValueError("invalid mechanism")
    if item["event_stage"] not in v3.STAGES:
        raise ValueError("invalid event_stage")
    horizon = item["horizon_mass"]
    if not isinstance(horizon, dict) or set(horizon) != {"h4", "h12", "h24", "h72"}:
        raise ValueError("invalid horizon_mass keys")
    for key, value in horizon.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            raise ValueError(f"invalid horizon_mass.{key}")
    total = sum((Decimal(str(value)) for value in horizon.values()), Decimal("0"))
    if abs(total - Decimal("1")) > Decimal("0.001"):
        raise ValueError("horizon_mass must sum to one within exact decimal tolerance 0.001")
    confidence = item["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        raise ValueError("invalid confidence")
    evidence = item["evidence_span"]
    if not isinstance(evidence, str) or not evidence or len(evidence) > 240:
        raise ValueError("invalid evidence_span")
    aligned, fallback = v3.align_evidence(expected["headline"], evidence)
    return {
        "context_id": expected["context_id"], "trade_id": expected["trade_id"],
        "symbol": expected["symbol"], "decision_time_iso": expected["decision_time_iso"],
        "headline_id": expected["headline_id"], "available_at": expected["available_at"],
        "source_domain": expected["source_domain"], "headline": expected["headline"],
        **{key: value for key, value in item.items() if key != "item_id"},
        "evidence_span": aligned, "evidence_fallback": fallback,
    }


def verify_frozen_base() -> None:
    try:
        config_path = Path(sys.argv[sys.argv.index("--config") + 1])
    except (ValueError, IndexError) as exc:
        raise ValueError("--config is required") from exc
    config = json.loads(config_path.read_text(encoding="utf-8"))
    frozen = config["frozen_contract"]["base_postprocessor"]
    path = Path(frozen["path"])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != frozen["sha256"]:
        raise ValueError("base postprocessor hash differs from v3.1 predeclaration")


if __name__ == "__main__":
    verify_frozen_base()
    v3.validate_item = validate_item
    v3.main()
