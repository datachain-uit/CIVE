"""Predeclared walk-forward predictive gate for the v3.9 event extraction."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def normalized_headline(value: str) -> str:
    return " ".join(value.casefold().split())


def headline_tokens(value: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(value.casefold()) if len(token) >= 2}


def causal_metadata_features(
    records_by_date: dict[str, list[dict]], dates: list[str], sources: list[str], coin_types: list[str],
    lookback_days: int,
) -> tuple[dict[str, dict[str, float]], dict[str, set[str]], int]:
    history: deque[tuple[str, list[str], set[str]]] = deque()
    historical_headlines: Counter[str] = Counter()
    historical_tokens: Counter[str] = Counter()
    seen_global: set[str] = set()
    deduplicated = 0
    result: dict[str, dict[str, float]] = {}
    kept_ids: dict[str, set[str]] = {}

    for date in dates:
        current_day = datetime.fromisoformat(date).date()
        while history and (current_day - datetime.fromisoformat(history[0][0]).date()).days > lookback_days:
            _, old_headlines, old_tokens = history.popleft()
            historical_headlines.subtract(old_headlines)
            historical_tokens.subtract(old_tokens)
            historical_headlines += Counter()
            historical_tokens += Counter()

        ordered_records = sorted(
            records_by_date[date], key=lambda item: (item["available_at"], item["position_in_day"])
        )
        all_day_headlines = [normalized_headline(item["headline"]) for item in ordered_records]
        all_day_tokens = set().union(*(headline_tokens(item["headline"]) for item in ordered_records))
        recurrence = sum(historical_headlines[headline] > 0 for headline in all_day_headlines) / len(ordered_records)
        novelty = (
            sum(historical_tokens[token] == 0 for token in all_day_tokens) / len(all_day_tokens)
            if all_day_tokens else 0.0
        )
        unique_records = []
        for record, normalized in zip(ordered_records, all_day_headlines):
            if normalized in seen_global:
                deduplicated += 1
                continue
            seen_global.add(normalized)
            unique_records.append(record)

        if not unique_records:
            raise ValueError(f"no unique headlines remain for {date}")
        denominator = float(len(unique_records))
        recencies = []
        token_counts = []
        for item in unique_records:
            available = datetime.fromisoformat(item["available_at"]).astimezone(timezone.utc)
            published = datetime.fromisoformat(item["published_at"]).astimezone(timezone.utc)
            recency = (available - published).total_seconds() / 3600.0
            if recency < 0:
                raise ValueError(f"negative article recency for {item['headline_id']}")
            recencies.append(recency)
            token_counts.append(len(headline_tokens(item["headline"])))

        features = {
            "meta_article_count": denominator,
            "meta_recency_mean_hours": float(np.mean(recencies)),
            "meta_recency_max_hours": float(np.max(recencies)),
            "meta_headline_token_count_mean": float(np.mean(token_counts)),
            "meta_exact_recurrence_30d_fraction": recurrence,
            "meta_token_novelty_30d_fraction": novelty,
        }
        for source in sources:
            features[f"meta_source_fraction::{source}"] = sum(
                item["source_domain"] == source for item in unique_records
            ) / denominator
        for coin_type in coin_types:
            features[f"meta_coin_type_fraction::{coin_type}"] = sum(
                item["coin_type"] == coin_type for item in unique_records
            ) / denominator
        result[date] = features
        kept_ids[date] = {item["headline_id"] for item in unique_records}
        history.append((date, all_day_headlines, all_day_tokens))
        historical_headlines.update(all_day_headlines)
        historical_tokens.update(all_day_tokens)
    return result, kept_ids, deduplicated


def event_features(
    input_by_id: dict[str, dict], events: list[dict], dates: list[str], kept_ids: dict[str, set[str]], relevance: list[str],
    event_types: list[str], directions: list[str], horizons: list[str],
) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    seen: set[str] = set()
    for event in events:
        headline_id = event.get("headline_id")
        source = input_by_id.get(headline_id)
        if source is None or headline_id in seen:
            raise ValueError("event IDs must match input one-to-one")
        seen.add(headline_id)
        if event.get("status") != "success" or event.get("error") is not None:
            raise ValueError("all extractor records must be successful")
        if event.get("information_date") != source["information_date"]:
            raise ValueError("event information_date mismatch")
        date = source["information_date"]
        if headline_id in kept_ids[date]:
            grouped[date].append(event)
    if seen != set(input_by_id):
        raise ValueError("extractor/input ID coverage mismatch")

    result = {}
    sign = {"positive": 1.0, "negative": -1.0, "mixed": 0.0, "unclear": 0.0}
    for date in dates:
        items = grouped[date]
        denominator = float(len(items))
        features: dict[str, float] = {}
        for value in relevance:
            features[f"event_relevance_fraction::{value}"] = sum(
                item["btc_relevance"] == value for item in items
            ) / denominator
        for value in event_types:
            features[f"event_type_fraction::{value}"] = sum(
                item["event_type"] == value for item in items
            ) / denominator
        for value in directions:
            features[f"event_direction_fraction::{value}"] = sum(
                item["direction"] == value for item in items
            ) / denominator
        for value in horizons:
            features[f"event_horizon_fraction::{value}"] = sum(
                item["expected_horizon"] == value for item in items
            ) / denominator
        for field in ("severity", "reported_surprise", "confidence"):
            values = [float(item[field]) for item in items]
            features[f"event_{field}_mean"] = float(np.mean(values))
            features[f"event_{field}_max"] = float(np.max(values))
        features["event_affected_asset_count_mean"] = float(np.mean([
            len(item["affected_assets"]) for item in items
        ]))
        features["event_evidence_fallback_fraction"] = sum(
            item.get("evidence_fallback") is True for item in items
        ) / denominator
        features["event_high_severity_fraction"] = sum(
            float(item["severity"]) >= 0.7 for item in items
        ) / denominator
        features["event_directional_severity_mean"] = float(np.mean([
            sign[item["direction"]] * float(item["severity"]) for item in items
        ]))
        result[date] = features
    return result


def ridge_predict(x_train: np.ndarray, y_train: np.ndarray, x_valid: np.ndarray, alpha: float) -> np.ndarray:
    mean = np.mean(x_train, axis=0)
    scale = np.std(x_train, axis=0)
    scale[scale == 0] = 1.0
    train = (x_train - mean) / scale
    valid = (x_valid - mean) / scale
    centered = y_train - np.mean(y_train)
    matrix = train.T @ train + alpha * np.eye(train.shape[1])
    coefficients = np.linalg.solve(matrix, train.T @ centered)
    return np.mean(y_train) + valid @ coefficients


def pearson(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) < 2 or np.std(left) == 0 or np.std(right) == 0:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def metrics(y: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    residual = y - prediction
    design = np.column_stack([np.ones(len(prediction)), prediction])
    calibration = np.linalg.lstsq(design, y, rcond=None)[0]
    return {
        "mse": float(np.mean(residual ** 2)),
        "rmse": float(math.sqrt(np.mean(residual ** 2))),
        "mae": float(np.mean(np.abs(residual))),
        "pearson": pearson(prediction, y),
        "prediction_std": float(np.std(prediction)),
        "calibration_intercept": float(calibration[0]),
        "calibration_slope": float(calibration[1]),
    }


def sampled_block_indices(length: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    if length <= block_length:
        return np.arange(length)
    starts = rng.integers(0, length - block_length + 1, size=math.ceil(length / block_length))
    return np.concatenate([np.arange(start, start + block_length) for start in starts])[:length]


def block_bootstrap(
    folds: list[dict[str, np.ndarray]], iterations: int, block_length: int, seed: int,
) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    delta_samples = []
    correlation_samples = []
    for _ in range(iterations):
        sampled = []
        for fold in folds:
            indices = sampled_block_indices(len(fold["y"]), block_length, rng)
            sampled.append({key: value[indices] for key, value in fold.items()})
        y = np.concatenate([item["y"] for item in sampled])
        metadata = np.concatenate([item["metadata"] for item in sampled])
        event = np.concatenate([item["event"] for item in sampled])
        delta_samples.append(float(np.mean((y - metadata) ** 2 - (y - event) ** 2)))
        correlation_samples.append(pearson(event, y))
    return {
        "paired_delta_mse_95_ci": [float(value) for value in np.quantile(delta_samples, [0.025, 0.975])],
        "event_pearson_95_ci": [float(value) for value in np.quantile(correlation_samples, [0.025, 0.975])],
    }


def evaluate(config: dict) -> tuple[dict, dict]:
    source_paths = {key: Path(value["path"]) for key, value in config["sources"].items()}
    for key, path in source_paths.items():
        if sha256(path) != config["sources"][key]["sha256"]:
            raise ValueError(f"{key} hash differs from predeclaration")
    evaluator = Path(config["evaluator"]["path"])
    if sha256(evaluator) != config["evaluator"]["sha256"]:
        raise ValueError("evaluator hash differs from predeclaration")

    extraction_gate = json.loads(source_paths["extraction_gate"].read_text(encoding="utf-8"))
    if not extraction_gate.get("passed") or extraction_gate.get("status") != "full-extraction-pass-downstream-design-authorized":
        raise ValueError("full extraction gate did not authorize downstream design")
    inputs = json.loads(source_paths["extraction_input"].read_text(encoding="utf-8"))["records"]
    extraction = json.loads(source_paths["extraction"].read_text(encoding="utf-8"))["records"]
    market = json.loads(source_paths["market_features"].read_text(encoding="utf-8"))["records"]
    targets = json.loads(source_paths["target_panel"].read_text(encoding="utf-8"))["records"]
    dates = [item["information_date"] for item in targets]
    if dates != sorted(dates) or len(dates) != config["data_gate"]["required_dates"]:
        raise ValueError("target dates are not the frozen ordered panel")

    input_by_id = {item["headline_id"]: item for item in inputs}
    if len(input_by_id) != len(inputs):
        raise ValueError("duplicate input headline_id")
    records_by_date: dict[str, list[dict]] = defaultdict(list)
    for item in inputs:
        records_by_date[item["information_date"]].append(item)
    feature_contract = config["feature_contract"]
    metadata, kept_ids, deduplicated = causal_metadata_features(
        records_by_date, dates, feature_contract["source_domains"], feature_contract["coin_types"],
        feature_contract["recurrence_lookback_days"],
    )
    events = event_features(
        input_by_id, extraction, dates, kept_ids, feature_contract["btc_relevance"],
        feature_contract["event_types"], feature_contract["directions"],
        feature_contract["expected_horizons"],
    )
    market_by_date = {item["information_date"]: item for item in market}
    target_by_date = {item["information_date"]: item for item in targets}
    if set(dates) != set(market_by_date) or set(dates) != set(metadata) or set(dates) != set(events):
        raise ValueError("daily feature coverage mismatch")
    for date in dates:
        if market_by_date[date]["source_snapshot_hash"] != target_by_date[date]["source_snapshot_hash"]:
            raise ValueError("source snapshot hash mismatch")

    market_names = feature_contract["market_numeric"]
    metadata_names = list(metadata[dates[0]])
    event_names = list(events[dates[0]])
    rows = []
    for date in dates:
        market_values = [float(market_by_date[date]["features"][name]) for name in market_names]
        metadata_values = market_values + [metadata[date][name] for name in metadata_names]
        event_values = metadata_values + [events[date][name] for name in event_names]
        rows.append({
            "information_date": date,
            "market": market_values,
            "metadata": metadata_values,
            "event": event_values,
            "target": float(target_by_date[date]["targets"][config["target"]["field"]]),
        })

    all_predictions = {"market": [], "metadata": [], "event": [], "target": [], "dates": []}
    bootstrap_folds = []
    fold_results = []
    for fold in config["folds"]:
        train_indices = [index for index, row in enumerate(rows) if row["information_date"] <= fold["train_end"]]
        valid_indices = [index for index, row in enumerate(rows) if fold["valid_start"] <= row["information_date"] <= fold["valid_end"]]
        if len(train_indices) != fold["train_records"] or len(valid_indices) != fold["valid_records"]:
            raise ValueError(f"fold {fold['fold']} record count mismatch")
        predictions = {}
        y_train = np.asarray([rows[index]["target"] for index in train_indices], dtype=float)
        y_valid = np.asarray([rows[index]["target"] for index in valid_indices], dtype=float)
        for arm in ("market", "metadata", "event"):
            x_train = np.asarray([rows[index][arm] for index in train_indices], dtype=float)
            x_valid = np.asarray([rows[index][arm] for index in valid_indices], dtype=float)
            predictions[arm] = ridge_predict(x_train, y_train, x_valid, float(config["model"]["alpha"]))
            all_predictions[arm].extend(predictions[arm].tolist())
        all_predictions["target"].extend(y_valid.tolist())
        all_predictions["dates"].extend(rows[index]["information_date"] for index in valid_indices)
        fold_metrics = {arm: metrics(y_valid, predictions[arm]) for arm in ("market", "metadata", "event")}
        fold_metrics["event_minus_metadata_delta_mse"] = (
            fold_metrics["metadata"]["mse"] - fold_metrics["event"]["mse"]
        )
        fold_results.append({"fold": fold["fold"], "validation_records": len(valid_indices), "metrics": fold_metrics})
        bootstrap_folds.append({"y": y_valid, "metadata": predictions["metadata"], "event": predictions["event"]})

    y = np.asarray(all_predictions["target"])
    overall = {arm: metrics(y, np.asarray(all_predictions[arm])) for arm in ("market", "metadata", "event")}
    delta_mse = overall["metadata"]["mse"] - overall["event"]["mse"]
    relative_reduction = delta_mse / overall["metadata"]["mse"] if overall["metadata"]["mse"] else 0.0
    uncertainty = block_bootstrap(
        bootstrap_folds, int(config["bootstrap"]["iterations"]),
        int(config["bootstrap"]["block_length_days"]), int(config["bootstrap"]["seed"]),
    )
    fold_wins = sum(item["metrics"]["event"]["mse"] < item["metrics"]["metadata"]["mse"] for item in fold_results)
    checks = {
        "oos_records": len(y) == config["predictive_gate"]["required_oos_records"],
        "paired_delta_mse_ci_lower_gt_zero": uncertainty["paired_delta_mse_95_ci"][0] > 0,
        "event_pearson_ci_lower_gt_zero": uncertainty["event_pearson_95_ci"][0] > 0,
        "event_mse_fold_wins": fold_wins >= config["predictive_gate"]["minimum_fold_wins"],
        "event_predictions_nonconstant": overall["event"]["prediction_std"] > 0,
    }
    passed = all(checks.values())
    panel = {
        "schema_version": 1,
        "experiment_id": config["experiment_id"],
        "status": "development-paired-oos-prediction-panel",
        "target": config["target"],
        "feature_names": {
            "market": market_names,
            "metadata": market_names + metadata_names,
            "event": market_names + metadata_names + event_names,
        },
        "deduplicated_repeated_headlines": deduplicated,
        "records": [{
            "information_date": date, "target": target, "market_prediction": market_prediction,
            "metadata_prediction": metadata_prediction, "event_prediction": event_prediction,
        } for date, target, market_prediction, metadata_prediction, event_prediction in zip(
            all_predictions["dates"], all_predictions["target"], all_predictions["market"],
            all_predictions["metadata"], all_predictions["event"],
        )],
    }
    result = {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "status": "predictive-gate-pass-overlay-design-authorized" if passed else "predictive-gate-fail-stop-before-threshold-or-backtest",
        "passed": passed,
        "outcomes_consulted": True,
        "trading_backtest_consulted": False,
        "target": config["target"],
        "model": config["model"],
        "oos_records": len(y),
        "overall": overall,
        "event_minus_metadata": {
            "paired_delta_mse": delta_mse,
            "relative_mse_reduction": relative_reduction,
            "mse_fold_wins": fold_wins,
        },
        "uncertainty": uncertainty,
        "folds": fold_results,
        "checks": checks,
        "inputs": {key: {"path": str(path.resolve()), "sha256": sha256(path)} for key, path in source_paths.items()},
    }
    return panel, result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--panel-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    panel, result = evaluate(config)
    write_json(args.panel_output, panel)
    result["prediction_panel"] = {"path": str(args.panel_output.resolve()), "sha256": sha256(args.panel_output)}
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
