"""Build the publication-time, four-hour event-response panel for v8."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from evaluate_llm_only_event_conditioned_v7 import (
    DIRECTION_SIGN,
    normalized_headline,
    write_json,
)


FOUR_HOURS_MS = 4 * 60 * 60 * 1000
ELIGIBLE_RELEVANCE = ("direct", "systemic")
ELIGIBLE_EVENT_TYPES = (
    "macro_liquidity",
    "regulation",
    "etf_institutional_flow",
    "exchange_security",
    "liquidation_leverage",
    "network_protocol",
    "fraud_legal",
    "adoption_business",
)
RELEVANCE_WEIGHT = {"direct": 1.0, "systemic": 0.75}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def next_4h_open_ms(timestamp: datetime) -> int:
    if timestamp.tzinfo is None:
        raise ValueError("published_at must include a timezone")
    value = int(timestamp.astimezone(timezone.utc).timestamp() * 1000)
    return ((value // FOUR_HOURS_MS) + 1) * FOUR_HOURS_MS


def llm_features(items: list[dict]) -> tuple[dict[str, float], dict[str, float]]:
    denominator = float(len(items))
    signs = np.asarray([DIRECTION_SIGN[item["direction"]] for item in items], dtype=float)
    severity = np.asarray([float(item["severity"]) for item in items], dtype=float)
    surprise = np.asarray([float(item["reported_surprise"]) for item in items], dtype=float)
    confidence = np.asarray([float(item["confidence"]) for item in items], dtype=float)
    sentiment = {
        "llm_sentiment_positive_fraction": sum(item["direction"] == "positive" for item in items) / denominator,
        "llm_sentiment_negative_fraction": sum(item["direction"] == "negative" for item in items) / denominator,
        "llm_sentiment_mixed_fraction": sum(item["direction"] == "mixed" for item in items) / denominator,
        "llm_sentiment_unclear_fraction": sum(item["direction"] == "unclear" for item in items) / denominator,
        "llm_sentiment_signed_mean": float(np.mean(signs)),
        "llm_sentiment_directional_severity_mean": float(np.mean(signs * severity)),
        "llm_sentiment_directional_confidence_mean": float(np.mean(signs * confidence)),
        "llm_sentiment_severity_mean": float(np.mean(severity)),
        "llm_sentiment_severity_max": float(np.max(severity)),
        "llm_sentiment_surprise_mean": float(np.mean(surprise)),
        "llm_sentiment_surprise_max": float(np.max(surprise)),
        "llm_sentiment_confidence_mean": float(np.mean(confidence)),
    }
    event = dict(sentiment)
    for relevance in ELIGIBLE_RELEVANCE:
        event[f"llm_event_relevance_fraction::{relevance}"] = sum(
            item["btc_relevance"] == relevance for item in items
        ) / denominator
    for event_type in ELIGIBLE_EVENT_TYPES:
        selected = [index for index, item in enumerate(items) if item["event_type"] == event_type]
        event[f"llm_event_type_fraction::{event_type}"] = len(selected) / denominator
        event[f"llm_event_impact::{event_type}"] = float(np.mean([
            signs[index] * severity[index] * surprise[index] * confidence[index]
            * RELEVANCE_WEIGHT[items[index]["btc_relevance"]]
            for index in selected
        ])) if selected else 0.0
    return sentiment, event


def build(inputs_path: Path, extraction_path: Path, bars_path: Path) -> tuple[dict, dict]:
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))["records"]
    events = json.loads(extraction_path.read_text(encoding="utf-8"))["records"]
    bars = json.loads(bars_path.read_text(encoding="utf-8"))
    input_by_id = {item["headline_id"]: item for item in inputs}
    if len(input_by_id) != len(inputs):
        raise ValueError("duplicate input headline_id")
    event_by_id = {item["headline_id"]: item for item in events}
    if len(event_by_id) != len(events) or set(event_by_id) != set(input_by_id):
        raise ValueError("event/input coverage mismatch")
    rows_by_time = {int(row[0]): row for row in bars}

    groups: dict[int, list[dict]] = defaultdict(list)
    seen_headlines: set[str] = set()
    duplicate_count = 0
    excluded_relevance = 0
    excluded_event_type = 0
    type_counts: Counter[str] = Counter()
    relevance_counts: Counter[str] = Counter()
    ordered_inputs = sorted(inputs, key=lambda item: (
        datetime.fromisoformat(item["published_at"]).astimezone(timezone.utc),
        item["headline_id"],
    ))
    for source in ordered_inputs:
        normalized = normalized_headline(source["headline"])
        if normalized in seen_headlines:
            duplicate_count += 1
            continue
        seen_headlines.add(normalized)
        event = event_by_id[source["headline_id"]]
        if event.get("status") != "success" or event.get("error") is not None:
            raise ValueError("all extractor records must be successful")
        if event["btc_relevance"] not in ELIGIBLE_RELEVANCE:
            excluded_relevance += 1
            continue
        if event["event_type"] not in ELIGIBLE_EVENT_TYPES:
            excluded_event_type += 1
            continue
        published = datetime.fromisoformat(source["published_at"])
        decision_ms = next_4h_open_ms(published)
        item = {
            "headline_id": source["headline_id"],
            "btc_relevance": event["btc_relevance"],
            "event_type": event["event_type"],
            "direction": event["direction"],
            "severity": float(event["severity"]),
            "reported_surprise": float(event["reported_surprise"]),
            "confidence": float(event["confidence"]),
        }
        groups[decision_ms].append(item)
        type_counts[item["event_type"]] += 1
        relevance_counts[item["btc_relevance"]] += 1

    records = []
    missing_bars = 0
    for decision_ms in sorted(groups):
        entry = rows_by_time.get(decision_ms)
        exit_row = rows_by_time.get(decision_ms + FOUR_HOURS_MS)
        if entry is None or exit_row is None:
            missing_bars += 1
            continue
        sentiment, event = llm_features(groups[decision_ms])
        records.append({
            "decision_at": datetime.fromtimestamp(decision_ms / 1000, timezone.utc).isoformat(),
            "target_h4_return": float(exit_row[1]) / float(entry[1]) - 1.0,
            "sentiment_features": sentiment,
            "event_features": event,
            "event_ids": [item["headline_id"] for item in groups[decision_ms]],
        })
    if not records:
        raise ValueError("event-response panel is empty")
    panel = {
        "schema_version": "llm-only-event-response-panel-v8",
        "status": "development-target-panel-before-predictive-evaluation",
        "sources": {
            "inputs": {"path": str(inputs_path.resolve()), "sha256": sha256(inputs_path)},
            "extraction": {"path": str(extraction_path.resolve()), "sha256": sha256(extraction_path)},
            "btc_4h": {"path": str(bars_path.resolve()), "sha256": sha256(bars_path)},
        },
        "policy": {
            "eligible_relevance": list(ELIGIBLE_RELEVANCE),
            "eligible_event_types": list(ELIGIBLE_EVENT_TYPES),
            "excluded_event_types": ["market_commentary", "other"],
            "decision_time": "strictly next UTC 4h open after published_at",
            "target": "Bybit BTCUSDT open[t+4h] / open[t] - 1",
            "predictive_inputs": "LLM output only",
        },
        "records": records,
    }
    years = Counter(datetime.fromisoformat(item["decision_at"]).year for item in records)
    audit = {
        "schema_version": "llm-only-event-response-panel-audit-v8",
        "counts": {
            "source_inputs": len(inputs),
            "deduplicated_normalized_headlines": duplicate_count,
            "excluded_by_relevance": excluded_relevance,
            "excluded_by_event_type": excluded_event_type,
            "eligible_events": sum(type_counts.values()),
            "labeled_four_hour_buckets": len(records),
            "buckets_missing_market_target": missing_bars,
        },
        "eligible_event_type_counts": dict(sorted(type_counts.items())),
        "eligible_relevance_counts": dict(sorted(relevance_counts.items())),
        "bucket_counts_by_year": {str(key): years[key] for key in sorted(years)},
        "coverage": {"start": records[0]["decision_at"], "end": records[-1]["decision_at"]},
        "sentiment_feature_names": list(records[0]["sentiment_features"]),
        "event_feature_names": list(records[0]["event_features"]),
        "target_audit_only": {
            "finite": all(np.isfinite(item["target_h4_return"]) for item in records),
            "nonconstant": len({item["target_h4_return"] for item in records}) > 1,
            "distribution_or_model_metric_consulted": False,
        },
    }
    return panel, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--extraction", type=Path, required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--panel-output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()
    panel, audit = build(args.inputs, args.extraction, args.bars)
    write_json(args.panel_output, panel)
    audit["panel"] = {"path": str(args.panel_output.resolve()), "sha256": sha256(args.panel_output)}
    write_json(args.audit_output, audit)
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
