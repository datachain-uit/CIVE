"""Score causal multi-source information sets with a pinned local Ollama model."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from llm_causal_pipeline import parse_model_response, write_json
from score_llm_causal_corpus import api, model_digest
from score_llm_daily_information_sets import stratified_sample

INPUT_CONTRACT = "crypto-multisource-causal-memory-v2"
PROMPT_VERSION = "crypto-multisource-causal-memory-v2.1"
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "minimum": -1, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason_code": {"type": "string", "maxLength": 240},
    },
    "required": ["score", "confidence", "reason_code"],
    "additionalProperties": False,
}
SYSTEM_PROMPT = (
    "Forecast the specified BTCUSDT forward return using only the supplied point-in-time information. "
    "Respect the stated cutoff, execution delay, and horizon. Integrate news with market regime, "
    "funding, cross-asset breadth, and retrieved historical cases. Do not treat a retrieved outcome as "
    "the current label and do not invent unavailable facts. Return exactly one JSON object with score "
    "in [-1,1], confidence in [0,1], and a short reason_code. Positive is bullish, negative is bearish, "
    "and zero is balanced or insufficient evidence. Do not return any other keys."
)


def score(record: dict, model: str, digest: str, disable_thinking: bool) -> dict:
    base = {
        "content_hash": record["content_hash"], "information_date": record["information_date"],
        "available_at": record["available_at"], "source_snapshot_hash": record["source_snapshot_hash"],
        "article_count": record["article_count"], "selected_article_count": record["selected_article_count"],
        "model": model, "model_digest": digest, "prompt_version": PROMPT_VERSION,
        "prompt_hash": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "thinking": not disable_thinking,
    }
    raw_content = None
    try:
        request = {
            "model": model, "stream": False, "format": RESPONSE_SCHEMA,
            "options": {"temperature": 0, "seed": 20260821},
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": record["text"]}],
        }
        if disable_thinking:
            request["think"] = False
        response = api("/api/chat", request)
        raw_content = response["message"]["content"]
        parsed = parse_model_response(raw_content)
        return {**base, "status": "success", **parsed, "error": None}
    except Exception as exc:
        return {**base, "status": "error", "score": None, "confidence": None,
                "reason_code": None, "error": f"{type(exc).__name__}: {exc}",
                "raw_response": raw_content}


def save(output: Path, run_id: str, model: str, digest: str, input_hash: str,
         records: list[dict], disable_thinking: bool) -> None:
    write_json(output, {
        "schema_version": 2, "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id, "model": model, "model_digest": digest,
        "input_sha256": input_hash, "prompt_version": PROMPT_VERSION,
        "prompt_hash": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "response_schema_hash": hashlib.sha256(
            json.dumps(RESPONSE_SCHEMA, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "thinking": not disable_thinking, "workers": 1, "records": records,
        "summary": {"attempted": len(records),
                    "success": sum(item["status"] == "success" for item in records),
                    "errors": sum(item["status"] == "error" for item in records)},
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
    parser.add_argument("--request-delay-seconds", type=float, default=0.0)
    args = parser.parse_args()
    if args.workers != 1:
        raise ValueError("multi-source scorer requires exactly one worker")
    input_hash = hashlib.sha256(args.input.read_bytes()).hexdigest()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if payload.get("prompt_contract") != INPUT_CONTRACT:
        raise ValueError("input prompt contract does not match scorer")
    selected = stratified_sample(payload["records"], args.sample_per_year)
    digest = model_digest(args.model)
    scored: list[dict] = []
    if args.output.exists():
        checkpoint = json.loads(args.output.read_text(encoding="utf-8"))
        if (checkpoint.get("model_digest") != digest or checkpoint.get("prompt_version") != PROMPT_VERSION
                or checkpoint.get("input_sha256") != input_hash
                or checkpoint.get("thinking", True) != (not args.disable_thinking)):
            raise ValueError("checkpoint model, prompt, input, or thinking mode does not match")
        scored = checkpoint.get("records", [])
    completed = {item["content_hash"] for item in scored}
    pending = [record for record in selected if record["content_hash"] not in completed]
    for index, record in enumerate(pending):
        result = score(record, args.model, digest, args.disable_thinking)
        scored.append(result)
        save(args.output, args.run_id, args.model, digest, input_hash, scored, args.disable_thinking)
        print(f"{len(scored)}/{len(selected)} {record['information_date']} {result['status']}", flush=True)
        if index + 1 < len(pending) and args.request_delay_seconds > 0:
            time.sleep(args.request_delay_seconds)


if __name__ == "__main__":
    main()
