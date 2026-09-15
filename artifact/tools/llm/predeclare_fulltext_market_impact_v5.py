"""Freeze the v5 full-text market-impact experiment before encoding."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def item(path: str) -> dict:
    value = Path(path)
    return {"path": path, "sha256": sha256(value)}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build(v4_config_path: Path) -> dict:
    v4 = json.loads(v4_config_path.read_text(encoding="utf-8"))
    encoder = dict(v4["encoder"])
    encoder.update({
        "device": "cpu",
        "max_length": 256,
        "batch_size": 32,
        "seed": 20260905,
        "cpu_threads": 4,
        "checkpoint_every": 512,
    })
    return {
        "schema_version": "llm-fulltext-market-impact-predeclaration-v5",
        "experiment_id": "llm-fulltext-market-impact-v5-development",
        "predeclared_at": datetime.now(timezone.utc).isoformat(),
        "scope": "New development branch using full-text multi-source news and causal Bybit BTCUSDT 24h labels; not sealed confirmation.",
        "prior_project_outcomes_consulted": True,
        "protocol": item("paper/working/protocols/LLM_Fulltext_Market_Impact_Protocol_v5.md"),
        "code": {
            "audit": item("tools/llm/audit_fulltext_corpus_v5.py"),
            "panel_builder": item("tools/llm/build_fulltext_market_impact_panel_v5.py"),
            "runner": item("tools/llm/run_fulltext_market_impact_v5.py"),
            "minilm_dependency": item("tools/llm/run_minilm_external_impact_v4.py"),
            "audit_tests": item("tools/llm/test_audit_fulltext_corpus_v5.py"),
            "panel_tests": item("tools/llm/test_build_fulltext_market_impact_panel_v5.py"),
            "runner_tests": item("tools/llm/test_run_fulltext_market_impact_v5.py"),
        },
        "tests": {"status": "9 tests passed before encoding", "python": str(Path(sys.executable).resolve())},
        "external_provenance": {
            "dataset": "maryamfakhari/crypto-news-coindesk-2020-2025",
            "revision": "d7bbdb7360291a81328d121080102f86258139b9",
            "repository": "https://huggingface.co/datasets/maryamfakhari/crypto-news-coindesk-2020-2025",
            "license_from_dataset_card": "cc-by-nc-4.0",
            "dataset_card": item("paper/input/references/source_artifacts/crypto_news_fulltext_v5/README.md"),
            "audit_summary": {
                "raw_rows": 229172,
                "unique_article_identities": 228995,
                "sources": 79,
                "coverage_start": "2019-10-29T00:05:57+00:00",
                "coverage_end": "2025-02-01T23:46:54+00:00",
            },
        },
        "sources": {
            "corpus": item("runtime/external/crypto_news_fulltext_v5/coindesk-crypto-news-2020-2025.csv"),
            "corpus_audit": item("runtime/external/crypto_news_fulltext_v5/corpus_audit_v5.json"),
            "panel": item("runtime/external/crypto_news_fulltext_v5/fulltext_market_impact_panel_v5.json"),
            "panel_audit": item("runtime/external/crypto_news_fulltext_v5/fulltext_market_impact_panel_audit_v5.json"),
            "btc_4h": item(str(ROOT / "results/bybit_lifecycle_4h/BTCUSDT_1660348800000_1786492800000.json")),
        },
        "data_policy": {
            "minimum_body_words": 50,
            "max_articles_per_bucket": 8,
            "selection": "BTC relevance descending; source-diverse first; publication time and article_id tie-break",
            "required_selected_articles": 36828,
            "required_buckets": 5187,
            "required_sources": 58,
        },
        "encoder": encoder,
        "representation": {
            "input": "normalized title + '. ' + normalized body",
            "article_pooling": "attention-mask mean then L2 normalize",
            "bucket_pooling": "concatenate L2-normalized mean and elementwise max",
            "dimensions": 768,
            "encoder_fine_tuning": False,
        },
        "target": {
            "asset": "Bybit BTCUSDT",
            "field": "target_h24_return",
            "definition": "open[t+24h] / open[t] - 1",
            "role": "single primary development target",
        },
        "model": {"family": "linear-ridge", "alpha": 100.0, "standardization": "training-only mean/std", "hyperparameter_tuning": False},
        "folds": [
            {"fold": 1, "train_end": "2023-12-31T20:00:00+00:00", "valid_start": "2024-01-02T00:00:00+00:00", "valid_end": "2024-04-30T20:00:00+00:00", "train_records": 2799, "valid_records": 720},
            {"fold": 2, "train_end": "2024-04-30T20:00:00+00:00", "valid_start": "2024-05-02T00:00:00+00:00", "valid_end": "2024-08-31T20:00:00+00:00", "train_records": 3525, "valid_records": 732},
            {"fold": 3, "train_end": "2024-08-31T20:00:00+00:00", "valid_start": "2024-09-02T00:00:00+00:00", "valid_end": "2024-12-31T20:00:00+00:00", "train_records": 4263, "valid_records": 725},
        ],
        "bootstrap": {"iterations": 5000, "seed": 20260905, "block_length_records": 42, "confidence_level": 0.95},
        "data_gate": {"required_buckets": 5187, "required_selected_articles": 36828},
        "gate": {
            "required_oos_records": 2177,
            "minimum_fold_wins": 2,
            "all_required_checks": [
                "paired MSE(market)-MSE(fusion) 95% CI lower bound > 0",
                "fusion prediction Pearson 95% CI lower bound > 0",
                "fusion MSE wins at least 2 of 3 folds",
                "2177 OOS records and nonconstant predictions",
            ],
        },
        "on_fail": "Freeze negative result and stop before threshold, action mapping, backtest, Tech+LLM, or sealed holdout.",
        "on_pass": "Authorize only a separate development overlay predeclaration.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v4-config", type=Path, required=True)
    parser.add_argument("--runtime-output", type=Path, required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--reference-manifest", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args.v4_config)
    write_json(args.runtime_output, payload)
    args.evidence_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.runtime_output, args.evidence_output)
    manifest = {
        "schema_version": "source-artifact-manifest-v5",
        "dataset_repository": payload["external_provenance"]["repository"],
        "revision": payload["external_provenance"]["revision"],
        "license_from_dataset_card": payload["external_provenance"]["license_from_dataset_card"],
        "dataset_card": payload["external_provenance"]["dataset_card"],
        "corpus_sha256": payload["sources"]["corpus"]["sha256"],
        "note": "Dataset card and audit are retained as evidence; the 240 MB corpus remains under runtime/external and is not redistributed in paper/input.",
    }
    write_json(args.reference_manifest, manifest)
    print(json.dumps({"config_sha256": sha256(args.runtime_output), "manifest_sha256": sha256(args.reference_manifest)}, indent=2))


if __name__ == "__main__":
    main()
