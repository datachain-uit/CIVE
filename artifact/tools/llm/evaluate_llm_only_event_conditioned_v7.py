"""Development-only LLM event-conditioned predictive gate for v7."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
BANNED_FEATURE_TERMS = (
    "price", "open", "high", "low", "close", "volume", "return", "volatility",
    "momentum", "funding", "breadth", "dispersion", "rsi", "macd", "technical",
)
RELEVANCE_WEIGHT = {"direct": 1.0, "systemic": 0.75, "indirect": 0.25, "none": 0.0}
DIRECTION_SIGN = {"positive": 1.0, "negative": -1.0, "mixed": 0.0, "unclear": 0.0}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def normalized_headline(value: str) -> str:
    return " ".join(value.casefold().split())


def unique_ids_by_date(inputs: list[dict], dates: list[str]) -> tuple[dict[str, set[str]], int]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in inputs:
        grouped[item["information_date"]].append(item)
    seen: set[str] = set()
    kept: dict[str, set[str]] = {}
    duplicate_count = 0
    for date in dates:
        ids: set[str] = set()
        for item in sorted(grouped[date], key=lambda row: (row["available_at"], row["position_in_day"])):
            normalized = normalized_headline(item["headline"])
            if normalized in seen:
                duplicate_count += 1
                continue
            seen.add(normalized)
            ids.add(item["headline_id"])
        if not ids:
            raise ValueError(f"no unique LLM records remain for {date}")
        kept[date] = ids
    return kept, duplicate_count


def llm_feature_sets(
    input_by_id: dict[str, dict], events: list[dict], dates: list[str], kept_ids: dict[str, set[str]],
    relevance_values: list[str], event_types: list[str], directions: list[str], horizons: list[str],
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    seen: set[str] = set()
    for event in events:
        headline_id = event.get("headline_id")
        source = input_by_id.get(headline_id)
        if source is None or headline_id in seen:
            raise ValueError("event IDs must match inputs one-to-one")
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

    sentiment_by_date: dict[str, dict[str, float]] = {}
    event_by_date: dict[str, dict[str, float]] = {}
    for date in dates:
        items = grouped[date]
        if not items:
            raise ValueError(f"no LLM events remain for {date}")
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
        conditioned = dict(sentiment)
        for value in relevance_values:
            conditioned[f"llm_event_relevance_fraction::{value}"] = sum(
                item["btc_relevance"] == value for item in items
            ) / denominator
        for value in event_types:
            selected = [index for index, item in enumerate(items) if item["event_type"] == value]
            conditioned[f"llm_event_type_fraction::{value}"] = len(selected) / denominator
            conditioned[f"llm_event_impact::{value}"] = float(np.mean([
                signs[index] * severity[index] * surprise[index] * confidence[index]
                * RELEVANCE_WEIGHT[items[index]["btc_relevance"]]
                for index in selected
            ])) if selected else 0.0
        for value in horizons:
            conditioned[f"llm_event_horizon_fraction::{value}"] = sum(
                item["expected_horizon"] == value for item in items
            ) / denominator
        for relevance in ("direct", "systemic"):
            selected = [index for index, item in enumerate(items) if item["btc_relevance"] == relevance]
            conditioned[f"llm_event_directional_impact::{relevance}"] = float(np.mean([
                signs[index] * severity[index] * surprise[index] * confidence[index]
                for index in selected
            ])) if selected else 0.0
        sentiment_by_date[date] = sentiment
        event_by_date[date] = conditioned
    return sentiment_by_date, event_by_date


def assert_llm_only_feature_names(feature_names: list[str]) -> None:
    invalid = []
    for name in feature_names:
        tokens = set(re.findall(r"[a-z0-9]+", name.casefold()))
        if any(term in tokens for term in BANNED_FEATURE_TERMS):
            invalid.append(name)
    if invalid:
        raise ValueError(f"non-LLM feature names are prohibited: {invalid}")
    if not feature_names or any(not name.startswith("llm_") for name in feature_names):
        raise ValueError("every predictive feature must be produced from LLM event records")


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
    return {
        "mse": float(np.mean(residual ** 2)),
        "rmse": float(math.sqrt(np.mean(residual ** 2))),
        "mae": float(np.mean(np.abs(residual))),
        "pearson": pearson(prediction, y),
        "prediction_std": float(np.std(prediction)),
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
        sentiment = np.concatenate([item["sentiment"] for item in sampled])
        event = np.concatenate([item["event"] for item in sampled])
        delta_samples.append(float(np.mean((y - sentiment) ** 2 - (y - event) ** 2)))
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
    evaluator = Path(config["code"]["evaluator"]["path"])
    if sha256(evaluator) != config["code"]["evaluator"]["sha256"]:
        raise ValueError("evaluator hash differs from predeclaration")

    extraction_gate = json.loads(source_paths["extraction_gate"].read_text(encoding="utf-8"))
    if not extraction_gate.get("passed"):
        raise ValueError("full extraction gate did not pass")
    inputs = json.loads(source_paths["extraction_input"].read_text(encoding="utf-8"))["records"]
    events = json.loads(source_paths["extraction"].read_text(encoding="utf-8"))["records"]
    targets = json.loads(source_paths["target_panel"].read_text(encoding="utf-8"))["records"]
    dates = [item["information_date"] for item in targets]
    if dates != sorted(dates) or len(dates) != config["data_gate"]["required_dates"]:
        raise ValueError("target dates are not the frozen ordered panel")
    if len(inputs) != config["data_gate"]["required_extraction_records"]:
        raise ValueError("extraction input count mismatch")

    input_by_id = {item["headline_id"]: item for item in inputs}
    if len(input_by_id) != len(inputs):
        raise ValueError("duplicate input headline_id")
    kept_ids, duplicate_count = unique_ids_by_date(inputs, dates)
    contract = config["feature_contract"]
    sentiment, event = llm_feature_sets(
        input_by_id, events, dates, kept_ids, contract["btc_relevance"], contract["event_types"],
        contract["directions"], contract["expected_horizons"],
    )
    sentiment_names = list(sentiment[dates[0]])
    event_names = list(event[dates[0]])
    assert_llm_only_feature_names(sentiment_names)
    assert_llm_only_feature_names(event_names)
    target_by_date = {item["information_date"]: item for item in targets}
    rows = [{
        "information_date": date,
        "sentiment": [sentiment[date][name] for name in sentiment_names],
        "event": [event[date][name] for name in event_names],
        "target": float(target_by_date[date]["targets"][config["target"]["field"]]),
    } for date in dates]

    all_predictions = {"prior": [], "sentiment": [], "event": [], "target": [], "dates": []}
    bootstrap_folds = []
    fold_results = []
    for fold in config["folds"]:
        train_indices = [index for index, row in enumerate(rows) if row["information_date"] <= fold["train_end"]]
        valid_indices = [index for index, row in enumerate(rows) if fold["valid_start"] <= row["information_date"] <= fold["valid_end"]]
        if len(train_indices) != fold["train_records"] or len(valid_indices) != fold["valid_records"]:
            raise ValueError(f"fold {fold['fold']} record count mismatch")
        y_train = np.asarray([rows[index]["target"] for index in train_indices], dtype=float)
        y_valid = np.asarray([rows[index]["target"] for index in valid_indices], dtype=float)
        predictions = {"prior": np.full(len(valid_indices), np.mean(y_train), dtype=float)}
        for arm in ("sentiment", "event"):
            x_train = np.asarray([rows[index][arm] for index in train_indices], dtype=float)
            x_valid = np.asarray([rows[index][arm] for index in valid_indices], dtype=float)
            predictions[arm] = ridge_predict(x_train, y_train, x_valid, float(config["model"]["alpha"]))
        for arm in ("prior", "sentiment", "event"):
            all_predictions[arm].extend(predictions[arm].tolist())
        all_predictions["target"].extend(y_valid.tolist())
        all_predictions["dates"].extend(rows[index]["information_date"] for index in valid_indices)
        fold_metrics = {arm: metrics(y_valid, predictions[arm]) for arm in ("prior", "sentiment", "event")}
        fold_metrics["event_minus_sentiment_delta_mse"] = fold_metrics["sentiment"]["mse"] - fold_metrics["event"]["mse"]
        fold_results.append({"fold": fold["fold"], "validation_records": len(valid_indices), "metrics": fold_metrics})
        bootstrap_folds.append({"y": y_valid, "sentiment": predictions["sentiment"], "event": predictions["event"]})

    y = np.asarray(all_predictions["target"])
    overall = {arm: metrics(y, np.asarray(all_predictions[arm])) for arm in ("prior", "sentiment", "event")}
    delta_mse = overall["sentiment"]["mse"] - overall["event"]["mse"]
    uncertainty = block_bootstrap(
        bootstrap_folds, int(config["bootstrap"]["iterations"]),
        int(config["bootstrap"]["block_length_days"]), int(config["bootstrap"]["seed"]),
    )
    fold_wins = sum(item["metrics"]["event"]["mse"] < item["metrics"]["sentiment"]["mse"] for item in fold_results)
    checks = {
        "oos_records": len(y) == config["gate"]["required_oos_records"],
        "paired_delta_mse_ci_lower_gt_zero": uncertainty["paired_delta_mse_95_ci"][0] > 0,
        "event_pearson_ci_lower_gt_zero": uncertainty["event_pearson_95_ci"][0] > 0,
        "event_mse_fold_wins": fold_wins >= config["gate"]["minimum_fold_wins"],
        "event_predictions_nonconstant": overall["event"]["prediction_std"] > 0,
    }
    passed = all(checks.values())
    panel = {
        "schema_version": "llm-only-event-conditioned-panel-v7",
        "experiment_id": config["experiment_id"],
        "status": "development-paired-oos-prediction-panel",
        "feature_names": {"prior": [], "sentiment": sentiment_names, "event": event_names},
        "deduplicated_repeated_headlines": duplicate_count,
        "records": [{
            "information_date": date, "target": target, "prior_prediction": prior,
            "sentiment_prediction": sentiment_prediction, "event_prediction": event_prediction,
        } for date, target, prior, sentiment_prediction, event_prediction in zip(
            all_predictions["dates"], all_predictions["target"], all_predictions["prior"],
            all_predictions["sentiment"], all_predictions["event"],
        )],
    }
    result = {
        "schema_version": "llm-only-event-conditioned-gate-v7",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "status": "predictive-gate-pass-backtest-design-authorized" if passed else "predictive-gate-fail-stop-before-backtest",
        "passed": passed,
        "development_only": True,
        "prior_outcomes_consulted_before_design": True,
        "technical_or_market_features_used": False,
        "trading_backtest_consulted": False,
        "target": config["target"],
        "model": config["model"],
        "oos_records": len(y),
        "overall": overall,
        "event_minus_sentiment": {
            "paired_delta_mse": delta_mse,
            "relative_mse_reduction": delta_mse / overall["sentiment"]["mse"],
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
