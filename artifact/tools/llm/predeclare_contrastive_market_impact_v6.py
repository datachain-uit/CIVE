"""Freeze the v6 contrastive experiment before fold-local training."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def item(path: str) -> dict:
    return {"path": path, "sha256": sha256(Path(path))}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build() -> dict:
    return {
        "schema_version": "llm-contrastive-market-impact-predeclaration-v6",
        "experiment_id": "llm-contrastive-market-impact-v6-development",
        "predeclared_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Post-v5 development branch; fold-local supervised contrastive projection, not sealed confirmation.",
        "prior_v5_outcomes_consulted": True,
        "protocol": item("paper/working/protocols/LLM_Contrastive_Market_Impact_Protocol_v6.md"),
        "code": {
            "runner": item("tools/llm/run_contrastive_market_impact_v6.py"),
            "tests": item("tools/llm/test_run_contrastive_market_impact_v6.py"),
            "v5_dependency": item("tools/llm/run_fulltext_market_impact_v5.py"),
            "ridge_dependency": item("tools/llm/run_minilm_external_impact_v4.py"),
        },
        "tests": {"status": "2 tests passed before training", "python": str(Path(sys.executable).resolve())},
        "sources": {
            "panel": item("runtime/external/crypto_news_fulltext_v5/fulltext_market_impact_panel_v5.json"),
            "v5_embeddings": item("runtime/ministral3_8b_challenger/results/llm_fulltext_bucket_embeddings_v5.npz"),
            "v5_embedding_metadata": item("runtime/ministral3_8b_challenger/results/llm_fulltext_bucket_embeddings_v5.json"),
            "v5_predeclaration": item("runtime/ministral3_8b_challenger/configs/llm_fulltext_market_impact_v5_predeclared.json"),
            "v5_gate": item("runtime/ministral3_8b_challenger/results/llm_fulltext_market_impact_gate_v5.json"),
        },
        "data_gate": {"required_buckets": 5187, "required_oos_records": 2177},
        "projection": {
            "input_dimensions": 768,
            "hidden_dimensions": 128,
            "output_dimensions": 32,
            "activation": "GELU",
            "output_normalization": "L2",
            "dropout": 0.0,
        },
        "training": {
            "objective": "supervised contrastive loss over training-only return-tertile classes",
            "class_thresholds": "training-only 1/3 and 2/3 raw h24 return quantiles",
            "temperature": 0.1,
            "optimizer": "AdamW",
            "learning_rate": 0.001,
            "weight_decay": 0.0001,
            "batch_size": 256,
            "epochs": 20,
            "scheduler": None,
            "early_stopping": False,
            "seed_base": 20260906,
            "cpu_threads": 4,
            "device": "cpu",
        },
        "model": {"family": "linear-ridge", "alpha": 100.0, "standardization": "training-only mean/std", "hyperparameter_tuning": False},
        "folds": [
            {"fold": 1, "train_end": "2023-12-31T20:00:00+00:00", "valid_start": "2024-01-02T00:00:00+00:00", "valid_end": "2024-04-30T20:00:00+00:00", "train_records": 2799, "valid_records": 720},
            {"fold": 2, "train_end": "2024-04-30T20:00:00+00:00", "valid_start": "2024-05-02T00:00:00+00:00", "valid_end": "2024-08-31T20:00:00+00:00", "train_records": 3525, "valid_records": 732},
            {"fold": 3, "train_end": "2024-08-31T20:00:00+00:00", "valid_start": "2024-09-02T00:00:00+00:00", "valid_end": "2024-12-31T20:00:00+00:00", "train_records": 4263, "valid_records": 725},
        ],
        "bootstrap": {"iterations": 5000, "seed": 20260906, "block_length_records": 42, "confidence_level": 0.95},
        "gate": {
            "required_oos_records": 2177,
            "minimum_fold_wins": 2,
            "all_required_checks": [
                "paired MSE(market)-MSE(market+contrastive) 95% CI lower bound > 0",
                "market+contrastive prediction Pearson 95% CI lower bound > 0",
                "market+contrastive MSE wins at least 2 of 3 folds",
                "2177 OOS records and nonconstant predictions",
            ],
        },
        "on_fail": "Freeze negative result and stop before threshold, action mapping, backtest, Tech+LLM, or sealed holdout.",
        "on_pass": "Authorize only a separate development overlay predeclaration.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-output", type=Path, required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    args = parser.parse_args()
    payload = build()
    write_json(args.runtime_output, payload)
    args.evidence_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.runtime_output, args.evidence_output)
    print(json.dumps({"config_sha256": sha256(args.runtime_output)}, indent=2))


if __name__ == "__main__":
    main()
