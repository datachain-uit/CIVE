"""Regression checks for the HYB-003 v3.1 exact-decimal tolerance repair."""
from __future__ import annotations

import json

import score_tech_llm_text_state_v3 as v3
from score_tech_llm_text_state_v3_1 import validate_item


v3.validate_item = validate_item


def source() -> dict:
    return {
        "context_id": "c", "trade_id": "t", "symbol": "BTCUSDT",
        "decision_time_iso": "2025-01-01T00:00:00+00:00", "headline_id": "h",
        "available_at": "2025-01-01T00:00:00+00:00", "source_domain": "example.com",
        "headline": "Bitcoin shorts liquidated as price rises",
    }


def payload(h24: float) -> dict:
    return {"records": [{
        "item_id": 0, "affected_asset_scope": "direct_held",
        "held_long_pressure": "supportive", "mechanism": "forced_short_buying",
        "event_stage": "initial_announcement",
        "horizon_mass": {"h4": 0.0, "h12": 0.0, "h24": h24, "h72": 0.0},
        "confidence": 0.9, "evidence_span": "Bitcoin shorts liquidated",
    }]}


def main() -> None:
    assert v3.parse_batch(json.dumps(payload(1.0)), [source()])
    assert v3.parse_batch(json.dumps(payload(0.999)), [source()])
    try:
        v3.parse_batch(json.dumps(payload(0.998)), [source()])
    except ValueError:
        pass
    else:
        raise AssertionError("horizon error beyond 0.001 was accepted")
    print("text-state v3.1 exact-decimal regression checks passed")


if __name__ == "__main__":
    main()
