"""Outcome-blind shared helpers for the v19 risk and v20 4h multi-coin transfers."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from eth_transfer_v17_common import FOLDS as DAILY_FOLDS

ASSETS = {
    "ETHUSDT": {"aliases": {"ethereum", "eth", "ether"}, "priority": "primary"},
    "SOLUSDT": {"aliases": {"sol", "solana"}, "priority": "primary"},
    "XRPUSDT": {"aliases": {"xrp", "ripple"}, "priority": "conditional"},
    "BNBUSDT": {"aliases": {"bnb", "binance coin"}, "priority": "conditional"},
}
EXPERIMENTS_V19 = {"ETHUSDT": "LLM-077", "SOLUSDT": "LLM-078", "XRPUSDT": "LLM-079", "BNBUSDT": "LLM-080"}
EXPERIMENTS_V20 = {"ETHUSDT": "LLM-081", "SOLUSDT": "LLM-082", "XRPUSDT": "LLM-083", "BNBUSDT": "LLM-084"}
EVENT_TYPES = [
    "macro_liquidity", "regulation", "etf_institutional_flow", "exchange_security",
    "liquidation_leverage", "network_protocol", "fraud_legal", "adoption_business",
    "market_commentary", "other",
]
CATALYST_TYPES = EVENT_TYPES[:8]
DIRECTIONS = ["positive", "negative", "mixed", "unclear"]
HORIZONS = ["4h", "12h", "24h", "72h", "unknown"]
SOURCES = ["cointelegraph.com", "coindesk.com", "decrypt.co", "cryptonews.com", "blockworks.co"]
FOUR_HOURS_MS = 14_400_000
TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def is_asset_event(record: dict[str, Any], aliases: set[str]) -> bool:
    return any(str(asset).strip().casefold() in aliases for asset in record.get("affected_assets", []))


def next_4h_open_ms(value: str) -> int:
    timestamp = datetime.fromisoformat(value).astimezone(timezone.utc)
    milliseconds = int(timestamp.timestamp() * 1000)
    return (milliseconds // FOUR_HOURS_MS + 1) * FOUR_HOURS_MS


def feature_names() -> tuple[list[str], list[str], list[str]]:
    metadata = [
        "meta_selected_event_count", "meta_recency_mean_hours", "meta_recency_max_hours",
        "meta_headline_token_mean", *[f"meta_source_fraction::{source}" for source in SOURCES],
    ]
    generic = metadata + [
        *[f"llm_direction_fraction::{value}" for value in DIRECTIONS],
        "llm_severity_mean", "llm_severity_max", "llm_confidence_mean", "llm_confidence_max",
        "llm_directional_severity_mean",
    ]
    event = generic + [
        "llm_reported_surprise_mean", "llm_reported_surprise_max",
        *[f"llm_event_type_fraction::{value}" for value in EVENT_TYPES],
        *[f"llm_horizon_fraction::{value}" for value in HORIZONS],
    ]
    return metadata, generic, event


def aggregate_features(items: list[tuple[dict, dict]]) -> dict[str, dict[str, float]]:
    metadata_names, generic_names, event_names = feature_names()
    values = {name: 0.0 for name in event_names}
    if not items:
        return {"metadata": {name: values[name] for name in metadata_names}, "generic": {name: values[name] for name in generic_names}, "event": values}
    n = float(len(items))
    events = [item[0] for item in items]
    inputs = [item[1] for item in items]
    recencies = []
    token_counts = []
    for source in inputs:
        published = datetime.fromisoformat(source["published_at"]).astimezone(timezone.utc)
        available = datetime.fromisoformat(source["available_at"]).astimezone(timezone.utc)
        recencies.append(max(0.0, (available - published).total_seconds() / 3600.0))
        token_counts.append(len(TOKEN_RE.findall(source["headline"])))
    values["meta_selected_event_count"] = n
    values["meta_recency_mean_hours"] = float(np.mean(recencies))
    values["meta_recency_max_hours"] = float(np.max(recencies))
    values["meta_headline_token_mean"] = float(np.mean(token_counts))
    for source in SOURCES:
        values[f"meta_source_fraction::{source}"] = sum(row["source_domain"] == source for row in inputs) / n
    signs = {"positive": 1.0, "negative": -1.0, "mixed": 0.0, "unclear": 0.0}
    for direction in DIRECTIONS:
        values[f"llm_direction_fraction::{direction}"] = sum(row["direction"] == direction for row in events) / n
    severity = np.asarray([float(row["severity"]) for row in events])
    confidence = np.asarray([float(row["confidence"]) for row in events])
    surprise = np.asarray([float(row["reported_surprise"]) for row in events])
    values["llm_severity_mean"] = float(np.mean(severity))
    values["llm_severity_max"] = float(np.max(severity))
    values["llm_confidence_mean"] = float(np.mean(confidence))
    values["llm_confidence_max"] = float(np.max(confidence))
    values["llm_directional_severity_mean"] = float(np.mean([signs[row["direction"]] * float(row["severity"]) for row in events]))
    values["llm_reported_surprise_mean"] = float(np.mean(surprise))
    values["llm_reported_surprise_max"] = float(np.max(surprise))
    for event_type in EVENT_TYPES:
        values[f"llm_event_type_fraction::{event_type}"] = sum(row["event_type"] == event_type for row in events) / n
    for horizon in HORIZONS:
        values[f"llm_horizon_fraction::{horizon}"] = sum(row["expected_horizon"] == horizon for row in events) / n
    return {
        "metadata": {name: values[name] for name in metadata_names},
        "generic": {name: values[name] for name in generic_names},
        "event": {name: values[name] for name in event_names},
    }


def ridge_predict(x_train: np.ndarray, y_train: np.ndarray, x_valid: np.ndarray, alpha: float = 10.0) -> np.ndarray:
    mean = np.mean(x_train, axis=0)
    scale = np.std(x_train, axis=0)
    scale[scale == 0] = 1.0
    train = (x_train - mean) / scale
    valid = (x_valid - mean) / scale
    centered = y_train - np.mean(y_train)
    coefficients = np.linalg.solve(train.T @ train + alpha * np.eye(train.shape[1]), train.T @ centered)
    return np.mean(y_train) + valid @ coefficients


def pearson(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) < 2 or np.std(left) == 0 or np.std(right) == 0:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def metrics(y: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    error = y - prediction
    return {"mse": float(np.mean(error ** 2)), "mae": float(np.mean(np.abs(error))), "pearson": pearson(prediction, y), "prediction_std": float(np.std(prediction))}


def block_indices(length: int, block: int, rng: np.random.Generator) -> np.ndarray:
    if length <= block:
        return np.arange(length)
    starts = rng.integers(0, length - block + 1, size=math.ceil(length / block))
    return np.concatenate([np.arange(start, start + block) for start in starts])[:length]


def bootstrap(folds: list[dict[str, np.ndarray]], target: str, iterations: int, block: int, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    delta_meta, delta_generic, corr = [], [], []
    for _ in range(iterations):
        sampled = []
        for fold in folds:
            idx = block_indices(len(fold[target]), block, rng)
            sampled.append({key: value[idx] for key, value in fold.items()})
        y = np.concatenate([row[target] for row in sampled])
        meta = np.concatenate([row[f"{target}_metadata"] for row in sampled])
        generic = np.concatenate([row[f"{target}_generic"] for row in sampled])
        event = np.concatenate([row[f"{target}_event"] for row in sampled])
        delta_meta.append(float(np.mean((y - meta) ** 2 - (y - event) ** 2)))
        delta_generic.append(float(np.mean((y - generic) ** 2 - (y - event) ** 2)))
        corr.append(pearson(event, y))
    return {
        "event_minus_metadata_delta_mse_95_ci": [float(x) for x in np.quantile(delta_meta, [0.025, 0.975])],
        "event_minus_generic_delta_mse_95_ci": [float(x) for x in np.quantile(delta_generic, [0.025, 0.975])],
        "event_pearson_95_ci": [float(x) for x in np.quantile(corr, [0.025, 0.975])],
        "one_sided_p_event_vs_metadata": float((1 + sum(x <= 0 for x in delta_meta)) / (iterations + 1)),
        "one_sided_p_event_vs_generic": float((1 + sum(x <= 0 for x in delta_generic)) / (iterations + 1)),
        "one_sided_p_pearson": float((1 + sum(x <= 0 for x in corr)) / (iterations + 1)),
    }

