"""Score completed daily information sets with a pinned local Ollama model."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from llm_causal_pipeline import parse_model_response, write_json
from score_llm_causal_corpus import api, model_digest

PROMPT_VERSION = "crypto-daily-information-set-v1"
SYSTEM_PROMPT = (
    "You assess the next-24-hour directional impact on the broad crypto market using only a "
    "completed UTC day's supplied headlines. Treat repeated themes as one theme and do not infer "
    "facts absent from the headlines. Return exactly one JSON object with score in [-1,1], "
    "confidence in [0,1], and a short reason_code. Positive is bullish, negative is bearish, and "
    "zero is balanced, irrelevant, or too uncertain."
)


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
        indices = [round(index * (len(group) - 1) / (per_year - 1)) for index in range(per_year)] if per_year > 1 else [len(group) // 2]
        selected.extend(group[index] for index in indices)
    return selected


def score(record: dict, model: str, digest: str, disable_thinking: bool = False) -> dict:
    base = {
        "content_hash": record["content_hash"],
        "information_date": record["information_date"],
        "available_at": record["available_at"],
        "source_snapshot_hash": record["source_snapshot_hash"],
        "article_count": record["article_count"],
        "selected_article_count": record["selected_article_count"],
        "model": model,
        "model_digest": digest,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "thinking": not disable_thinking,
    }
    try:
        request = {
            "model": model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "seed": 20260814},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": record["text"]},
            ],
        }
        if disable_thinking:
            request["think"] = False
        response = api("/api/chat", request)
        return {**base, "status": "success", **parse_model_response(response["message"]["content"]), "error": None}
    except Exception as exc:
        return {**base, "status": "error", "score": None, "confidence": None,
                "reason_code": None, "error": f"{type(exc).__name__}: {exc}"}


def save(output: Path, run_id: str, model: str, digest: str, records: list[dict],
         disable_thinking: bool = False, workers: int = 1,
         seed_checkpoint: dict | None = None,
         request_delay_seconds: float = 0.0) -> None:
    write_json(output, {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "model": model,
        "model_digest": digest,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "thinking": not disable_thinking,
        "workers": workers,
        "request_delay_seconds": request_delay_seconds,
        "seed_checkpoint": seed_checkpoint,
        "records": records,
        "summary": {
            "attempted": len(records),
            "success": sum(item["status"] == "success" for item in records),
            "errors": sum(item["status"] == "error" for item in records),
        },
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sample-per-year", type=int, default=0)
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--seed-checkpoint", type=Path)
    parser.add_argument("--request-delay-seconds", type=float, default=0.0)
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    if args.request_delay_seconds < 0:
        raise ValueError("request delay must be non-negative")
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    selected = stratified_sample(payload["records"], args.sample_per_year)
    digest = model_digest(args.model)
    scored: list[dict] = []
    seed_provenance = None
    if args.output.exists():
        checkpoint = json.loads(args.output.read_text(encoding="utf-8"))
        if (checkpoint.get("model_digest") != digest or checkpoint.get("prompt_version") != PROMPT_VERSION
                or checkpoint.get("thinking", True) != (not args.disable_thinking)):
            raise ValueError("checkpoint model or prompt does not match current run")
        scored = checkpoint.get("records", [])
        seed_provenance = checkpoint.get("seed_checkpoint")
    elif args.seed_checkpoint:
        checkpoint = json.loads(args.seed_checkpoint.read_text(encoding="utf-8"))
        if (checkpoint.get("model_digest") != digest or checkpoint.get("prompt_version") != PROMPT_VERSION
                or checkpoint.get("thinking", True) != (not args.disable_thinking)):
            raise ValueError("seed checkpoint model or prompt does not match current run")
        scored = checkpoint.get("records", [])
        seed_provenance = {
            "path": str(args.seed_checkpoint),
            "sha256": hashlib.sha256(args.seed_checkpoint.read_bytes()).hexdigest(),
            "records": len(scored),
        }
    completed = {item["content_hash"] for item in scored}
    pending = [record for record in selected if record["content_hash"] not in completed]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for batch_start in range(0, len(pending), args.workers):
            batch = pending[batch_start:batch_start + args.workers]
            results = list(pool.map(
                lambda record: score(record, args.model, digest, args.disable_thinking), batch
            ))
            scored.extend(results)
            save(args.output, args.run_id, args.model, digest, scored, args.disable_thinking,
                 args.workers, seed_provenance, args.request_delay_seconds)
            for offset, (record, result) in enumerate(zip(batch, results), start=1):
                progress = len(completed) + batch_start + offset
                print(f"{progress}/{len(selected)} {record['information_date']} {result['status']}", flush=True)
            if args.request_delay_seconds > 0 and batch_start + args.workers < len(pending):
                time.sleep(args.request_delay_seconds)


if __name__ == "__main__":
    main()
