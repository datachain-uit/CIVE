"""Resume CryptoBERT full daily scoring for the thesis LLM evidence gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


MODEL_ID = "ElKulako/cryptobert"
CONTRACT_VERSION = "cryptobert-social-sentiment-transfer-v1"
CONTRACT_HASH = "c5aadbb2587e6c69fbe0b32f9c3fa774546be306ebf9b4814c5c48320d53ac48"
PAPER_DOI = "10.1109/MIS.2023.3283170"
HEADLINE_PATTERN = re.compile(r"^-\s*\[[^\]]+\]\s*(.+?)\s*$")
LABELS = {0: "bearish", 1: "neutral", 2: "bullish"}


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{time.time_ns()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(8):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.25)


def parse_headlines(text: str) -> list[str]:
    headlines: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = HEADLINE_PATTERN.match(line.strip())
        if not match:
            raise ValueError(f"daily information-set line violates contract: {line[:80]}")
        headlines.append(match.group(1))
    if not headlines:
        raise ValueError("daily information set contains no headlines")
    return headlines


def load_model(args: argparse.Namespace):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        args.model,
        revision=args.revision,
        cache_dir=str(args.cache_dir),
        local_files_only=args.local_files_only,
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model,
        revision=args.revision,
        cache_dir=str(args.cache_dir),
        local_files_only=args.local_files_only,
    )
    model.to("cpu")
    model.eval()
    return torch, tokenizer, model


def classify_headlines(headlines: list[str], torch, tokenizer, model, max_length: int) -> dict:
    labels: list[str] = []
    confidences: list[float] = []
    for headline in headlines:
        inputs = tokenizer(headline, return_tensors="pt", truncation=True, max_length=max_length)
        with torch.inference_mode():
            output = model(**inputs)
            probs = torch.softmax(output.logits[0], dim=-1)
        label_index = int(torch.argmax(probs).item())
        labels.append(LABELS[label_index])
        confidences.append(float(probs[label_index].item()))
    return {
        "parsed_headlines": len(headlines),
        "score": (labels.count("bullish") - labels.count("bearish")) / len(labels),
        "confidence": sum(confidences) / len(confidences),
        "label_counts": {label: labels.count(label) for label in ("bearish", "neutral", "bullish")},
    }


def base_result(args: argparse.Namespace, sources: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": args.experiment_id,
        "stage": "full-inference",
        "paper": {
            "id": "S13",
            "title": "Sentiment Classification of Cryptocurrency-Related Social Media Posts",
            "doi": PAPER_DOI,
            "role": "crypto social-sentiment transfer test; not a news-headline or trading replication",
        },
        "model": {"model_id": args.model, "revision": args.revision},
        "input": {"artifact": str(args.input), "sha256": sha256_file(args.input)},
        "contract_version": CONTRACT_VERSION,
        "contract_hash": CONTRACT_HASH,
        "market_outcomes_consulted": False,
        "trading_backtest_consulted": False,
        "runtime": {
            "max_length": args.max_length,
            "cache_dir": str(args.cache_dir),
            "local_files_only": args.local_files_only,
        },
        "stage_config": {
            "information_sets": len(sources),
            "runs": 1,
            "stores_headline_level_rows": False,
        },
        "runs": [],
        "passed": False,
        "status": "full-inference-running",
        "error": None,
        "records": [],
    }


def score_source(source: dict, torch, tokenizer, model, max_length: int) -> dict:
    base = {
        "content_hash": source["content_hash"],
        "information_date": source["information_date"],
        "available_at": source["available_at"],
        "source_snapshot_hash": source["source_snapshot_hash"],
        "selected_article_count": source["selected_article_count"],
    }
    try:
        headlines = parse_headlines(source["text"])
        if len(headlines) != int(source["selected_article_count"]):
            raise ValueError(f"parsed {len(headlines)} headlines but expected {source['selected_article_count']}")
        scored = classify_headlines(headlines, torch, tokenizer, model, max_length)
        return {**base, "status": "success", "headline_count_matches": True, **scored, "error": None}
    except Exception as exc:
        return {
            **base,
            "status": "error",
            "headline_count_matches": False,
            "parsed_headlines": None,
            "score": None,
            "confidence": None,
            "label_counts": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def finalize_full(result: dict, required_sets: int) -> None:
    records = result.get("records", [])
    successes = sum(record.get("status") == "success" for record in records)
    errors = sum(record.get("status") == "error" for record in records)
    headline_matches = sum(record.get("headline_count_matches") is True for record in records)
    parsed_headlines = sum(int(record.get("parsed_headlines") or 0) for record in records)
    result["summary"] = {
        "information_sets": required_sets,
        "attempted": len(records),
        "success": successes,
        "errors": errors,
        "headline_count_matches": headline_matches,
        "parsed_headlines": parsed_headlines,
    }
    result["checks"] = {
        "schema_success": {"observed": successes, "required": required_sets, "passed": successes == required_sets},
        "errors": {"observed": errors, "required": 0, "passed": errors == 0},
        "headline_count_matches": {
            "observed": headline_matches,
            "required": required_sets,
            "passed": headline_matches == required_sets,
        },
    }
    result["passed"] = successes == required_sets and errors == 0 and headline_matches == required_sets
    result["status"] = (
        "full-inference-complete-predictive-gate-authorized"
        if result["passed"]
        else "full-inference-fail-stop-before-predictive-gate"
    )


def load_or_create_result(args: argparse.Namespace, sources: list[dict]) -> dict:
    expected = base_result(args, sources)
    if not args.resume or not args.output.exists():
        write_atomic(args.output, expected)
        return expected
    result = json.loads(args.output.read_text(encoding="utf-8"))
    checks = {
        "stage": result.get("stage") == expected["stage"],
        "experiment_id": result.get("experiment_id") == expected["experiment_id"],
        "model": result.get("model") == expected["model"],
        "input": result.get("input") == expected["input"],
        "contract_hash": result.get("contract_hash") == expected["contract_hash"],
        "stage_config": result.get("stage_config") == expected["stage_config"],
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise ValueError(f"cannot resume incompatible full artifact; failed checks: {', '.join(failed)}")
    records = result.get("records", [])
    source_hashes = [source["content_hash"] for source in sources]
    record_hashes = [record.get("content_hash") for record in records]
    if record_hashes != source_hashes[: len(record_hashes)]:
        raise ValueError("cannot resume because record content_hash prefix does not match input")
    if any(record.get("status") != "success" or record.get("headline_count_matches") is not True for record in records):
        raise ValueError("cannot resume artifact containing non-success records")
    finalize_full(result, len(sources))
    result["status"] = "full-inference-running"
    result["passed"] = False
    result["error"] = None
    result.pop("traceback", None)
    write_atomic(args.output, result)
    return result


def full_inference(args: argparse.Namespace) -> dict:
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    sources = payload["records"]
    result = load_or_create_result(args, sources)
    try:
        torch, tokenizer, model = load_model(args)
        result["runtime"].update({
            "device": "cpu",
            "workers": 1,
            "torch": torch.__version__,
            "cuda_available": bool(torch.cuda.is_available()),
            "label_schema": {str(index): label for index, label in LABELS.items()},
            "model_eval_mode": True,
        })
        start_index = len(result["records"])
        for index, source in enumerate(sources[start_index:], start=start_index + 1):
            record = score_source(source, torch, tokenizer, model, args.max_length)
            result["records"].append(record)
            finalize_full(result, len(sources))
            result["status"] = "full-inference-running"
            result["passed"] = False
            write_atomic(args.output, result)
            print(f"full {index}/{len(sources)} {source['information_date']} {record['status']}", flush=True)
        finalize_full(result, len(sources))
        result["error"] = None
        result.pop("traceback", None)
    except Exception as exc:
        result["status"] = "full-inference-infeasible-stop-before-predictive-gate"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
    result["evaluated_at"] = datetime.now(timezone.utc).isoformat()
    write_atomic(args.output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("full",), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--model", default=MODEL_ID)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--experiment-id", default="llm-cryptobert-v1-development")
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    result = full_inference(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.get("passed") else 2)


if __name__ == "__main__":
    main()
