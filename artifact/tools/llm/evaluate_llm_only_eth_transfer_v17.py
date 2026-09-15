"""Evaluate the predeclared LLM-only direct-ETH transfer diagnostic."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from eth_transfer_v17_common import FOLDS, block_indices, llm_features, metrics, pearson, ridge_predict, sha256, write_json


def evaluate(config_path: Path, target_path: Path) -> tuple[dict, dict]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    target_payload = json.loads(target_path.read_text(encoding="utf-8"))
    for key in ("extraction", "target_builder", "llm_evaluator", "common_helper"):
        path = Path(config["sources"][key]["path"])
        if sha256(path) != config["sources"][key]["sha256"]:
            raise ValueError(f"{key} hash mismatch")
    events = json.loads(Path(config["sources"]["extraction"]["path"]).read_text(encoding="utf-8"))["records"]
    rows = target_payload["records"]
    dates = [row["information_date"] for row in rows]
    generic_names, event_names, features = llm_features(events, dates)
    prediction_rows = []
    fold_results = []
    bootstrap_folds = []
    for fold in FOLDS:
        train = [i for i, row in enumerate(rows) if row["information_date"] <= fold["train_end"]]
        valid = [i for i, row in enumerate(rows) if fold["valid_start"] <= row["information_date"] <= fold["valid_end"]]
        y_train = np.asarray([rows[i]["target_h24_return"] for i in train])
        y_valid = np.asarray([rows[i]["target_h24_return"] for i in valid])
        predictions = {"prior": np.full(len(valid), float(np.mean(y_train)))}
        for arm, names in (("generic", generic_names), ("event", event_names)):
            x_train = np.asarray([[features[dates[i]][name] for name in names] for i in train])
            x_valid = np.asarray([[features[dates[i]][name] for name in names] for i in valid])
            predictions[arm] = ridge_predict(x_train, y_train, x_valid, float(config["model"]["alpha"]))
        fold_metrics = {arm: metrics(y_valid, pred) for arm, pred in predictions.items()}
        fold_results.append({"fold": fold["fold"], "records": len(valid), "metrics": fold_metrics})
        bootstrap_folds.append({"y": y_valid, "generic": predictions["generic"], "event": predictions["event"]})
        for j, index in enumerate(valid):
            prediction_rows.append({
                "information_date": dates[index], "fold": fold["fold"], "target": float(y_valid[j]),
                **{f"{arm}_prediction": float(pred[j]) for arm, pred in predictions.items()},
            })
    y = np.asarray([row["target"] for row in prediction_rows])
    generic = np.asarray([row["generic_prediction"] for row in prediction_rows])
    event = np.asarray([row["event_prediction"] for row in prediction_rows])
    prior = np.asarray([row["prior_prediction"] for row in prediction_rows])
    rng = np.random.default_rng(int(config["bootstrap"]["seed"]))
    delta_samples, correlation_samples = [], []
    for _ in range(int(config["bootstrap"]["iterations"])):
        samples = []
        for fold in bootstrap_folds:
            idx = block_indices(len(fold["y"]), int(config["bootstrap"]["block_length_days"]), rng)
            samples.append({key: value[idx] for key, value in fold.items()})
        sy = np.concatenate([x["y"] for x in samples])
        sg = np.concatenate([x["generic"] for x in samples])
        se = np.concatenate([x["event"] for x in samples])
        delta_samples.append(float(np.mean((sy - sg) ** 2 - (sy - se) ** 2)))
        correlation_samples.append(pearson(se, sy))
    ci_delta = [float(x) for x in np.quantile(delta_samples, [0.025, 0.975])]
    ci_corr = [float(x) for x in np.quantile(correlation_samples, [0.025, 0.975])]
    fold_wins = sum(x["metrics"]["event"]["mse"] < x["metrics"]["generic"]["mse"] for x in fold_results)
    checks = {
        "required_oos_records": len(rows) == 1079 and len(y) == 699,
        "event_minus_generic_mse_ci_lower_gt_zero": ci_delta[0] > 0,
        "event_pearson_ci_lower_gt_zero": ci_corr[0] > 0,
        "event_mse_wins_at_least_3_of_5_folds": fold_wins >= 3,
        "event_prediction_nonconstant": float(np.std(event)) > 0,
    }
    passed = all(checks.values())
    panel = {
        "schema_version": 1, "experiment_id": config["experiment_id"],
        "status": "DEVELOPMENT_TIME_OOS_PREDICTION_PANEL", "feature_names": {"generic": generic_names, "event": event_names},
        "records": prediction_rows,
    }
    result = {
        "schema_version": 1, "experiment_id": config["experiment_id"],
        "status": "PASS_BACKTEST_DESIGN_AUTHORIZED" if passed else "FAIL_STOP_BEFORE_LLM_ONLY_BACKTEST",
        "passed": passed, "outcomes_consulted": True, "trading_backtest_consulted": False,
        "scope": "ETH transfer diagnostic using BTC-centric v3.9 extractor fields; development, not replication or sealed validation.",
        "overall": {"prior": metrics(y, prior), "generic": metrics(y, generic), "event": metrics(y, event)},
        "event_minus_generic": {"delta_mse": float(np.mean((y-generic)**2 - (y-event)**2)), "delta_mse_95_ci": ci_delta, "pearson_95_ci": ci_corr, "fold_wins": fold_wins},
        "folds": fold_results, "checks": checks,
        "inputs": {"predeclaration": {"path": str(config_path), "sha256": sha256(config_path)}, "target_panel": {"path": str(target_path), "sha256": sha256(target_path)}},
    }
    return panel, result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target-panel", type=Path, required=True)
    parser.add_argument("--prediction-panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    panel, result = evaluate(args.config, args.target_panel)
    write_json(args.prediction_panel, panel)
    result["prediction_panel"] = {"path": str(args.prediction_panel), "sha256": sha256(args.prediction_panel)}
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "overall": result["overall"], "contrast": result["event_minus_generic"]}, indent=2))


if __name__ == "__main__":
    main()

