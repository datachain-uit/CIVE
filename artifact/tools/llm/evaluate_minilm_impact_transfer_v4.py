"""Evaluate the predeclared MiniLM external-impact transfer on project outcomes."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from evaluate_llm_event_predictive_gate_v3 import (
    block_bootstrap,
    causal_metadata_features,
    metrics,
    ridge_predict,
    sha256,
    write_json,
)


def daily_impact_features(
    score_records: list[dict], input_by_id: dict[str, dict], dates: list[str],
    kept_ids: dict[str, set[str]],
) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    seen = set()
    for record in score_records:
        headline_id = record.get("headline_id")
        source = input_by_id.get(headline_id)
        if source is None or headline_id in seen:
            raise ValueError("impact score IDs must match project input one-to-one")
        seen.add(headline_id)
        score = float(record["impact_score"])
        if not np.isfinite(score) or record.get("information_date") != source["information_date"]:
            raise ValueError("invalid impact score record")
        date = source["information_date"]
        if headline_id in kept_ids[date]:
            grouped[date].append(score)
    if seen != set(input_by_id):
        raise ValueError("impact score/input ID coverage mismatch")

    result = {}
    for date in dates:
        values = np.asarray(grouped[date], dtype=float)
        if not len(values):
            raise ValueError(f"no impact scores remain for {date}")
        result[date] = {
            "impact_score_mean": float(np.mean(values)),
            "impact_score_max": float(np.max(values)),
            "impact_score_min": float(np.min(values)),
            "impact_score_std": float(np.std(values)),
            "impact_score_abs_mean": float(np.mean(np.abs(values))),
        }
    return result


def evaluate(config: dict, scores_path: Path) -> tuple[dict, dict]:
    for key, item in config["code"].items():
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"code hash differs from predeclaration: {key}")
    source_paths = {key: Path(value["path"]) for key, value in config["sources"].items()}
    for key, path in source_paths.items():
        if sha256(path) != config["sources"][key]["sha256"]:
            raise ValueError(f"source hash differs from predeclaration: {key}")

    scores = json.loads(scores_path.read_text(encoding="utf-8"))
    if scores.get("status") != "frozen-project-headline-external-impact-scores":
        raise ValueError("impact score artifact is not frozen")
    if scores["project_corpus"]["sha256"] != config["sources"]["project_corpus"]["sha256"]:
        raise ValueError("impact score corpus provenance mismatch")
    external_gate_path = Path(scores["external_gate"]["path"])
    if sha256(external_gate_path) != scores["external_gate"]["sha256"]:
        raise ValueError("external gate provenance mismatch")
    external_gate = json.loads(external_gate_path.read_text(encoding="utf-8"))
    if not external_gate.get("passed"):
        raise ValueError("external gate did not authorize transfer evaluation")

    inputs = json.loads(source_paths["project_corpus"].read_text(encoding="utf-8"))["records"]
    market = json.loads(source_paths["market_features"].read_text(encoding="utf-8"))["records"]
    targets = json.loads(source_paths["target_panel"].read_text(encoding="utf-8"))["records"]
    dates = [item["information_date"] for item in targets]
    if dates != sorted(dates) or len(dates) != config["data_gate"]["required_dates"]:
        raise ValueError("target dates are not the frozen ordered panel")
    input_by_id = {item["headline_id"]: item for item in inputs}
    if len(input_by_id) != len(inputs):
        raise ValueError("duplicate project headline_id")
    by_date: dict[str, list[dict]] = defaultdict(list)
    for item in inputs:
        by_date[item["information_date"]].append(item)
    contract = config["feature_contract"]
    metadata, kept_ids, deduplicated = causal_metadata_features(
        by_date, dates, contract["source_domains"], contract["coin_types"],
        contract["recurrence_lookback_days"],
    )
    impact = daily_impact_features(scores["records"], input_by_id, dates, kept_ids)
    market_by_date = {item["information_date"]: item for item in market}
    target_by_date = {item["information_date"]: item for item in targets}
    if set(dates) != set(market_by_date) or set(dates) != set(impact):
        raise ValueError("daily transfer feature coverage mismatch")
    for date in dates:
        if market_by_date[date]["source_snapshot_hash"] != target_by_date[date]["source_snapshot_hash"]:
            raise ValueError("source snapshot hash mismatch")

    market_names = contract["market_numeric"]
    metadata_names = list(metadata[dates[0]])
    impact_names = list(impact[dates[0]])
    rows = []
    for date in dates:
        market_values = [float(market_by_date[date]["features"][name]) for name in market_names]
        metadata_values = market_values + [metadata[date][name] for name in metadata_names]
        rows.append({
            "information_date": date,
            "market": market_values,
            "metadata": metadata_values,
            "impact": metadata_values + [impact[date][name] for name in impact_names],
            "target": float(target_by_date[date]["targets"][config["target"]["field"]]),
        })

    all_predictions = {"market": [], "metadata": [], "impact": [], "target": [], "dates": []}
    fold_results = []
    bootstrap_folds = []
    for fold in config["project_folds"]:
        train = [i for i, row in enumerate(rows) if row["information_date"] <= fold["train_end"]]
        valid = [i for i, row in enumerate(rows) if fold["valid_start"] <= row["information_date"] <= fold["valid_end"]]
        if len(train) != fold["train_records"] or len(valid) != fold["valid_records"]:
            raise ValueError("project fold count mismatch")
        y_train = np.asarray([rows[i]["target"] for i in train])
        y_valid = np.asarray([rows[i]["target"] for i in valid])
        prediction = {}
        for arm in ("market", "metadata", "impact"):
            prediction[arm] = ridge_predict(
                np.asarray([rows[i][arm] for i in train]),
                y_train,
                np.asarray([rows[i][arm] for i in valid]),
                float(config["model"]["alpha"]),
            )
            all_predictions[arm].extend(prediction[arm].tolist())
        all_predictions["target"].extend(y_valid.tolist())
        all_predictions["dates"].extend(rows[i]["information_date"] for i in valid)
        fold_metrics = {arm: metrics(y_valid, prediction[arm]) for arm in ("market", "metadata", "impact")}
        fold_metrics["impact_minus_metadata_delta_mse"] = (
            fold_metrics["metadata"]["mse"] - fold_metrics["impact"]["mse"]
        )
        fold_results.append({"fold": fold["fold"], "validation_records": len(valid), "metrics": fold_metrics})
        bootstrap_folds.append({"y": y_valid, "metadata": prediction["metadata"], "event": prediction["impact"]})

    y = np.asarray(all_predictions["target"])
    overall = {arm: metrics(y, np.asarray(all_predictions[arm])) for arm in ("market", "metadata", "impact")}
    delta = overall["metadata"]["mse"] - overall["impact"]["mse"]
    uncertainty_raw = block_bootstrap(
        bootstrap_folds, int(config["bootstrap"]["iterations"]),
        int(config["bootstrap"]["block_length_days"]), int(config["bootstrap"]["seed"]),
    )
    uncertainty = {
        "paired_delta_mse_95_ci": uncertainty_raw["paired_delta_mse_95_ci"],
        "impact_pearson_95_ci": uncertainty_raw["event_pearson_95_ci"],
    }
    fold_wins = sum(
        item["metrics"]["impact"]["mse"] < item["metrics"]["metadata"]["mse"] for item in fold_results
    )
    checks = {
        "oos_records": len(y) == config["project_gate"]["required_oos_records"],
        "paired_delta_mse_ci_lower_gt_zero": uncertainty["paired_delta_mse_95_ci"][0] > 0,
        "impact_pearson_ci_lower_gt_zero": uncertainty["impact_pearson_95_ci"][0] > 0,
        "impact_mse_fold_wins": fold_wins >= config["project_gate"]["minimum_fold_wins"],
        "impact_predictions_nonconstant": overall["impact"]["prediction_std"] > 0,
    }
    passed = all(checks.values())
    panel = {
        "schema_version": 1,
        "experiment_id": config["experiment_id"],
        "status": "development-external-impact-transfer-predictions",
        "target": config["target"],
        "feature_names": {
            "market": market_names,
            "metadata": market_names + metadata_names,
            "impact": market_names + metadata_names + impact_names,
        },
        "deduplicated_repeated_headlines": deduplicated,
        "records": [{
            "information_date": date,
            "target": target,
            "market_prediction": market_prediction,
            "metadata_prediction": metadata_prediction,
            "impact_prediction": impact_prediction,
        } for date, target, market_prediction, metadata_prediction, impact_prediction in zip(
            all_predictions["dates"], all_predictions["target"], all_predictions["market"],
            all_predictions["metadata"], all_predictions["impact"],
        )],
    }
    result = {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "status": "transfer-gate-pass-overlay-design-authorized" if passed else "transfer-gate-fail-stop-before-threshold-or-backtest",
        "passed": passed,
        "development_outcomes_consulted": True,
        "trading_backtest_consulted": False,
        "oos_records": len(y),
        "target": config["target"],
        "overall": overall,
        "impact_minus_metadata": {
            "paired_delta_mse": delta,
            "relative_mse_reduction": delta / overall["metadata"]["mse"],
            "mse_fold_wins": fold_wins,
        },
        "uncertainty": uncertainty,
        "folds": fold_results,
        "checks": checks,
        "impact_scores": {"path": str(scores_path.resolve()), "sha256": sha256(scores_path)},
    }
    return panel, result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--panel-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    panel, result = evaluate(config, args.scores)
    write_json(args.panel_output, panel)
    result["prediction_panel"] = {
        "path": str(args.panel_output.resolve()),
        "sha256": sha256(args.panel_output),
    }
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
