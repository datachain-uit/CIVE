"""Shared, frozen helpers for the ETH LLM-only v17 and HYB-004 transfer tests."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np


ETH_ALIASES = {"ethereum", "eth", "ether"}
EVENT_TYPES = [
    "macro_liquidity", "regulation", "etf_institutional_flow", "exchange_security",
    "liquidation_leverage", "network_protocol", "fraud_legal", "adoption_business",
    "market_commentary", "other",
]
DIRECTIONS = ["positive", "negative", "mixed", "unclear"]
HORIZONS = ["4h", "12h", "24h", "72h", "unknown"]
FOLDS = [
    {"fold": 1, "train_end": "2023-09-11", "valid_start": "2023-09-15", "valid_end": "2024-01-31"},
    {"fold": 2, "train_end": "2024-01-31", "valid_start": "2024-02-04", "valid_end": "2024-06-21"},
    {"fold": 3, "train_end": "2024-06-21", "valid_start": "2024-06-25", "valid_end": "2024-11-10"},
    {"fold": 4, "train_end": "2024-11-10", "valid_start": "2024-11-14", "valid_end": "2025-04-01"},
    {"fold": 5, "train_end": "2025-04-01", "valid_start": "2025-04-05", "valid_end": "2025-08-27"},
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def is_eth_event(record: dict) -> bool:
    return any(str(asset).casefold() in ETH_ALIASES for asset in record.get("affected_assets", []))


def llm_features(events: list[dict], dates: list[str]) -> tuple[list[str], list[str], dict[str, dict[str, float]]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        if event.get("status") == "success" and event.get("error") is None and is_eth_event(event):
            grouped[event["information_date"]].append(event)
    generic_names = [
        "llm_event_present", "llm_event_count", *[f"llm_direction_fraction::{v}" for v in DIRECTIONS],
        "llm_severity_mean", "llm_severity_max", "llm_confidence_mean", "llm_confidence_max",
        "llm_directional_severity_mean",
    ]
    event_names = generic_names + [
        "llm_reported_surprise_mean", "llm_reported_surprise_max",
        *[f"llm_event_type_fraction::{v}" for v in EVENT_TYPES],
        *[f"llm_horizon_fraction::{v}" for v in HORIZONS],
    ]
    sign = {"positive": 1.0, "negative": -1.0, "mixed": 0.0, "unclear": 0.0}
    result: dict[str, dict[str, float]] = {}
    for date in dates:
        items = grouped.get(date, [])
        n = float(len(items))
        features = {name: 0.0 for name in event_names}
        if items:
            features["llm_event_present"] = 1.0
            features["llm_event_count"] = n
            for value in DIRECTIONS:
                features[f"llm_direction_fraction::{value}"] = sum(i["direction"] == value for i in items) / n
            severity = np.asarray([float(i["severity"]) for i in items])
            confidence = np.asarray([float(i["confidence"]) for i in items])
            surprise = np.asarray([float(i["reported_surprise"]) for i in items])
            features["llm_severity_mean"] = float(np.mean(severity))
            features["llm_severity_max"] = float(np.max(severity))
            features["llm_confidence_mean"] = float(np.mean(confidence))
            features["llm_confidence_max"] = float(np.max(confidence))
            features["llm_directional_severity_mean"] = float(np.mean([
                sign[i["direction"]] * float(i["severity"]) for i in items
            ]))
            features["llm_reported_surprise_mean"] = float(np.mean(surprise))
            features["llm_reported_surprise_max"] = float(np.max(surprise))
            for value in EVENT_TYPES:
                features[f"llm_event_type_fraction::{value}"] = sum(i["event_type"] == value for i in items) / n
            for value in HORIZONS:
                features[f"llm_horizon_fraction::{value}"] = sum(i["expected_horizon"] == value for i in items) / n
        result[date] = features
    return generic_names, event_names, result


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
    residual = y - prediction
    return {
        "mse": float(np.mean(residual ** 2)),
        "rmse": float(math.sqrt(np.mean(residual ** 2))),
        "mae": float(np.mean(np.abs(residual))),
        "pearson": pearson(prediction, y),
        "prediction_std": float(np.std(prediction)),
    }


def block_indices(length: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    if length <= block_length:
        return np.arange(length)
    starts = rng.integers(0, length - block_length + 1, size=math.ceil(length / block_length))
    return np.concatenate([np.arange(s, s + block_length) for s in starts])[:length]
