"""Encode full-text news buckets and evaluate the predeclared v5 impact gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from run_minilm_external_impact_v4 import ridge_apply, ridge_fit, sha256, write_json


def validate_files(items: dict, label: str) -> None:
    for key, item in items.items():
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"{label} hash mismatch: {key}")


def validate_encoder(config: dict) -> Path:
    root = Path(config["encoder"]["path"])
    for relative, expected in config["encoder"]["files"].items():
        if sha256(root / relative) != expected:
            raise ValueError(f"encoder file hash mismatch: {relative}")
    return root


def load_encoder(config: dict):
    import torch
    from transformers import AutoModel, AutoTokenizer

    if config["encoder"]["device"] != "cpu":
        raise ValueError("v5 predeclaration requires CPU inference")
    torch.manual_seed(int(config["encoder"]["seed"]))
    torch.set_num_threads(int(config["encoder"]["cpu_threads"]))
    root = validate_encoder(config)
    tokenizer = AutoTokenizer.from_pretrained(root, local_files_only=True)
    model = AutoModel.from_pretrained(root, local_files_only=True).to("cpu").eval()
    return torch, tokenizer, model


def flatten_articles(records: list[dict]) -> tuple[list[str], list[str], list[int]]:
    texts = []
    hashes = []
    counts = []
    for record in records:
        counts.append(len(record["articles"]))
        for article in record["articles"]:
            texts.append(article["text"])
            hashes.append(article["text_hash"])
    return texts, hashes, counts


def encode_with_checkpoint(texts: list[str], text_hashes: list[str], config: dict,
                           checkpoint: Path, progress_path: Path) -> np.ndarray:
    count = len(texts)
    aggregate_hash = hashlib.sha256("".join(text_hashes).encode("ascii")).hexdigest()
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    if checkpoint.exists() or progress_path.exists():
        if not checkpoint.exists() or not progress_path.exists():
            raise ValueError("incomplete checkpoint pair")
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if progress["text_hash_aggregate"] != aggregate_hash or progress["records"] != count:
            raise ValueError("checkpoint input mismatch")
        embeddings = np.lib.format.open_memmap(checkpoint, mode="r+")
        start_index = int(progress["next_index"])
    else:
        embeddings = np.lib.format.open_memmap(checkpoint, mode="w+", dtype=np.float32, shape=(count, 384))
        start_index = 0

    torch, tokenizer, model = load_encoder(config)
    batch_size = int(config["encoder"]["batch_size"])
    checkpoint_every = int(config["encoder"]["checkpoint_every"])
    with torch.inference_mode():
        for start in range(start_index, count, batch_size):
            end = min(start + batch_size, count)
            encoded = tokenizer(
                texts[start:end], padding=True, truncation=True,
                max_length=int(config["encoder"]["max_length"]), return_tensors="pt",
            )
            hidden = model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            embeddings[start:end] = pooled.cpu().numpy().astype(np.float32)
            if end == count or end % checkpoint_every < batch_size:
                embeddings.flush()
                write_json(progress_path, {
                    "schema_version": "llm-fulltext-embedding-checkpoint-v5",
                    "records": count,
                    "next_index": end,
                    "text_hash_aggregate": aggregate_hash,
                })
                print(f"encoded={end}/{count}", flush=True)
    return np.asarray(embeddings)


def aggregate_buckets(article_embeddings: np.ndarray, counts: list[int]) -> np.ndarray:
    vectors = []
    offset = 0
    for count in counts:
        values = article_embeddings[offset:offset + count].astype(np.float64)
        if len(values) != count or count == 0:
            raise ValueError("article/bucket embedding count mismatch")
        mean = np.mean(values, axis=0)
        maximum = np.max(values, axis=0)
        mean_norm = np.linalg.norm(mean)
        max_norm = np.linalg.norm(maximum)
        if not np.isfinite(mean_norm + max_norm) or mean_norm == 0 or max_norm == 0:
            raise ValueError("invalid bucket embedding")
        vectors.append(np.concatenate((mean / mean_norm, maximum / max_norm)))
        offset += count
    if offset != len(article_embeddings):
        raise ValueError("unused article embeddings")
    return np.asarray(vectors, dtype=np.float64)


def metrics(y: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    std = float(np.std(prediction))
    pearson = float(np.corrcoef(y, prediction)[0, 1]) if std > 0 and np.std(y) > 0 else 0.0
    return {
        "mse": float(np.mean((y - prediction) ** 2)),
        "pearson": pearson,
        "prediction_std": std,
    }


def circular_block_indices(length: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    result = []
    while len(result) < length:
        start = int(rng.integers(0, length))
        result.extend((start + step) % length for step in range(block_length))
    return np.asarray(result[:length], dtype=int)


def paired_bootstrap(folds: list[dict], iterations: int, block_length: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    deltas = []
    correlations = []
    for _ in range(iterations):
        sampled_y = []
        sampled_market = []
        sampled_fusion = []
        for fold in folds:
            indices = circular_block_indices(len(fold["y"]), block_length, rng)
            sampled_y.append(fold["y"][indices])
            sampled_market.append(fold["market"][indices])
            sampled_fusion.append(fold["fusion"][indices])
        y = np.concatenate(sampled_y)
        market = np.concatenate(sampled_market)
        fusion = np.concatenate(sampled_fusion)
        deltas.append(float(np.mean((y - market) ** 2) - np.mean((y - fusion) ** 2)))
        correlations.append(float(np.corrcoef(y, fusion)[0, 1]))
    return {
        "paired_delta_mse_95_ci": [float(x) for x in np.quantile(deltas, [0.025, 0.975])],
        "fusion_pearson_95_ci": [float(x) for x in np.quantile(correlations, [0.025, 0.975])],
    }


def encode(config: dict, output_npz: Path, metadata_output: Path,
           checkpoint: Path, progress: Path) -> dict:
    validate_files(config["code"], "code")
    validate_files(config["sources"], "source")
    panel_path = Path(config["sources"]["panel"]["path"])
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    records = panel["records"]
    if len(records) != config["data_gate"]["required_buckets"]:
        raise ValueError("panel bucket count mismatch")
    texts, text_hashes, counts = flatten_articles(records)
    if len(texts) != config["data_gate"]["required_selected_articles"]:
        raise ValueError("selected article count mismatch")
    article_embeddings = encode_with_checkpoint(texts, text_hashes, config, checkpoint, progress)
    bucket_embeddings = aggregate_buckets(article_embeddings, counts)
    output_npz.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_npz.with_suffix(".tmp.npz")
    np.savez_compressed(
        temporary,
        decision_at=np.asarray([item["decision_at"] for item in records]),
        embeddings=bucket_embeddings.astype(np.float32),
    )
    temporary.replace(output_npz)
    metadata = {
        "schema_version": "llm-fulltext-bucket-embeddings-v5",
        "status": "frozen-development-representation",
        "panel": {"path": str(panel_path.resolve()), "sha256": sha256(panel_path)},
        "encoder": config["encoder"],
        "representation": config["representation"],
        "articles": len(texts),
        "buckets": len(records),
        "embedding_npz": {"path": str(output_npz.resolve()), "sha256": sha256(output_npz)},
        "bucket_records": [{
            "decision_at": item["decision_at"],
            "article_ids": [article["article_id"] for article in item["articles"]],
            "text_hashes": [article["text_hash"] for article in item["articles"]],
        } for item in records],
    }
    write_json(metadata_output, metadata)
    return metadata


def evaluate(config: dict, embedding_npz: Path, metadata_path: Path, output: Path) -> dict:
    validate_files(config["code"], "code")
    validate_files(config["sources"], "source")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if sha256(embedding_npz) != metadata["embedding_npz"]["sha256"]:
        raise ValueError("embedding artifact hash mismatch")
    panel = json.loads(Path(config["sources"]["panel"]["path"]).read_text(encoding="utf-8"))
    arrays = np.load(embedding_npz)
    decisions = arrays["decision_at"].tolist()
    embeddings = arrays["embeddings"].astype(np.float64)
    if decisions != [item["decision_at"] for item in panel["records"]]:
        raise ValueError("embedding/panel order mismatch")
    market = np.asarray([list(item["market_features"].values()) for item in panel["records"]], dtype=float)
    target = np.asarray([item["target_h24_return"] for item in panel["records"]], dtype=float)
    fusion = np.concatenate((market, embeddings), axis=1)
    arms = {"market": market, "text": embeddings, "fusion": fusion}
    all_values = {"target": [], "market": [], "text": [], "fusion": [], "decision_at": []}
    fold_results = []
    bootstrap_folds = []
    for fold in config["folds"]:
        train = [i for i, value in enumerate(decisions) if value <= fold["train_end"]]
        valid = [i for i, value in enumerate(decisions) if fold["valid_start"] <= value <= fold["valid_end"]]
        if len(train) != fold["train_records"] or len(valid) != fold["valid_records"]:
            raise ValueError("fold count mismatch")
        predictions = {}
        for name, values in arms.items():
            model = ridge_fit(values[train], target[train], float(config["model"]["alpha"]))
            predictions[name] = ridge_apply(model, values[valid])
            all_values[name].extend(predictions[name].tolist())
        y_valid = target[valid]
        all_values["target"].extend(y_valid.tolist())
        all_values["decision_at"].extend(decisions[i] for i in valid)
        fold_metrics = {name: metrics(y_valid, predictions[name]) for name in arms}
        fold_metrics["fusion_minus_market_delta_mse"] = fold_metrics["market"]["mse"] - fold_metrics["fusion"]["mse"]
        fold_results.append({"fold": fold["fold"], "train_records": len(train), "validation_records": len(valid), "metrics": fold_metrics})
        bootstrap_folds.append({"y": y_valid, "market": predictions["market"], "fusion": predictions["fusion"]})

    y = np.asarray(all_values["target"])
    overall = {name: metrics(y, np.asarray(all_values[name])) for name in arms}
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
        "schema_version": "llm-fulltext-market-impact-gate-v5",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "status": "predictive-gate-pass-overlay-predeclaration-authorized" if passed else "predictive-gate-fail-stop-before-threshold-or-backtest",
        "passed": passed,
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
        "predictions": [{
            "decision_at": decision,
            "target": actual,
            "market_prediction": market_prediction,
            "text_prediction": text_prediction,
            "fusion_prediction": fusion_prediction,
        } for decision, actual, market_prediction, text_prediction, fusion_prediction in zip(
            all_values["decision_at"], all_values["target"], all_values["market"],
            all_values["text"], all_values["fusion"],
        )],
        "representation": {"metadata_path": str(metadata_path.resolve()), "metadata_sha256": sha256(metadata_path), "npz_sha256": sha256(embedding_npz)},
    }
    write_json(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    encode_parser = subparsers.add_parser("encode")
    encode_parser.add_argument("--embedding-output", type=Path, required=True)
    encode_parser.add_argument("--metadata-output", type=Path, required=True)
    encode_parser.add_argument("--checkpoint", type=Path, required=True)
    encode_parser.add_argument("--progress", type=Path, required=True)
    gate_parser = subparsers.add_parser("evaluate")
    gate_parser.add_argument("--embeddings", type=Path, required=True)
    gate_parser.add_argument("--metadata", type=Path, required=True)
    gate_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.command == "encode":
        result = encode(config, args.embedding_output, args.metadata_output, args.checkpoint, args.progress)
        print(json.dumps({"status": result["status"], "articles": result["articles"], "buckets": result["buckets"]}, indent=2))
    else:
        print(json.dumps(evaluate(config, args.embeddings, args.metadata, args.output), indent=2))


if __name__ == "__main__":
    main()
