"""Join frozen v11 LLM outputs to target-only BTC four-hour labels."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


FOUR_HOURS_MS = 14_400_000
EVENT_TYPES = ["rate_or_balance_sheet", "liquidity_or_emergency", "bank_capital_or_stress", "supervision_or_enforcement", "payments_or_access", "administrative_or_information", "other"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def next_4h_open_ms(value: str) -> int:
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        raise ValueError("published timestamp must be timezone aware")
    milliseconds = int(timestamp.astimezone(timezone.utc).timestamp() * 1000)
    return (milliseconds // FOUR_HOURS_MS + 1) * FOUR_HOURS_MS


def features(row: dict) -> tuple[dict[str, float], dict[str, float]]:
    generic = {
        "llm_generic_direction": float(row["generic_direction"]),
        "llm_generic_intensity": float(row["generic_intensity"]),
        "llm_generic_signed_intensity": float(row["generic_direction"]) * float(row["generic_intensity"]),
    }
    event = dict(generic)
    event.update({
        "llm_policy_direction": float(row["policy_direction"]),
        "llm_policy_intensity": float(row["policy_intensity"]),
        "llm_policy_signed_intensity": float(row["policy_direction"]) * float(row["policy_intensity"]),
        "llm_surprise_language": float(row["surprise_language"]),
        "llm_systemic_scope": float(row["systemic_scope"]),
        "llm_confidence": float(row["confidence"]),
    })
    for event_type in EVENT_TYPES:
        event[f"llm_event_type::{event_type}"] = float(row["event_type"] == event_type)
    return generic, event


def average(rows: list[dict[str, float]]) -> dict[str, float]:
    return {key: float(np.mean([row[key] for row in rows])) for key in rows[0]}


def build(events_path: Path, extraction_path: Path, bars_path: Path) -> tuple[dict, dict]:
    events = json.loads(events_path.read_text(encoding="utf-8"))
    extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
    if extraction["outcomes_consulted"] or extraction["summary"]["errors"]:
        raise ValueError("extraction is not an outcome-blind complete run")
    by_id = {row["event_id"]: row for row in extraction["records"]}
    if len(by_id) != len(events) or set(by_id) != {row["event_id"] for row in events}:
        raise ValueError("event/extraction coverage mismatch")
    bars = {int(row[0]): row for row in json.loads(bars_path.read_text(encoding="utf-8"))}
    grouped = defaultdict(list)
    for event in events:
        scored = by_id[event["event_id"]]
        generic, conditioned = features(scored)
        grouped[next_4h_open_ms(event["published_at_claimed_utc"])].append((event["event_id"], generic, conditioned))
    records, missing = [], 0
    for decision_ms in sorted(grouped):
        entry, exit_row = bars.get(decision_ms), bars.get(decision_ms + FOUR_HOURS_MS)
        if entry is None or exit_row is None:
            missing += 1
            continue
        bucket = grouped[decision_ms]
        records.append({
            "decision_at": datetime.fromtimestamp(decision_ms / 1000, timezone.utc).isoformat(),
            "target_h4_return": float(exit_row[1]) / float(entry[1]) - 1.0,
            "generic_features": average([row[1] for row in bucket]),
            "event_features": average([row[2] for row in bucket]),
            "event_ids": [row[0] for row in bucket],
        })
    panel = {
        "schema_version": "open-fed-policy-panel-v11", "status": "development-target-panel",
        "policy": {"predictive_inputs": "LLM output only", "market_data_role": "target only", "decision_time": "strictly next UTC 4h open", "target": "BTCUSDT open[t+4h]/open[t]-1"},
        "sources": {"events": {"path": str(events_path), "sha256": sha256(events_path)}, "extraction": {"path": str(extraction_path), "sha256": sha256(extraction_path)}, "btc_4h": {"path": str(bars_path), "sha256": sha256(bars_path)}},
        "records": records,
    }
    years = Counter(datetime.fromisoformat(row["decision_at"]).year for row in records)
    audit = {
        "schema_version": "open-fed-policy-panel-audit-v11", "source_events": len(events),
        "labeled_buckets": len(records), "missing_target_buckets": missing,
        "same_4h_events_collapsed": sum(len(rows) - 1 for rows in grouped.values()),
        "buckets_per_year": {str(year): years[year] for year in sorted(years)},
        "generic_feature_names": list(records[0]["generic_features"]), "event_feature_names": list(records[0]["event_features"]),
        "target_distribution_consulted": False,
    }
    return panel, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--extraction", type=Path, required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--panel-output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()
    panel, audit = build(args.events, args.extraction, args.bars)
    write_json(args.panel_output, panel)
    audit["panel"] = {"path": str(args.panel_output), "sha256": sha256(args.panel_output)}
    write_json(args.audit_output, audit)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
