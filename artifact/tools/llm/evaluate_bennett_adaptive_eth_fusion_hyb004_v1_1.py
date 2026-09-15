"""HYB-004 v1.1: causal initialization for the adaptive-MSFE transfer baseline."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np

import evaluate_bennett_adaptive_eth_fusion_hyb004 as base
from eth_transfer_v17_common import ridge_predict, write_json


def adaptive_predictions(y_train, x_tech_train, x_llm_train, y_valid, x_tech_valid, x_llm_valid, valid_rows, alpha, window):
    p_tech = ridge_predict(x_tech_train, y_train, x_tech_valid, alpha)
    p_llm = ridge_predict(x_llm_train, y_train, x_llm_valid, alpha)
    tech_errors, llm_errors, pending = [], [], []
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
        if len(tech_errors) < window:
            weight_tech = 0.5
        else:
            mse_tech = max(float(np.mean(tech_errors)), 1e-12)
            mse_llm = max(float(np.mean(llm_errors)), 1e-12)
            inv_tech, inv_llm = 1.0 / mse_tech, 1.0 / mse_llm
            weight_tech = inv_tech / (inv_tech + inv_llm)
        prediction = weight_tech * p_tech[i] + (1.0 - weight_tech) * p_llm[i]
        fusion.append(prediction)
        weights.append(weight_tech)
        pending.append({"exit_at": row["exit_at"], "tech_error": float((y_valid[i]-p_tech[i])**2), "llm_error": float((y_valid[i]-p_llm[i])**2)})
    return p_tech, p_llm, np.asarray(fusion), np.asarray(weights)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target-panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base.adaptive_predictions = adaptive_predictions
    result = base.evaluate(args.config, args.target_panel)
    result["remediation"] = {
        "post_outcome": True,
        "reason": "v1 initialized recent-MSFE weights from in-sample fitted residuals; v1.1 uses 0.5/0.5 until 30 matured OOS forecast errors exist",
        "claim_scope": "reproducible development transfer baseline only; not predeclared validation",
    }
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "overall": result["overall"], "contrast": result["fusion_minus_tech"]}, indent=2))


if __name__ == "__main__":
    main()

