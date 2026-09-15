"""Shared outcome-blind helpers for LLM-only multi-coin transfer v18."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from eth_transfer_v17_common import (
    DIRECTIONS, EVENT_TYPES, FOLDS, HORIZONS, block_indices, metrics,
    pearson, ridge_predict, sha256, write_json,
)

ASSETS = {
    "BTCUSDT": {"experiment_id": "LLM-073", "aliases": {"bitcoin", "btc"}},
    "XRPUSDT": {"experiment_id": "LLM-074", "aliases": {"xrp", "ripple"}},
    "SOLUSDT": {"experiment_id": "LLM-075", "aliases": {"sol", "solana"}},
    "BNBUSDT": {"experiment_id": "LLM-076", "aliases": {"bnb", "binance coin"}},
}


def is_asset_event(record: dict[str, Any], aliases: set[str]) -> bool:
    return any(str(asset).strip().casefold() in aliases for asset in record.get("affected_assets", []))


def llm_features(events: list[dict[str, Any]], dates: list[str], aliases: set[str]) -> tuple[list[str], list[str], dict[str, dict[str, float]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("status") == "success" and event.get("error") is None and is_asset_event(event, aliases):
            grouped[event["information_date"]].append(event)
    generic_names = [
        "llm_event_present", "llm_event_count", *[f"llm_direction_fraction::{value}" for value in DIRECTIONS],
        "llm_severity_mean", "llm_severity_max", "llm_confidence_mean", "llm_confidence_max",
        "llm_directional_severity_mean",
    ]
    event_names = generic_names + [
        "llm_reported_surprise_mean", "llm_reported_surprise_max",
        *[f"llm_event_type_fraction::{value}" for value in EVENT_TYPES],
        *[f"llm_horizon_fraction::{value}" for value in HORIZONS],
    ]
    signs = {"positive": 1.0, "negative": -1.0, "mixed": 0.0, "unclear": 0.0}
    result: dict[str, dict[str, float]] = {}
    for date in dates:
        items = grouped.get(date, [])
        features = {name: 0.0 for name in event_names}
        if items:
            n = float(len(items))
            features["llm_event_present"] = 1.0
            features["llm_event_count"] = n
            for value in DIRECTIONS:
                features[f"llm_direction_fraction::{value}"] = sum(item["direction"] == value for item in items) / n
            severity = np.asarray([float(item["severity"]) for item in items])
            confidence = np.asarray([float(item["confidence"]) for item in items])
            surprise = np.asarray([float(item["reported_surprise"]) for item in items])
            features["llm_severity_mean"] = float(np.mean(severity))
            features["llm_severity_max"] = float(np.max(severity))
            features["llm_confidence_mean"] = float(np.mean(confidence))
            features["llm_confidence_max"] = float(np.max(confidence))
            features["llm_directional_severity_mean"] = float(np.mean([signs[item["direction"]] * float(item["severity"]) for item in items]))
            features["llm_reported_surprise_mean"] = float(np.mean(surprise))
            features["llm_reported_surprise_max"] = float(np.max(surprise))
            for value in EVENT_TYPES:
                features[f"llm_event_type_fraction::{value}"] = sum(item["event_type"] == value for item in items) / n
            for value in HORIZONS:
                features[f"llm_horizon_fraction::{value}"] = sum(item["expected_horizon"] == value for item in items) / n
        result[date] = features
    return generic_names, event_names, result
