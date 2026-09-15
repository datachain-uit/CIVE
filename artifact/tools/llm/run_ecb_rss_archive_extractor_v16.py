"""Outcome-blind, checkpointed extraction for the frozen ECB RSS v16 corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from score_llm_event_extractor_v3_9 import api, model_digest, parse_batch


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_corpus_v16/corpus.json"
CORPUS_GATE = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_corpus_v16/corpus_gate.json"
PREDECLARED = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_predictive_v16/predeclared.json"
PROMPT = ROOT / "tools/llm/prompts/cftc_rss_event_extractor_v15.txt"
SCHEMA = ROOT / "tools/llm/schemas/llm_event_extraction_batch_v3_2.schema.json"
MODEL = "ministral-3:8b"
MODEL_DIGEST = "1922accd5827ebe6829e536369195db25eaf664528dc66206d646ea3bb386b71"
BATCH_SIZE = 4


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def append(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def preflight(output_dir: Path) -> tuple[list[dict], dict]:
    predeclared = json.loads(PREDECLARED.read_text(encoding="utf-8"))
    corpus_gate = json.loads(CORPUS_GATE.read_text(encoding="utf-8"))
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    if predeclared["status"] != "FROZEN_PENDING_OUTCOME_BLIND_EXTRACTION":
        raise ValueError("predictive predeclaration is not frozen")
    if corpus_gate["status"] != "OUTCOME_BLIND_CORPUS_GATE_PASS_EXTRACTION_AUTHORIZED" or corpus_gate.get("target_join_authorized") is not False:
        raise ValueError("outcome-blind corpus gate has not authorized extraction")
    if corpus.get("market_data_accessed") is not False or corpus.get("model_run") is not False:
        raise ValueError("corpus no longer satisfies outcome-blind input contract")
    records = corpus["records"]
    if len(records) != 2249 or len({item["record_id"] for item in records}) != len(records):
        raise ValueError("frozen corpus count or identifiers differ")
    manifest = {
        "schema_version": "ecb-rss-extraction-preflight-v16",
        "status": "FROZEN_BEFORE_MODEL_RUN",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "model_digest": MODEL_DIGEST,
        "workers": 1,
        "batch_size": BATCH_SIZE,
        "outcomes_consulted": False,
        "trading_backtest_consulted": False,
        "inputs": {str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path) for path in (PREDECLARED, CORPUS_GATE, CORPUS, PROMPT, SCHEMA, Path(__file__))},
        "expected_records": len(records),
    }
    path = output_dir / "extraction_preflight.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != manifest:
        raise ValueError("preflight differs from frozen extraction contract")
    atomic_json(path, manifest)
    return records, manifest


def load_checkpoint(path: Path, header: dict, records: list[dict]) -> list[dict]:
    if not path.exists():
        append(path, header)
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or json.loads(lines[0]) != header:
        raise ValueError("checkpoint header differs from frozen extraction contract")
    scored = []
    for index, line in enumerate(lines[1:]):
        payload = json.loads(line)
        if payload.get("batch_index") != index or not isinstance(payload.get("records"), list):
            raise ValueError("checkpoint is not contiguous")
        scored.extend(payload["records"])
    if len(scored) > len(records) or [item["record_id"] for item in scored] != [item["record_id"] for item in records[:len(scored)]]:
        raise ValueError("checkpoint record order differs from frozen corpus")
    return scored


def save_progress(path: Path, manifest: dict, checkpoint: Path, scored: list[dict]) -> None:
    atomic_json(path, {"status": "EXTRACTION_IN_PROGRESS", "updated_at": datetime.now(timezone.utc).isoformat(), "expected_records": manifest["expected_records"], "records": len(scored), "success": sum(item["status"] == "success" for item in scored), "errors": sum(item["status"] == "error" for item in scored), "checkpoint": str(checkpoint.resolve()), "outcomes_consulted": False})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--request-delay-seconds", type=float, default=5.0)
    args = parser.parse_args()
    output_dir = args.output_dir
    records, manifest = preflight(output_dir)
    if model_digest(MODEL) != MODEL_DIGEST:
        raise ValueError("installed model digest differs from frozen extraction contract")
    prompt = PROMPT.read_text(encoding="utf-8")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    checkpoint = output_dir / "extraction_checkpoint.ndjson"
    progress = output_dir / "extraction_progress.json"
    header = {"type": "header", "experiment_id": "ecb-rss-archive-llm-only-event-conditioned-v16-development", "manifest": manifest, "run_id": "ecb-rss-v16"}
    scored = load_checkpoint(checkpoint, header, records)
    save_progress(progress, manifest, checkpoint, scored)
    if any(item["status"] == "error" for item in scored):
        return
    for start in range(len(scored), len(records), BATCH_SIZE):
        batch = records[start:start + BATCH_SIZE]
        expected = [{"headline_id": item["record_id"], "headline": item["text"], "item_id": str(index + 1)} for index, item in enumerate(batch)]
        raw = None
        try:
            for attempt in range(4):
                try:
                    response = api("/api/chat", {"model": MODEL, "stream": False, "format": schema, "think": False, "keep_alive": "5m", "options": {"temperature": 0, "seed": 20260909}, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps([{ "item_id": item["item_id"], "text": item["headline"]} for item in expected], ensure_ascii=False)}]})
                    raw = response["message"]["content"]
                    parsed = parse_batch(raw, expected, "ordinal_item_id")
                    batch_records = [{**value, "record_id": source["record_id"], "archive_capture_at": source["archive_capture_at"], "status": "success", "error": None} for value, source in zip(parsed, batch)]
                    break
                except (urllib.error.URLError, TimeoutError):
                    if attempt == 3:
                        raise
                    time.sleep(5 * (attempt + 1))
            else:
                raise RuntimeError("unreachable retry state")
        except Exception as exc:
            batch_records = [{"record_id": item["record_id"], "archive_capture_at": item["archive_capture_at"], "status": "error", "error": f"{type(exc).__name__}: {exc}", "raw_response": raw} for item in batch]
        append(checkpoint, {"batch_index": start // BATCH_SIZE, "records": batch_records})
        scored.extend(batch_records)
        save_progress(progress, manifest, checkpoint, scored)
        print(f"{len(scored)}/{len(records)} errors={sum(item['status'] == 'error' for item in scored)}", flush=True)
        if any(item["status"] == "error" for item in batch_records):
            return
        if start + BATCH_SIZE < len(records):
            time.sleep(args.request_delay_seconds)
    atomic_json(output_dir / "extraction.json", {"status": "EXTRACTION_COMPLETE_OUTCOME_JOIN_PROHIBITED", "manifest": manifest, "records": scored, "summary": {"attempted": len(scored), "success": sum(item["status"] == "success" for item in scored), "errors": sum(item["status"] == "error" for item in scored)}, "outcomes_consulted": False, "trading_backtest_consulted": False})


if __name__ == "__main__":
    main()

