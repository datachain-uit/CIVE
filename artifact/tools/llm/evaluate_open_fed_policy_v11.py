"""Evaluate the frozen three-arm v11 LLM-only development gate."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from evaluate_llm_only_event_conditioned_v7 import block_bootstrap, metrics, ridge_predict, sha256, write_json


def indices(records: list[dict], fold: dict) -> tuple[list[int], list[int]]:
    train = [i for i, row in enumerate(records) if row["decision_at"] <= fold["train_end"]]
    valid = [i for i, row in enumerate(records) if fold["valid_start"] <= row["decision_at"] <= fold["valid_end"]]
    return train, valid


def evaluate(config: dict) -> dict:
    panel_path = Path(config["sources"]["panel"]["path"])
    if sha256(panel_path) != config["sources"]["panel"]["sha256"]:
        raise ValueError("panel hash mismatch")
    records = json.loads(panel_path.read_text(encoding="utf-8"))["records"]
    if not records or any(not all(key.startswith("llm_") for key in row["event_features"] | row["generic_features"]) for row in records):
        raise ValueError("non-LLM feature or empty panel")
    values = {key: [] for key in ("target", "prior", "generic", "event")}
    boot, folds = [], []
    for fold in config["folds"]:
        train, valid = indices(records, fold)
        if len(train) != fold["train_records"] or len(valid) != fold["valid_records"]:
            raise ValueError("fold count mismatch")
        y_train = np.array([records[i]["target_h4_return"] for i in train])
        y_valid = np.array([records[i]["target_h4_return"] for i in valid])
        predictions = {"prior": np.full(len(valid), y_train.mean())}
        for arm, key in (("generic", "generic_features"), ("event", "event_features")):
            names = list(records[0][key])
            x_train = np.array([[records[i][key][name] for name in names] for i in train])
            x_valid = np.array([[records[i][key][name] for name in names] for i in valid])
            predictions[arm] = ridge_predict(x_train, y_train, x_valid, float(config["model"]["alpha"]))
        values["target"].extend(y_valid.tolist())
        for arm in ("prior", "generic", "event"): values[arm].extend(predictions[arm].tolist())
        fold_metrics = {arm: metrics(y_valid, predictions[arm]) for arm in ("prior", "generic", "event")}
        folds.append({"fold": fold["fold"], "validation_records": len(valid), "metrics": fold_metrics})
        boot.append({"y": y_valid, "sentiment": predictions["generic"], "event": predictions["event"]})
    y = np.array(values["target"])
    overall = {arm: metrics(y, np.array(values[arm])) for arm in ("prior", "generic", "event")}
    uncertainty = block_bootstrap(boot, config["bootstrap"]["iterations"], config["bootstrap"]["block_length_records"], config["bootstrap"]["seed"])
    # A second paired bootstrap uses the same routine with prior in the comparator slot.
    prior_boot = [{"y": row["y"], "sentiment": np.full(len(row["y"]), np.nan), "event": row["event"]} for row in boot]
    offset = 0
    for item, fold in zip(prior_boot, config["folds"]):
        count = fold["valid_records"]
        item["sentiment"] = np.array(values["prior"][offset:offset + count]); offset += count
    prior_uncertainty = block_bootstrap(prior_boot, config["bootstrap"]["iterations"], config["bootstrap"]["block_length_records"], config["bootstrap"]["seed"] + 1)
    wins_generic = sum(row["metrics"]["event"]["mse"] < row["metrics"]["generic"]["mse"] for row in folds)
    wins_prior = sum(row["metrics"]["event"]["mse"] < row["metrics"]["prior"]["mse"] for row in folds)
    checks = {
        "event_vs_generic_mse_ci_lower_gt_zero": uncertainty["paired_delta_mse_95_ci"][0] > 0,
        "event_vs_prior_mse_ci_lower_gt_zero": prior_uncertainty["paired_delta_mse_95_ci"][0] > 0,
        "event_pearson_ci_lower_gt_zero": uncertainty["event_pearson_95_ci"][0] > 0,
        "event_wins_majority_vs_generic": wins_generic >= config["gate"]["minimum_fold_wins"],
        "event_wins_majority_vs_prior": wins_prior >= config["gate"]["minimum_fold_wins"],
        "event_nonconstant": overall["event"]["prediction_std"] > 0,
    }
    passed = all(checks.values())
    return {"schema_version": "open-fed-policy-gate-v11", "evaluated_at": datetime.now(timezone.utc).isoformat(), "status": "development-gate-pass" if passed else "development-gate-fail-stop-before-backtest", "passed": passed, "development_only": True, "strict_point_in_time": False, "technical_or_market_features_used": False, "oos_records": len(y), "overall": overall, "folds": folds, "event_vs_generic": {"paired_delta_mse": overall["generic"]["mse"] - overall["event"]["mse"], "uncertainty": uncertainty, "fold_wins": wins_generic}, "event_vs_prior": {"paired_delta_mse": overall["prior"]["mse"] - overall["event"]["mse"], "uncertainty": prior_uncertainty, "fold_wins": wins_prior}, "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--config", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    result = evaluate(json.loads(args.config.read_text(encoding="utf-8"))); write_json(args.output, result); print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
