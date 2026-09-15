"""Score causal news snapshots with a pinned local Ollama model."""
from __future__ import annotations
import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from llm_causal_pipeline import parse_model_response, write_json

PROMPT_VERSION = "crypto-direction-v1"
SYSTEM_PROMPT = (
    "You classify the directional impact of one crypto news item using only its text. "
    "Return exactly one JSON object with score in [-1,1], confidence in [0,1], and a short "
    "reason_code. Positive means bullish for the broad crypto market over the next 24 hours; "
    "negative means bearish; use zero for irrelevant or balanced information. Do not infer facts "
    "not present in the text."
)

def api(path: str, payload: dict | None = None) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:11434{path}",
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())

def model_digest(model: str) -> str:
    models = api("/api/tags").get("models", [])
    match = next((item for item in models if item.get("name") == model), None)
    if not match: raise ValueError(f"Ollama model not installed: {model}")
    return str(match["digest"])

def score_record(record: dict, model: str, digest: str) -> dict:
    base = {
        "content_hash": record["content_hash"], "available_at": record["available_at"],
        "model": model, "model_digest": digest, "prompt_version": PROMPT_VERSION,
        "prompt_hash": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
    }
    try:
        response = api("/api/chat", {
            "model": model, "stream": False, "format": "json",
            "options": {"temperature": 0, "seed": 20260814},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": record["text"]},
            ],
        })
        parsed = parse_model_response(response["message"]["content"])
        return {**base, "status": "success", **parsed, "error": None}
    except Exception as exc:
        return {**base, "status": "error", "score": None, "confidence": None,
                "reason_code": None, "error": f"{type(exc).__name__}: {exc}"}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("results/llm_causal_corpus_v1.json"))
    parser.add_argument("--model", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--run-id", default="run1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.input.read_text(encoding="utf-8"))[args.offset:]
    if args.limit: records = records[:args.limit]
    digest = model_digest(args.model)
    scored = [score_record(record, args.model, digest) for record in records]
    payload = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": args.run_id, "model": args.model, "model_digest": digest,
        "prompt_version": PROMPT_VERSION, "records": scored,
        "summary": {"attempted": len(scored), "success": sum(r["status"] == "success" for r in scored),
                    "errors": sum(r["status"] == "error" for r in scored)},
    }
    write_json(args.output, payload); print(json.dumps(payload["summary"], indent=2))

if __name__ == "__main__": main()
