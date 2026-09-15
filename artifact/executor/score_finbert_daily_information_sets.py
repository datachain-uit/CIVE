"""Score causal daily headline sets with a pinned ProsusAI FinBERT checkpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from llm_causal_pipeline import write_json

CONTRACT_VERSION = "finbert-headline-mean-probability-v1"
CONTRACT_TEXT = (
    "Treat every nonempty line in a daily information set as one metadata-prefixed headline. "
    "Remove the leading metadata bracket. Classify each title independently with ProsusAI "
    "FinBERT at max length 128. Daily score equals the arithmetic mean of positive probability "
    "minus negative probability. Daily confidence equals the arithmetic mean of the largest "
    "class probability. Errors remain explicit and market outcomes are not used."
)
CONTRACT_HASH = hashlib.sha256(CONTRACT_TEXT.encode()).hexdigest()
HEADLINE_PATTERN = re.compile(r"^-\s*\[[^\]]+\]\s*(.+?)\s*$")


def stratified_sample(records: list[dict], per_year: int) -> list[dict]:
    if per_year <= 0:
        return records
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[record["information_date"][:4]].append(record)
    selected: list[dict] = []
    for year in sorted(groups):
        group = groups[year]
        if len(group) <= per_year:
            selected.extend(group)
            continue
        indices = (
            [round(index * (len(group) - 1) / (per_year - 1)) for index in range(per_year)]
            if per_year > 1
            else [len(group) // 2]
        )
        selected.extend(group[index] for index in indices)
    return selected


def parse_headlines(text: str) -> list[str]:
    headlines: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = HEADLINE_PATTERN.match(line.strip())
        if not match:
            raise ValueError(f"daily information-set line does not match contract: {line[:80]}")
        headlines.append(match.group(1))
    if not headlines:
        raise ValueError("daily information set contains no headlines")
    return headlines


def aggregate_probabilities(rows: Iterable[dict[str, float]]) -> dict:
    rows = list(rows)
    if not rows:
        raise ValueError("cannot aggregate an empty probability set")
    required = {"positive", "negative", "neutral"}
    for row in rows:
        if set(row) != required:
            raise ValueError("FinBERT probability row must contain positive, negative and neutral")
        if any(value < 0 or value > 1 for value in row.values()):
            raise ValueError("FinBERT probability is outside [0,1]")
    means = {label: sum(row[label] for row in rows) / len(rows) for label in sorted(required)}
    score = sum(row["positive"] - row["negative"] for row in rows) / len(rows)
    confidence = sum(max(row.values()) for row in rows) / len(rows)
    return {"score": score, "confidence": confidence, "mean_probabilities": means}


def load_model(model_id: str, revision: str, cache_dir: Path, threads: int):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    tokenizer = AutoTokenizer.from_pretrained(
        model_id, revision=revision, cache_dir=cache_dir, local_files_only=True
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        model_id, revision=revision, cache_dir=cache_dir, local_files_only=True
    )
    model.eval()
    labels = {int(index): str(label).lower() for index, label in model.config.id2label.items()}
    if set(labels.values()) != {"positive", "negative", "neutral"}:
        raise ValueError(f"unexpected FinBERT labels: {labels}")
    return torch, tokenizer, model, labels


def classify_headlines(
    headlines: list[str], torch, tokenizer, model, labels: dict[int, str], batch_size: int,
    max_length: int,
) -> list[dict[str, float]]:
    probabilities: list[dict[str, float]] = []
    with torch.inference_mode():
        for start in range(0, len(headlines), batch_size):
            batch = headlines[start:start + batch_size]
            encoded = tokenizer(
                batch,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=max_length,
            )
            logits = model(**encoded).logits
            for vector in torch.softmax(logits, dim=-1).cpu().tolist():
                probabilities.append({labels[index]: float(value) for index, value in enumerate(vector)})
    return probabilities


def save(
    output: Path, run_id: str, model_id: str, revision: str, records: list[dict],
    batch_size: int, max_length: int, threads: int,
) -> None:
    write_json(output, {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "model": model_id,
        "model_revision": revision,
        "model_digest": revision,
        "contract_version": CONTRACT_VERSION,
        "contract_hash": CONTRACT_HASH,
        "prompt_version": CONTRACT_VERSION,
        "prompt_hash": CONTRACT_HASH,
        "runtime": {
            "device": "cpu",
            "workers": 1,
            "torch_threads": threads,
            "batch_size": batch_size,
            "max_length": max_length,
        },
        "records": records,
        "summary": {
            "attempted": len(records),
            "success": sum(record["status"] == "success" for record in records),
            "errors": sum(record["status"] == "error" for record in records),
            "headline_count_matches": sum(
                record.get("headline_count_matches", False) for record in records
            ),
        },
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="ProsusAI/finbert")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sample-per-year", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if min(args.batch_size, args.max_length, args.threads) <= 0:
        raise ValueError("batch size, max length and threads must be positive")

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    selected = stratified_sample(payload["records"], args.sample_per_year)
    records: list[dict] = []
    if args.output.exists():
        checkpoint = json.loads(args.output.read_text(encoding="utf-8"))
        if (
            checkpoint.get("model_digest") != args.revision
            or checkpoint.get("contract_hash") != CONTRACT_HASH
        ):
            raise ValueError("checkpoint model revision or contract does not match")
        records = checkpoint.get("records", [])
    completed = {record["content_hash"] for record in records}
    if len(completed) != len(records):
        raise ValueError("checkpoint contains duplicate content hashes")

    torch, tokenizer, model, labels = load_model(
        args.model, args.revision, args.cache_dir, args.threads
    )
    for source in selected:
        if source["content_hash"] in completed:
            continue
        base = {
            "content_hash": source["content_hash"],
            "information_date": source["information_date"],
            "available_at": source["available_at"],
            "source_snapshot_hash": source["source_snapshot_hash"],
            "selected_article_count": source["selected_article_count"],
        }
        try:
            headlines = parse_headlines(source["text"])
            count_matches = len(headlines) == int(source["selected_article_count"])
            if not count_matches:
                raise ValueError(
                    f"parsed {len(headlines)} headlines but expected {source['selected_article_count']}"
                )
            probabilities = classify_headlines(
                headlines, torch, tokenizer, model, labels, args.batch_size, args.max_length
            )
            aggregate = aggregate_probabilities(probabilities)
            result = {
                **base,
                "status": "success",
                "parsed_headlines": len(headlines),
                "headline_count_matches": True,
                **aggregate,
                "error": None,
            }
        except Exception as exc:
            result = {
                **base,
                "status": "error",
                "parsed_headlines": None,
                "headline_count_matches": False,
                "score": None,
                "confidence": None,
                "mean_probabilities": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
        records.append(result)
        save(
            args.output, args.run_id, args.model, args.revision, records,
            args.batch_size, args.max_length, args.threads,
        )
        print(
            f"{len(records)}/{len(selected)} {source['information_date']} {result['status']}",
            flush=True,
        )


if __name__ == "__main__":
    main()
