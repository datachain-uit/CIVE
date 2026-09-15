"""Checkpointed full-corpus event extraction after the v3.5 reliability gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from score_llm_event_extractor_v3_5 import api, model_digest, parse_batch, sha256, write_json


def checkpoint_header(config: dict, config_hash: str, input_hash: str, run_id: str) -> dict:
    contract = config["frozen_contract"]
    return {
        "type": "header",
        "schema_version": 1,
        "experiment_id": config["experiment_id"],
        "run_id": run_id,
        "model": config["candidate"]["model"],
        "model_digest": config["candidate"]["digest"],
        "config_sha256": config_hash,
        "input_sha256": input_hash,
        "prompt_sha256": contract["prompt"]["sha256"],
        "response_schema_sha256": contract["response_schema"]["sha256"],
        "postprocessor_sha256": contract["postprocessor"]["sha256"],
        "outcomes_consulted": False,
    }


def append_line(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def load_checkpoint(path: Path, header: dict, source: list[dict], batch_size: int) -> list[dict]:
    if not path.exists():
        append_line(path, header)
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or json.loads(lines[0]) != header:
        raise ValueError("checkpoint header differs from frozen full-extraction contract")
    records: list[dict] = []
    for expected_batch_index, line in enumerate(lines[1:]):
        payload = json.loads(line)
        if payload.get("type") != "batch" or payload.get("batch_index") != expected_batch_index:
            raise ValueError("checkpoint batch index is not contiguous")
        batch_records = payload.get("records")
        if not isinstance(batch_records, list) or not 1 <= len(batch_records) <= batch_size:
            raise ValueError("checkpoint batch record count is invalid")
        records.extend(batch_records)
    if len(records) > len(source):
        raise ValueError("checkpoint exceeds frozen full input")
    expected_ids = [item["headline_id"] for item in source[:len(records)]]
    if [item.get("headline_id") for item in records] != expected_ids:
        raise ValueError("checkpoint headline order differs from frozen full input")
    return records


def save_progress(path: Path, config: dict, config_hash: str, input_hash: str,
                  checkpoint: Path, records: list[dict], total: int, batch_size: int) -> None:
    write_json(path, {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "config_sha256": config_hash,
        "input_sha256": input_hash,
        "checkpoint_path": str(checkpoint.resolve()),
        "records": len(records),
        "success": sum(item["status"] == "success" for item in records),
        "errors": sum(item["status"] == "error" for item in records),
        "evidence_fallbacks": sum(item.get("evidence_fallback") is True for item in records),
        "completed_batches": (len(records) + batch_size - 1) // batch_size,
        "expected_records": total,
        "outcomes_consulted": False,
    })


def save_final(path: Path, config: dict, config_hash: str, input_hash: str,
               run_id: str, records: list[dict]) -> None:
    contract = config["frozen_contract"]
    write_json(path, {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "run_id": run_id,
        "status": "full-extraction-complete-outcome-join-prohibited",
        "model": config["candidate"]["model"],
        "model_digest": config["candidate"]["digest"],
        "config_sha256": config_hash,
        "input_sha256": input_hash,
        "prompt_sha256": contract["prompt"]["sha256"],
        "response_schema_sha256": contract["response_schema"]["sha256"],
        "postprocessor_sha256": contract["postprocessor"]["sha256"],
        "batch_size": contract["batch_size"],
        "workers": 1,
        "outcomes_consulted": False,
        "trading_backtest_consulted": False,
        "records": records,
        "summary": {
            "attempted": len(records),
            "success": sum(item["status"] == "success" for item in records),
            "errors": sum(item["status"] == "error" for item in records),
            "evidence_fallbacks": sum(item.get("evidence_fallback") is True for item in records),
        },
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--request-delay-seconds", type=float, default=10)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    contract = config["frozen_contract"]
    config_hash = sha256(args.config)
    input_hash = sha256(args.input)
    if input_hash != contract["full_input"]["sha256"]:
        raise ValueError("full input hash differs from predeclaration")
    for key in ("prompt", "response_schema", "postprocessor", "stage1_gate", "producer", "audit"):
        frozen = contract[key]
        if sha256(Path(frozen["path"])) != frozen["sha256"]:
            raise ValueError(f"{key} hash differs from predeclaration")
    stage1_gate = json.loads(Path(contract["stage1_gate"]["path"]).read_text(encoding="utf-8"))
    if stage1_gate.get("passed") is not True or stage1_gate.get("status") != contract["stage1_gate"]["required_status"]:
        raise ValueError("Stage 1 gate does not authorize full extraction")
    if model_digest(config["candidate"]["model"]) != config["candidate"]["digest"]:
        raise ValueError("installed model digest differs from predeclaration")

    source = json.loads(args.input.read_text(encoding="utf-8"))["records"]
    expected_records = int(contract["full_input"]["records"])
    if len(source) != expected_records:
        raise ValueError("full input count differs from predeclaration")
    prompt = Path(contract["prompt"]["path"]).read_text(encoding="utf-8")
    schema = json.loads(Path(contract["response_schema"]["path"]).read_text(encoding="utf-8"))
    batch_size = int(contract["batch_size"])
    header = checkpoint_header(config, config_hash, input_hash, args.run_id)
    scored = load_checkpoint(args.checkpoint, header, source, batch_size)
    save_progress(args.progress, config, config_hash, input_hash, args.checkpoint,
                  scored, expected_records, batch_size)
    if any(item["status"] == "error" for item in scored):
        return

    retries = int(contract["transport_retries"])
    for start in range(len(scored), len(source), batch_size):
        batch = source[start:start + batch_size]
        expected_batch = [{**item, "item_id": str(offset + 1)}
                          for offset, item in enumerate(batch)]
        user_payload = [{
            "item_id": item["item_id"], "published_at": item["published_at"],
            "available_at": item["available_at"], "source_domain": item["source_domain"],
            "coin_type": item["coin_type"], "headline": item["headline"],
        } for item in expected_batch]
        raw = None
        try:
            response = None
            for attempt in range(retries + 1):
                try:
                    response = api("/api/chat", {
                        "model": config["candidate"]["model"], "stream": False,
                        "format": schema, "think": False, "keep_alive": "5m",
                        "options": {"temperature": 0, "seed": contract["seed"]},
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                        ],
                    })
                    break
                except (urllib.error.URLError, TimeoutError):
                    if attempt == retries:
                        raise
                    time.sleep(5 * (attempt + 1))
            raw = response["message"]["content"]
            parsed = parse_batch(raw, expected_batch, "ordinal_item_id")
            batch_records = [{
                **item, "status": "success", "error": None,
                "information_date": expected["information_date"],
            } for item, expected in zip(parsed, batch)]
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            batch_records = [{
                "headline_id": item["headline_id"],
                "information_date": item["information_date"],
                "status": "error", "error": error, "raw_response": raw,
            } for item in batch]
        batch_index = start // batch_size
        append_line(args.checkpoint, {
            "type": "batch", "batch_index": batch_index, "records": batch_records,
        })
        scored.extend(batch_records)
        save_progress(args.progress, config, config_hash, input_hash, args.checkpoint,
                      scored, expected_records, batch_size)
        print(f"{len(scored)}/{expected_records} batch={batch_index + 1} errors="
              f"{sum(item['status'] == 'error' for item in scored)}", flush=True)
        if any(item["status"] == "error" for item in batch_records):
            return
        if start + batch_size < len(source) and args.request_delay_seconds > 0:
            time.sleep(args.request_delay_seconds)

    save_final(args.output, config, config_hash, input_hash, args.run_id, scored)


if __name__ == "__main__":
    main()
