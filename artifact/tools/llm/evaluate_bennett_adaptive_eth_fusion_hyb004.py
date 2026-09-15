"""Bennett-style adaptive recent-MSFE Tech+LLM transfer benchmark on ETH."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np

from eth_transfer_v17_common import FOLDS, block_indices, llm_features, metrics, ridge_predict, sha256, write_json


def strategy_metrics(returns: np.ndarray) -> dict[str, float]:
    equity = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(equity)
    std = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    return {
        "compounded_net_return": float(equity[-1] - 1.0),
        "annualized_sharpe": float(np.mean(returns) / std * np.sqrt(365.0)) if std else 0.0,
        "max_drawdown": float(np.max(1.0 - equity / peak)),
        "mean_daily_net_return": float(np.mean(returns)),
    }


def adaptive_predictions(y_train, x_tech_train, x_llm_train, y_valid, x_tech_valid, x_llm_valid, valid_rows, alpha, window):
    p_tech = ridge_predict(x_tech_train, y_train, x_tech_valid, alpha)
    p_llm = ridge_predict(x_llm_train, y_train, x_llm_valid, alpha)
    fitted_tech = ridge_predict(x_tech_train, y_train, x_tech_train, alpha)
    fitted_llm = ridge_predict(x_llm_train, y_train, x_llm_train, alpha)
    tech_errors = list((y_train[-window:] - fitted_tech[-window:]) ** 2)
    llm_errors = list((y_train[-window:] - fitted_llm[-window:]) ** 2)
    pending = []
    fusion, weights = [], []
    for i, row in enumerate(valid_rows):
        now = datetime.fromisoformat(row["available_at"])
        matured = [item for item in pending if datetime.fromisoformat(item["exit_at"]) <= now]
        pending = [item for item in pending if datetime.fromisoformat(item["exit_at"]) > now]
        for item in matured:
            tech_errors.append(item["tech_error"])
            llm_errors.append(item["llm_error"])
        tech_errors = tech_errors[-window:]
        llm_errors = llm_errors[-window:]
        mse_tech = max(float(np.mean(tech_errors)), 1e-12)
        mse_llm = max(float(np.mean(llm_errors)), 1e-12)
        inv_tech, inv_llm = 1.0 / mse_tech, 1.0 / mse_llm
        weight_tech = inv_tech / (inv_tech + inv_llm)
        prediction = weight_tech * p_tech[i] + (1.0 - weight_tech) * p_llm[i]
        fusion.append(prediction)
        weights.append(weight_tech)
        pending.append({"exit_at": row["exit_at"], "tech_error": float((y_valid[i]-p_tech[i])**2), "llm_error": float((y_valid[i]-p_llm[i])**2)})
    return p_tech, p_llm, np.asarray(fusion), np.asarray(weights)


def net_returns(rows, predictions, one_way_cost):
    positions = np.where(predictions >= 0.0, 1.0, -1.0)
    returns, previous = [], 0.0
    for row, position in zip(rows, positions):
        turnover = abs(position - previous)
        net = position * float(row["target_h24_return"]) - position * float(row["funding_rate_sum_h24"]) - turnover * one_way_cost
        returns.append(net)
        previous = position
    if returns:
        returns[-1] -= abs(previous) * one_way_cost
    return positions, np.asarray(returns)


def evaluate(config_path: Path, target_path: Path) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    for key in ("extraction", "hybrid_evaluator", "common_helper"):
        path = Path(config["sources"][key]["path"])
        if sha256(path) != config["sources"][key]["sha256"]:
            raise ValueError(f"{key} hash mismatch")
    events = json.loads(Path(config["sources"]["extraction"]["path"]).read_text(encoding="utf-8"))["records"]
    rows = json.loads(target_path.read_text(encoding="utf-8"))["records"]
    dates = [row["information_date"] for row in rows]
    _, llm_names, llm = llm_features(events, dates)
    tech_names = list(rows[0]["tech_features"])
    prediction_rows, fold_results, bootstrap_folds = [], [], []
    for fold in FOLDS:
        train = [i for i, row in enumerate(rows) if row["information_date"] <= fold["train_end"]]
        valid = [i for i, row in enumerate(rows) if fold["valid_start"] <= row["information_date"] <= fold["valid_end"]]
        y_train = np.asarray([rows[i]["target_h24_return"] for i in train])
        y_valid = np.asarray([rows[i]["target_h24_return"] for i in valid])
        x_tech_train = np.asarray([[rows[i]["tech_features"][n] for n in tech_names] for i in train])
        x_tech_valid = np.asarray([[rows[i]["tech_features"][n] for n in tech_names] for i in valid])
        x_llm_train = np.asarray([[llm[dates[i]][n] for n in llm_names] for i in train])
        x_llm_valid = np.asarray([[llm[dates[i]][n] for n in llm_names] for i in valid])
        valid_rows = [rows[i] for i in valid]
        p_tech, p_llm, p_fusion, weights = adaptive_predictions(
            y_train, x_tech_train, x_llm_train, y_valid, x_tech_valid, x_llm_valid, valid_rows,
            float(config["model"]["alpha"]), int(config["adaptive_fusion"]["recent_msfe_window"]),
        )
        _, r_tech = net_returns(valid_rows, p_tech, float(config["execution"]["one_way_cost_rate"]))
        _, r_fusion = net_returns(valid_rows, p_fusion, float(config["execution"]["one_way_cost_rate"]))
        fold_results.append({
            "fold": fold["fold"], "records": len(valid), "tech": metrics(y_valid, p_tech), "llm": metrics(y_valid, p_llm),
            "fusion": metrics(y_valid, p_fusion), "strategy_tech": strategy_metrics(r_tech), "strategy_fusion": strategy_metrics(r_fusion),
            "mean_tech_weight": float(np.mean(weights)),
        })
        bootstrap_folds.append({"y": y_valid, "tech": p_tech, "fusion": p_fusion, "r_tech": r_tech, "r_fusion": r_fusion})
        for j, index in enumerate(valid):
            prediction_rows.append({
                "information_date": dates[index], "fold": fold["fold"], "target": float(y_valid[j]),
                "tech_prediction": float(p_tech[j]), "llm_prediction": float(p_llm[j]), "fusion_prediction": float(p_fusion[j]),
                "tech_weight": float(weights[j]), "tech_net_return": float(r_tech[j]), "fusion_net_return": float(r_fusion[j]),
            })
    y = np.asarray([r["target"] for r in prediction_rows])
    tech = np.asarray([r["tech_prediction"] for r in prediction_rows])
    fusion = np.asarray([r["fusion_prediction"] for r in prediction_rows])
    r_tech = np.asarray([r["tech_net_return"] for r in prediction_rows])
    r_fusion = np.asarray([r["fusion_net_return"] for r in prediction_rows])
    rng = np.random.default_rng(int(config["bootstrap"]["seed"]))
    mse_delta, net_delta = [], []
    for _ in range(int(config["bootstrap"]["iterations"])):
        samples = []
        for f in bootstrap_folds:
            idx = block_indices(len(f["y"]), int(config["bootstrap"]["block_length_days"]), rng)
            samples.append({k: v[idx] for k, v in f.items()})
        sy = np.concatenate([x["y"] for x in samples]); st = np.concatenate([x["tech"] for x in samples]); sf = np.concatenate([x["fusion"] for x in samples])
        rt = np.concatenate([x["r_tech"] for x in samples]); rf = np.concatenate([x["r_fusion"] for x in samples])
        mse_delta.append(float(np.mean((sy-st)**2 - (sy-sf)**2)))
        net_delta.append(float(np.mean(rf-rt)))
    ci_mse = [float(x) for x in np.quantile(mse_delta, [0.025, 0.975])]
    ci_net = [float(x) for x in np.quantile(net_delta, [0.025, 0.975])]
    fold_wins = sum(f["fusion"]["mse"] < f["tech"]["mse"] for f in fold_results)
    checks = {
        "required_oos_records": len(y) == 699,
        "fusion_minus_tech_mse_ci_lower_gt_zero": ci_mse[0] > 0,
        "fusion_minus_tech_net_ci_lower_gt_zero": ci_net[0] > 0,
        "fusion_mse_wins_at_least_3_of_5_folds": fold_wins >= 3,
    }
    passed = all(checks.values())
    return {
        "schema_version": 1, "experiment_id": config["experiment_id"],
        "status": "EXPLORATORY_TRANSFER_PASS" if passed else "EXPLORATORY_TRANSFER_FAIL",
        "passed": passed, "outcomes_consulted": True, "trading_backtest_consulted": True,
        "external_method": config["external_method"],
        "scope": "Bennett-style adaptive recent-MSFE transfer, not a replication; project LLM representation and execution are retained.",
        "overall": {"tech": metrics(y, tech), "fusion": metrics(y, fusion), "strategy_tech": strategy_metrics(r_tech), "strategy_fusion": strategy_metrics(r_fusion)},
        "fusion_minus_tech": {"delta_mse": float(np.mean((y-tech)**2-(y-fusion)**2)), "delta_mse_95_ci": ci_mse, "mean_daily_net_delta": float(np.mean(r_fusion-r_tech)), "mean_daily_net_delta_95_ci": ci_net, "mse_fold_wins": fold_wins},
        "checks": checks, "folds": fold_results, "records": prediction_rows,
        "inputs": {"predeclaration": {"path": str(config_path), "sha256": sha256(config_path)}, "target_panel": {"path": str(target_path), "sha256": sha256(target_path)}},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target-panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.config, args.target_panel)
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "overall": result["overall"], "contrast": result["fusion_minus_tech"]}, indent=2))


if __name__ == "__main__":
    main()

