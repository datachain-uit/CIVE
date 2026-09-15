"""Build and gate a frozen MiniLM market-impact representation."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def normalize_url(value: str) -> str:
    return value.strip().rstrip("/")


def load_external_articles(path: Path, max_chunks: int) -> list[dict]:
    grouped: dict[str, dict] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            url = normalize_url(row["url"])
            article = grouped.setdefault(url, {
                "article_id": hashlib.sha256(url.encode("utf-8")).hexdigest(),
                "url": url,
                "dates": set(),
                "labels": set(),
                "chunks": [],
                "seen_chunks": set(),
            })
            article["dates"].add(row["datetime"].strip())
            article["labels"].add(int(row["label"]))
            text = " ".join(row["text"].split())
            if text and text not in article["seen_chunks"]:
                article["seen_chunks"].add(text)
                article["chunks"].append(text)

    result = []
    for article in grouped.values():
        if len(article["dates"]) != 1 or len(article["labels"]) != 1:
            raise ValueError("each external URL must have exactly one date and label")
        chunks = article["chunks"][:max_chunks]
        if not chunks:
            raise ValueError("external article has no usable text")
        result.append({
            "article_id": article["article_id"],
            "url": article["url"],
            "information_date": next(iter(article["dates"])),
            "label": next(iter(article["labels"])),
            "available_unique_chunks": len(article["chunks"]),
            "chunks": chunks,
        })
    return sorted(result, key=lambda item: (item["information_date"], item["article_id"]))


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
        raise ValueError("v4 predeclaration requires CPU inference")
    torch.manual_seed(int(config["encoder"]["seed"]))
    torch.set_num_threads(int(config["encoder"]["cpu_threads"]))
    root = validate_encoder(config)
    tokenizer = AutoTokenizer.from_pretrained(root, local_files_only=True)
    model = AutoModel.from_pretrained(root, local_files_only=True).to("cpu").eval()
    return torch, tokenizer, model


def encode_texts(texts: list[str], config: dict) -> np.ndarray:
    torch, tokenizer, model = load_encoder(config)
    batches = []
    batch_size = int(config["encoder"]["batch_size"])
    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            encoded = tokenizer(
                texts[start:start + batch_size],
                padding=True,
                truncation=True,
                max_length=int(config["encoder"]["max_length"]),
                return_tensors="pt",
            )
            hidden = model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            batches.append(pooled.cpu().numpy().astype(np.float64))
    return np.concatenate(batches)


def aggregate_article_embeddings(
    articles: list[dict], chunk_embeddings: np.ndarray,
) -> np.ndarray:
    vectors = []
    offset = 0
    for article in articles:
        count = len(article["chunks"])
        vector = np.mean(chunk_embeddings[offset:offset + count], axis=0)
        norm = np.linalg.norm(vector)
        if not np.isfinite(norm) or norm == 0:
            raise ValueError("invalid article embedding")
        vectors.append(vector / norm)
        offset += count
    if offset != len(chunk_embeddings):
        raise ValueError("chunk/article embedding count mismatch")
    return np.asarray(vectors)


def ridge_fit(x: np.ndarray, y: np.ndarray, alpha: float) -> dict[str, np.ndarray | float]:
    mean = np.mean(x, axis=0)
    scale = np.std(x, axis=0)
    scale[scale == 0] = 1.0
    standardized = (x - mean) / scale
    target_mean = float(np.mean(y))
    coefficients = np.linalg.solve(
        standardized.T @ standardized + alpha * np.eye(x.shape[1]),
        standardized.T @ (y - target_mean),
    )
    return {"mean": mean, "scale": scale, "target_mean": target_mean, "coefficients": coefficients}


def ridge_apply(model: dict, x: np.ndarray) -> np.ndarray:
    return model["target_mean"] + ((x - model["mean"]) / model["scale"]) @ model["coefficients"]


def auc(y: np.ndarray, score: np.ndarray) -> float:
    positive = score[y == 1]
    negative = score[y == 0]
    if len(positive) == 0 or len(negative) == 0:
        return float("nan")
    comparisons = positive[:, None] - negative[None, :]
    return float(np.mean(comparisons > 0) + 0.5 * np.mean(comparisons == 0))


def binary_metrics(y: np.ndarray, score: np.ndarray) -> dict[str, float]:
    return {
        "auc": auc(y, score),
        "mean_score_label_1": float(np.mean(score[y == 1])),
        "mean_score_label_0": float(np.mean(score[y == 0])),
        "score_separation": float(np.mean(score[y == 1]) - np.mean(score[y == 0])),
        "mse": float(np.mean((y - score) ** 2)),
        "prediction_std": float(np.std(score)),
    }


def date_cluster_bootstrap(
    folds: list[list[dict]], iterations: int, seed: int,
) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    auc_values = []
    separation_values = []
    attempts = 0
    while len(auc_values) < iterations and attempts < iterations * 20:
        attempts += 1
        sampled_rows = []
        for fold in folds:
            by_date: dict[str, list[dict]] = defaultdict(list)
            for row in fold:
                by_date[row["information_date"]].append(row)
            dates = sorted(by_date)
            for sampled_date in rng.choice(dates, size=len(dates), replace=True):
                sampled_rows.extend(by_date[str(sampled_date)])
        y = np.asarray([item["label"] for item in sampled_rows])
        score = np.asarray([item["prediction"] for item in sampled_rows])
        value = auc(y, score)
        if not math.isnan(value):
            auc_values.append(value)
            separation_values.append(float(np.mean(score[y == 1]) - np.mean(score[y == 0])))
    if len(auc_values) != iterations:
        raise ValueError("insufficient valid external bootstrap samples")
    return {
        "auc_95_ci": [float(x) for x in np.quantile(auc_values, [0.025, 0.975])],
        "score_separation_95_ci": [float(x) for x in np.quantile(separation_values, [0.025, 0.975])],
    }


def external_gate(config: dict, embedding_output: Path, gate_output: Path) -> dict:
    runner = Path(config["code"]["representation"]["path"])
    if sha256(runner) != config["code"]["representation"]["sha256"]:
        raise ValueError("representation runner hash differs from predeclaration")
    for key in ("labeler_base", "labeler_color"):
        item = config["external_provenance"][key]
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"external provenance hash mismatch: {key}")
    source = Path(config["sources"]["external_dataset"]["path"])
    if sha256(source) != config["sources"]["external_dataset"]["sha256"]:
        raise ValueError("external dataset hash differs from predeclaration")
    articles = load_external_articles(source, int(config["representation"]["max_chunks_per_article"]))
    if len(articles) != config["external_gate"]["required_articles"]:
        raise ValueError("external article count mismatch")
    chunks = [text for article in articles for text in article["chunks"]]
    embeddings = aggregate_article_embeddings(articles, encode_texts(chunks, config))
    representation = {
        "schema_version": 1,
        "experiment_id": config["experiment_id"],
        "status": "frozen-external-article-embeddings",
        "source": {"path": str(source.resolve()), "sha256": sha256(source)},
        "encoder": config["encoder"],
        "representation": config["representation"],
        "records": [{
            "article_id": article["article_id"],
            "information_date": article["information_date"],
            "label": article["label"],
            "available_unique_chunks": article["available_unique_chunks"],
            "selected_chunks": len(article["chunks"]),
            "selected_chunk_hashes": [
                hashlib.sha256(text.encode("utf-8")).hexdigest() for text in article["chunks"]
            ],
            "embedding": vector.tolist(),
        } for article, vector in zip(articles, embeddings)],
    }
    write_json(embedding_output, representation)

    rows = []
    fold_results = []
    bootstrap_folds = []
    for fold in config["external_folds"]:
        train = [i for i, item in enumerate(articles) if item["information_date"] <= fold["train_end"]]
        valid = [i for i, item in enumerate(articles) if fold["valid_start"] <= item["information_date"] <= fold["valid_end"]]
        if len(train) != fold["train_records"] or len(valid) != fold["valid_records"]:
            raise ValueError("external fold count mismatch")
        y_train = np.asarray([articles[i]["label"] for i in train], dtype=float)
        y_valid = np.asarray([articles[i]["label"] for i in valid], dtype=float)
        model = ridge_fit(embeddings[train], y_train, float(config["model"]["alpha"]))
        prediction = ridge_apply(model, embeddings[valid])
        fold_rows = [{
            "information_date": articles[i]["information_date"],
            "article_id": articles[i]["article_id"],
            "label": int(articles[i]["label"]),
            "prediction": float(value),
        } for i, value in zip(valid, prediction)]
        rows.extend(fold_rows)
        bootstrap_folds.append(fold_rows)
        fold_results.append({
            "fold": fold["fold"],
            "train_records": len(train),
            "validation_records": len(valid),
            "metrics": binary_metrics(y_valid, prediction),
        })
    y = np.asarray([item["label"] for item in rows])
    score = np.asarray([item["prediction"] for item in rows])
    overall = binary_metrics(y, score)
    uncertainty = date_cluster_bootstrap(
        bootstrap_folds, int(config["bootstrap"]["iterations"]), int(config["bootstrap"]["seed"])
    )
    checks = {
        "oos_articles": len(rows) == config["external_gate"]["required_oos_articles"],
        "auc_ci_lower_gt_half": uncertainty["auc_95_ci"][0] > 0.5,
        "score_separation_ci_lower_gt_zero": uncertainty["score_separation_95_ci"][0] > 0,
        "both_fold_auc_gt_half": all(item["metrics"]["auc"] > 0.5 for item in fold_results),
        "predictions_nonconstant": overall["prediction_std"] > 0,
    }
    passed = all(checks.values())
    result = {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "status": "external-gate-pass-corpus-scoring-authorized" if passed else "external-gate-fail-stop-before-corpus-scoring",
        "passed": passed,
        "project_target_outcomes_consulted": False,
        "external_articles": len(articles),
        "selected_chunks": len(chunks),
        "oos_articles": len(rows),
        "overall": overall,
        "uncertainty": uncertainty,
        "folds": fold_results,
        "checks": checks,
        "predictions": rows,
        "embedding_artifact": {
            "path": str(embedding_output.resolve()),
            "sha256": sha256(embedding_output),
        },
    }
    write_json(gate_output, result)
    return result


def score_corpus(config: dict, embeddings_path: Path, gate_path: Path, output: Path) -> dict:
    runner = Path(config["code"]["representation"]["path"])
    if sha256(runner) != config["code"]["representation"]["sha256"]:
        raise ValueError("representation runner hash differs from predeclaration")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if not gate.get("passed") or gate.get("status") != "external-gate-pass-corpus-scoring-authorized":
        raise ValueError("external gate did not authorize corpus scoring")
    if sha256(embeddings_path) != gate["embedding_artifact"]["sha256"]:
        raise ValueError("external embedding artifact hash mismatch")
    representation = json.loads(embeddings_path.read_text(encoding="utf-8"))
    records = representation["records"]
    x = np.asarray([item["embedding"] for item in records], dtype=float)
    y = np.asarray([item["label"] for item in records], dtype=float)
    head = ridge_fit(x, y, float(config["model"]["alpha"]))

    source = Path(config["sources"]["project_corpus"]["path"])
    if sha256(source) != config["sources"]["project_corpus"]["sha256"]:
        raise ValueError("project corpus hash differs from predeclaration")
    inputs = json.loads(source.read_text(encoding="utf-8"))["records"]
    unique_texts = list(dict.fromkeys(" ".join(item["headline"].split()) for item in inputs))
    vectors = encode_texts(unique_texts, config)
    scores = ridge_apply(head, vectors)
    score_by_text = dict(zip(unique_texts, scores))
    payload = {
        "schema_version": 1,
        "experiment_id": config["experiment_id"],
        "status": "frozen-project-headline-external-impact-scores",
        "external_gate": {"path": str(gate_path.resolve()), "sha256": sha256(gate_path)},
        "external_embeddings": {"path": str(embeddings_path.resolve()), "sha256": sha256(embeddings_path)},
        "project_corpus": {"path": str(source.resolve()), "sha256": sha256(source)},
        "head": {
            "alpha": config["model"]["alpha"],
            "mean": head["mean"].tolist(),
            "scale": head["scale"].tolist(),
            "target_mean": head["target_mean"],
            "coefficients": head["coefficients"].tolist(),
        },
        "records": [{
            "headline_id": item["headline_id"],
            "information_date": item["information_date"],
            "impact_score": float(score_by_text[" ".join(item["headline"].split())]),
        } for item in inputs],
    }
    write_json(output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    gate_parser = subparsers.add_parser("external-gate")
    gate_parser.add_argument("--embedding-output", type=Path, required=True)
    gate_parser.add_argument("--gate-output", type=Path, required=True)
    score_parser = subparsers.add_parser("score-corpus")
    score_parser.add_argument("--embeddings", type=Path, required=True)
    score_parser.add_argument("--gate", type=Path, required=True)
    score_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.command == "external-gate":
        result = external_gate(config, args.embedding_output, args.gate_output)
        print(json.dumps(result, indent=2))
    else:
        payload = score_corpus(config, args.embeddings, args.gate, args.output)
        print(json.dumps({"status": payload["status"], "records": len(payload["records"])}, indent=2))


if __name__ == "__main__":
    main()
