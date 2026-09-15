"""Train fold-local supervised contrastive projections and evaluate the v6 gate."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from run_fulltext_market_impact_v5 import metrics, paired_bootstrap, validate_files
from run_minilm_external_impact_v4 import ridge_apply, ridge_fit, sha256, write_json


def return_classes(y: np.ndarray) -> tuple[np.ndarray, list[float]]:
    thresholds = np.quantile(y, [1 / 3, 2 / 3])
    labels = np.digitize(y, thresholds, right=True).astype(np.int64)
    if len(np.unique(labels)) != 3:
        raise ValueError("training return quantiles do not form three classes")
    return labels, [float(value) for value in thresholds]


def supervised_contrastive_loss(torch, projected, labels, temperature: float):
    similarity = projected @ projected.T / temperature
    count = len(labels)
    eye = torch.eye(count, dtype=torch.bool, device=projected.device)
    positive = labels[:, None].eq(labels[None, :]) & ~eye
    valid = positive.sum(dim=1) > 0
    similarity = similarity.masked_fill(eye, float("-inf"))
    log_probability = similarity - torch.logsumexp(similarity, dim=1, keepdim=True)
    positive_log_probability = log_probability.masked_fill(~positive, 0.0).sum(dim=1)
    per_anchor = -positive_log_probability[valid] / positive.sum(dim=1)[valid]
    return per_anchor.mean()


def train_projection(x_train: np.ndarray, y_train: np.ndarray, x_valid: np.ndarray,
                     config: dict, fold: int) -> tuple[np.ndarray, np.ndarray, dict, dict]:
    import torch

    seed = int(config["training"]["seed_base"]) + fold
    torch.manual_seed(seed)
    torch.set_num_threads(int(config["training"]["cpu_threads"]))
    torch.use_deterministic_algorithms(True)
    mean = np.mean(x_train, axis=0)
    scale = np.std(x_train, axis=0)
    scale[scale == 0] = 1.0
    train_values = torch.tensor((x_train - mean) / scale, dtype=torch.float32)
    valid_values = torch.tensor((x_valid - mean) / scale, dtype=torch.float32)
    labels_np, thresholds = return_classes(y_train)
    labels = torch.tensor(labels_np, dtype=torch.long)
    model = torch.nn.Sequential(
        torch.nn.Linear(int(config["projection"]["input_dimensions"]), int(config["projection"]["hidden_dimensions"])),
        torch.nn.GELU(),
        torch.nn.Linear(int(config["projection"]["hidden_dimensions"]), int(config["projection"]["output_dimensions"])),
    )
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=float(config["training"]["learning_rate"]),
        weight_decay=float(config["training"]["weight_decay"]),
    )
    generator = torch.Generator().manual_seed(seed)
    dataset = torch.utils.data.TensorDataset(train_values, labels)
    loader = torch.utils.data.DataLoader(
        dataset, batch_size=int(config["training"]["batch_size"]), shuffle=True,
        generator=generator, num_workers=0, drop_last=False,
    )
    epoch_losses = []
    model.train()
    for _ in range(int(config["training"]["epochs"])):
        losses = []
        for batch_values, batch_labels in loader:
            optimizer.zero_grad(set_to_none=True)
            projected = torch.nn.functional.normalize(model(batch_values), p=2, dim=1)
            loss = supervised_contrastive_loss(
                torch, projected, batch_labels, float(config["training"]["temperature"])
            )
            if not torch.isfinite(loss):
                raise ValueError("non-finite supervised contrastive loss")
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))
        epoch_losses.append(float(np.mean(losses)))
    model.eval()
    with torch.inference_mode():
        projected_train = torch.nn.functional.normalize(model(train_values), p=2, dim=1).numpy().astype(np.float64)
        projected_valid = torch.nn.functional.normalize(model(valid_values), p=2, dim=1).numpy().astype(np.float64)
    state = {
        "input_mean": mean.astype(np.float32),
        "input_scale": scale.astype(np.float32),
        "layer1_weight": model[0].weight.detach().numpy(),
        "layer1_bias": model[0].bias.detach().numpy(),
        "layer2_weight": model[2].weight.detach().numpy(),
        "layer2_bias": model[2].bias.detach().numpy(),
    }
    diagnostics = {
        "seed": seed,
        "return_class_thresholds": thresholds,
        "class_counts": np.bincount(labels_np, minlength=3).tolist(),
        "epoch_losses": epoch_losses,
        "final_loss": epoch_losses[-1],
    }
    return projected_train, projected_valid, diagnostics, state


def save_states(path: Path, states: list[dict]) -> None:
    arrays = {}
    for fold, state in enumerate(states, start=1):
        for key, value in state.items():
            arrays[f"fold{fold}_{key}"] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.npz")
    np.savez_compressed(temporary, **arrays)
    temporary.replace(path)


def evaluate(config: dict, output: Path, models_output: Path) -> dict:
    validate_files(config["code"], "code")
    validate_files(config["sources"], "source")
    panel = json.loads(Path(config["sources"]["panel"]["path"]).read_text(encoding="utf-8"))
    arrays = np.load(Path(config["sources"]["v5_embeddings"]["path"]))
    decisions = arrays["decision_at"].tolist()
    embeddings = arrays["embeddings"].astype(np.float64)
    if decisions != [item["decision_at"] for item in panel["records"]]:
        raise ValueError("v5 embedding/panel order mismatch")
    if len(decisions) != config["data_gate"]["required_buckets"]:
        raise ValueError("v6 bucket count mismatch")
    market = np.asarray([list(item["market_features"].values()) for item in panel["records"]], dtype=float)
    target = np.asarray([item["target_h24_return"] for item in panel["records"]], dtype=float)

    all_values = {"target": [], "market": [], "contrastive": [], "fusion": [], "decision_at": []}
    fold_results = []
    bootstrap_folds = []
    states = []
    for fold in config["folds"]:
        train = [i for i, value in enumerate(decisions) if value <= fold["train_end"]]
        valid = [i for i, value in enumerate(decisions) if fold["valid_start"] <= value <= fold["valid_end"]]
        if len(train) != fold["train_records"] or len(valid) != fold["valid_records"]:
            raise ValueError("v6 fold count mismatch")
        projected_train, projected_valid, diagnostics, state = train_projection(
            embeddings[train], target[train], embeddings[valid], config, int(fold["fold"])
        )
        states.append(state)
        train_fusion = np.concatenate((market[train], projected_train), axis=1)
        valid_fusion = np.concatenate((market[valid], projected_valid), axis=1)
        arm_data = {
            "market": (market[train], market[valid]),
            "contrastive": (projected_train, projected_valid),
            "fusion": (train_fusion, valid_fusion),
        }
        predictions = {}
        for name, (x_train, x_valid) in arm_data.items():
            model = ridge_fit(x_train, target[train], float(config["model"]["alpha"]))
            predictions[name] = ridge_apply(model, x_valid)
            all_values[name].extend(predictions[name].tolist())
        y_valid = target[valid]
        all_values["target"].extend(y_valid.tolist())
        all_values["decision_at"].extend(decisions[i] for i in valid)
        fold_metrics = {name: metrics(y_valid, predictions[name]) for name in arm_data}
        fold_metrics["fusion_minus_market_delta_mse"] = fold_metrics["market"]["mse"] - fold_metrics["fusion"]["mse"]
        fold_results.append({
            "fold": fold["fold"], "train_records": len(train), "validation_records": len(valid),
            "training": diagnostics, "metrics": fold_metrics,
        })
        bootstrap_folds.append({"y": y_valid, "market": predictions["market"], "fusion": predictions["fusion"]})

    save_states(models_output, states)
    y = np.asarray(all_values["target"])
    overall = {name: metrics(y, np.asarray(all_values[name])) for name in ("market", "contrastive", "fusion")}
    uncertainty = paired_bootstrap(
        bootstrap_folds, int(config["bootstrap"]["iterations"]),
        int(config["bootstrap"]["block_length_records"]), int(config["bootstrap"]["seed"]),
    )
    fold_wins = sum(item["metrics"]["fusion"]["mse"] < item["metrics"]["market"]["mse"] for item in fold_results)
    checks = {
        "required_oos_records": len(y) == config["gate"]["required_oos_records"],
        "paired_delta_mse_ci_lower_gt_zero": uncertainty["paired_delta_mse_95_ci"][0] > 0,
        "fusion_pearson_ci_lower_gt_zero": uncertainty["fusion_pearson_95_ci"][0] > 0,
        "minimum_fold_wins": fold_wins >= config["gate"]["minimum_fold_wins"],
        "fusion_predictions_nonconstant": overall["fusion"]["prediction_std"] > 0,
    }
    passed = all(checks.values())
    result = {
        "schema_version": "llm-contrastive-market-impact-gate-v6",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "status": "predictive-gate-pass-overlay-predeclaration-authorized" if passed else "predictive-gate-fail-stop-before-threshold-or-backtest",
        "passed": passed,
        "prior_v5_outcomes_consulted": True,
        "development_outcomes_consulted": True,
        "trading_backtest_consulted": False,
        "oos_records": len(y),
        "overall": overall,
        "fusion_minus_market": {
            "paired_delta_mse": overall["market"]["mse"] - overall["fusion"]["mse"],
            "relative_mse_reduction": (overall["market"]["mse"] - overall["fusion"]["mse"]) / overall["market"]["mse"],
            "fold_wins": fold_wins,
        },
        "uncertainty": uncertainty,
        "folds": fold_results,
        "checks": checks,
        "models": {"path": str(models_output.resolve()), "sha256": sha256(models_output)},
        "predictions": [{
            "decision_at": decision, "target": actual,
            "market_prediction": market_prediction,
            "contrastive_prediction": contrastive_prediction,
            "fusion_prediction": fusion_prediction,
        } for decision, actual, market_prediction, contrastive_prediction, fusion_prediction in zip(
            all_values["decision_at"], all_values["target"], all_values["market"],
            all_values["contrastive"], all_values["fusion"],
        )],
    }
    write_json(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models-output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = evaluate(config, args.output, args.models_output)
    summary = {key: result[key] for key in ("status", "passed", "oos_records", "overall", "fusion_minus_market", "uncertainty", "checks")}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
