"""Regression checks for the HYB-003 text-state validator."""
from __future__ import annotations

import json

from score_tech_llm_text_state_v3 import parse_batch


def source() -> dict:
    return {
        "context_id": "c", "trade_id": "t", "symbol": "BTCUSDT",
        "decision_time_iso": "2025-01-01T00:00:00+00:00", "headline_id": "h",
        "available_at": "2025-01-01T00:00:00+00:00", "source_domain": "example.com",
        "headline": "Bitcoin shorts liquidated as price rises",
    }


def valid() -> dict:
    return {"records": [{
        "item_id": 0, "affected_asset_scope": "direct_held",
        "held_long_pressure": "supportive", "mechanism": "forced_short_buying",
        "event_stage": "initial_announcement",
        "horizon_mass": {"h4": 0.7, "h12": 0.2, "h24": 0.1, "h72": 0.0},
        "confidence": 0.9, "evidence_span": "Bitcoin shorts liquidated",
    }]}


def main() -> None:
    parsed = parse_batch(json.dumps(valid()), [source()])
    assert parsed[0]["held_long_pressure"] == "supportive"
    bad = valid()
    bad["records"][0]["held_long_pressure"] = "negative"
    try:
        parse_batch(json.dumps(bad), [source()])
    except ValueError:
        pass
    else:
        raise AssertionError("invalid pressure was accepted")
    bad = valid()
    bad["records"][0]["horizon_mass"]["h4"] = 0.6
    try:
        parse_batch(json.dumps(bad), [source()])
    except ValueError:
        pass
    else:
        raise AssertionError("non-unit horizon mass was accepted")
    print("text-state validator regression checks passed")


if __name__ == "__main__":
    main()
