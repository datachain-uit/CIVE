"""Evaluate eligible v18 assets and apply the frozen family correction."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from eth_transfer_v17_common import FOLDS, block_indices, metrics, pearson, ridge_predict, sha256, write_json
from multicoin_transfer_v18_common import llm_features


def holm_adjust(raw: dict[str, float]) -> dict[str, float]:
    ordered = sorted(raw, key=raw.get)
    adjusted = {}
    running = 0.0
    m = len(ordered)
    for rank, key in enumerate(ordered):
        running = max(running, min(1.0, (m - rank) * raw[key]))
        adjusted[key] = running
    return adjusted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target-panel", type=Path, required=True)
    parser.add_argument("--prediction-panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    targets = json.loads(args.target_panel.read_text(encoding="utf-8"))
    if targets["predeclaration"]["sha256"] != sha256(args.config):
        raise ValueError("target panel uses a different predeclaration")
    for key in ("extraction", "target_builder", "evaluator", "common_helper"):
        item = config["sources"][key]
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"frozen source changed: {key}")
    events = json.loads(Path(config["sources"]["extraction"]["path"]).read_text(encoding="utf-8"))["records"]
    coin_results = {}
    all_predictions = {}
    raw_delta_p = {}
    raw_corr_p = {}
    for asset_index, symbol in enumerate(config["eligible_assets"]):
        rows = targets["assets"][symbol]["records"]
        dates = [row["information_date"] for row in rows]
        aliases = set(config["assets"][symbol]["aliases"])
        generic_names, event_names, features = llm_features(events, dates, aliases)
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
            fold_metrics = {arm: metrics(y_valid, prediction) for arm, prediction in predictions.items()}
            fold_results.append({"fold": fold["fold"], "records": len(valid), "metrics": fold_metrics})
            bootstrap_folds.append({"y": y_valid, "generic": predictions["generic"], "event": predictions["event"]})
            for j, index in enumerate(valid):
                prediction_rows.append({
                    "information_date": dates[index],
                    "fold": fold["fold"],
                    "target": float(y_valid[j]),
                    **{f"{arm}_prediction": float(prediction[j]) for arm, prediction in predictions.items()},
                })
        y = np.asarray([row["target"] for row in prediction_rows])
        generic = np.asarray([row["generic_prediction"] for row in prediction_rows])
        event = np.asarray([row["event_prediction"] for row in prediction_rows])
        prior = np.asarray([row["prior_prediction"] for row in prediction_rows])
        rng = np.random.default_rng(int(config["bootstrap"]["seed"]) + asset_index)
        delta_samples = []
        correlation_samples = []
        for _ in range(int(config["bootstrap"]["iterations"])):
            samples = []
            for fold in bootstrap_folds:
                indices = block_indices(len(fold["y"]), int(config["bootstrap"]["block_length_days"]), rng)
                samples.append({key: value[indices] for key, value in fold.items()})
            sample_y = np.concatenate([sample["y"] for sample in samples])
            sample_generic = np.concatenate([sample["generic"] for sample in samples])
            sample_event = np.concatenate([sample["event"] for sample in samples])
            delta_samples.append(float(np.mean((sample_y - sample_generic) ** 2 - (sample_y - sample_event) ** 2)))
            correlation_samples.append(pearson(sample_event, sample_y))
        ci_delta = [float(value) for value in np.quantile(delta_samples, [0.025, 0.975])]
        ci_corr = [float(value) for value in np.quantile(correlation_samples, [0.025, 0.975])]
        fold_wins = sum(item["metrics"]["event"]["mse"] < item["metrics"]["generic"]["mse"] for item in fold_results)
        raw_delta_p[symbol] = (1 + sum(value <= 0 for value in delta_samples)) / (len(delta_samples) + 1)
        raw_corr_p[symbol] = (1 + sum(value <= 0 for value in correlation_samples)) / (len(correlation_samples) + 1)
        checks = {
            "required_oos_records": len(rows) == 1079 and len(y) == 699,
            "event_minus_generic_mse_ci_lower_gt_zero": ci_delta[0] > 0,
            "event_pearson_ci_lower_gt_zero": ci_corr[0] > 0,
            "event_mse_wins_at_least_3_of_5_folds": fold_wins >= 3,
            "event_prediction_nonconstant": float(np.std(event)) > 0,
        }
        coin_results[symbol] = {
            "experiment_id": config["assets"][symbol]["experiment_id"],
            "overall": {"prior": metrics(y, prior), "generic": metrics(y, generic), "event": metrics(y, event)},
            "event_minus_generic": {
                "delta_mse": float(np.mean((y - generic) ** 2 - (y - event) ** 2)),
                "delta_mse_95_ci": ci_delta,
                "pearson_95_ci": ci_corr,
                "fold_wins": fold_wins,
                "raw_one_sided_p_delta_mse": raw_delta_p[symbol],
                "raw_one_sided_p_pearson": raw_corr_p[symbol],
            },
            "folds": fold_results,
            "checks": checks,
            "passed_per_coin_gate": all(checks.values()),
        }
        all_predictions[symbol] = {"feature_names": {"generic": generic_names, "event": event_names}, "records": prediction_rows}
    adjusted_delta = holm_adjust(raw_delta_p)
    adjusted_corr = holm_adjust(raw_corr_p)
    family_success_assets = []
    for symbol, result in coin_results.items():
        result["event_minus_generic"]["holm_adjusted_p_delta_mse"] = adjusted_delta[symbol]
        result["event_minus_generic"]["holm_adjusted_p_pearson"] = adjusted_corr[symbol]
        if adjusted_delta[symbol] < 0.05 and adjusted_corr[symbol] < 0.05 and result["checks"]["event_mse_wins_at_least_3_of_5_folds"] and result["checks"]["event_prediction_nonconstant"]:
            family_success_assets.append(symbol)
    passed = bool(family_success_assets)
    panel = {
        "schema_version": 1,
        "family_id": config["family_id"],
        "status": "DEVELOPMENT_TIME_OOS_PREDICTION_PANEL",
        "assets": all_predictions,
    }
    write_json(args.prediction_panel, panel)
    result = {
        "schema_version": 1,
        "family_id": config["family_id"],
        "status": "PASS_FAMILY_TRANSFER" if passed else "FAIL_FAMILY_TRANSFER",
        "passed": passed,
        "outcomes_consulted": True,
        "trading_backtest_consulted": False,
        "eligible_assets": config["eligible_assets"],
        "stopped_before_target": config["stopped_assets"],
        "family_success_assets": family_success_assets,
        "assets": coin_results,
        "inputs": {
            "predeclaration": {"path": str(args.config), "sha256": sha256(args.config)},
            "target_panel": {"path": str(args.target_panel), "sha256": sha256(args.target_panel)},
            "prediction_panel": {"path": str(args.prediction_panel), "sha256": sha256(args.prediction_panel)},
        },
        "interpretation": "Development transfer family only; no direct claim about incremental value over Tech.",
    }
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
