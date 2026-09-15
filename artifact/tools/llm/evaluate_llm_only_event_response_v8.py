"""Evaluate the predeclared LLM-only four-hour event-response gate."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from evaluate_llm_only_event_conditioned_v7 import (
    assert_llm_only_feature_names,
    block_bootstrap,
    metrics,
    ridge_predict,
    sha256,
    write_json,
)


def fold_indices(records: list[dict], fold: dict) -> tuple[list[int], list[int]]:
    train = [index for index, row in enumerate(records) if row["decision_at"] <= fold["train_end"]]
    valid = [
        index for index, row in enumerate(records)
        if fold["valid_start"] <= row["decision_at"] <= fold["valid_end"]
    ]
    return train, valid


def evaluate(config: dict) -> tuple[dict, dict]:
    panel_path = Path(config["sources"]["panel"]["path"])
    if sha256(panel_path) != config["sources"]["panel"]["sha256"]:
        raise ValueError("panel hash differs from predeclaration")
    evaluator = Path(config["code"]["evaluator"]["path"])
    if sha256(evaluator) != config["code"]["evaluator"]["sha256"]:
        raise ValueError("evaluator hash differs from predeclaration")
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    records = panel["records"]
    if len(records) != config["data_gate"]["required_panel_records"]:
        raise ValueError("panel record count mismatch")
    decisions = [row["decision_at"] for row in records]
    if decisions != sorted(decisions) or len(decisions) != len(set(decisions)):
        raise ValueError("decision_at must be unique and ordered")
    if panel["policy"]["predictive_inputs"] != "LLM output only":
        raise ValueError("panel does not assert LLM-only predictive inputs")

    sentiment_names = list(records[0]["sentiment_features"])
    event_names = list(records[0]["event_features"])
    assert_llm_only_feature_names(sentiment_names)
    assert_llm_only_feature_names(event_names)
    if sentiment_names != config["feature_contract"]["sentiment_feature_names"]:
        raise ValueError("sentiment feature contract mismatch")
    if event_names != config["feature_contract"]["event_feature_names"]:
        raise ValueError("event feature contract mismatch")
    for row in records:
        if list(row["sentiment_features"]) != sentiment_names or list(row["event_features"]) != event_names:
            raise ValueError("feature order or coverage mismatch")
        if not np.isfinite(float(row["target_h4_return"])):
            raise ValueError("non-finite target")

    all_values = {"target": [], "prior": [], "sentiment": [], "event": [], "decision_at": []}
    bootstrap_folds = []
    fold_results = []
    alpha = float(config["model"]["alpha"])
    for fold in config["folds"]:
        train, valid = fold_indices(records, fold)
        if len(train) != fold["train_records"] or len(valid) != fold["valid_records"]:
            raise ValueError(f"fold {fold['fold']} record count mismatch")
        y_train = np.asarray([records[index]["target_h4_return"] for index in train], dtype=float)
        y_valid = np.asarray([records[index]["target_h4_return"] for index in valid], dtype=float)
        predictions = {"prior": np.full(len(valid), np.mean(y_train), dtype=float)}
        for arm, feature_key, names in (
            ("sentiment", "sentiment_features", sentiment_names),
            ("event", "event_features", event_names),
        ):
            x_train = np.asarray([[records[index][feature_key][name] for name in names] for index in train], dtype=float)
            x_valid = np.asarray([[records[index][feature_key][name] for name in names] for index in valid], dtype=float)
            predictions[arm] = ridge_predict(x_train, y_train, x_valid, alpha)
        for arm in ("prior", "sentiment", "event"):
            all_values[arm].extend(predictions[arm].tolist())
        all_values["target"].extend(y_valid.tolist())
        all_values["decision_at"].extend(records[index]["decision_at"] for index in valid)
        fold_metrics = {arm: metrics(y_valid, predictions[arm]) for arm in ("prior", "sentiment", "event")}
        fold_metrics["event_minus_sentiment_delta_mse"] = fold_metrics["sentiment"]["mse"] - fold_metrics["event"]["mse"]
        fold_results.append({"fold": fold["fold"], "validation_records": len(valid), "metrics": fold_metrics})
        bootstrap_folds.append({"y": y_valid, "sentiment": predictions["sentiment"], "event": predictions["event"]})

    y = np.asarray(all_values["target"], dtype=float)
    overall = {arm: metrics(y, np.asarray(all_values[arm], dtype=float)) for arm in ("prior", "sentiment", "event")}
    delta_mse = overall["sentiment"]["mse"] - overall["event"]["mse"]
    uncertainty = block_bootstrap(
        bootstrap_folds,
        int(config["bootstrap"]["iterations"]),
        int(config["bootstrap"]["block_length_records"]),
        int(config["bootstrap"]["seed"]),
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
    prediction_panel = {
        "schema_version": "llm-only-event-response-predictions-v8",
        "experiment_id": config["experiment_id"],
        "status": "development-oos-predictions",
        "feature_names": {"prior": [], "sentiment": sentiment_names, "event": event_names},
        "records": [{
            "decision_at": decision,
            "target_h4_return": target,
            "prior_prediction": prior,
            "sentiment_prediction": sentiment,
            "event_prediction": event,
        } for decision, target, prior, sentiment, event in zip(
            all_values["decision_at"], all_values["target"], all_values["prior"],
            all_values["sentiment"], all_values["event"],
        )],
    }
    result = {
        "schema_version": "llm-only-event-response-gate-v8",
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
        "inputs": {"panel": {"path": str(panel_path.resolve()), "sha256": sha256(panel_path)}},
    }
    return prediction_panel, result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--panel-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    prediction_panel, result = evaluate(config)
    write_json(args.panel_output, prediction_panel)
    result["prediction_panel"] = {"path": str(args.panel_output.resolve()), "sha256": sha256(args.panel_output)}
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
