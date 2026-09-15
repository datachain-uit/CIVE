#!/usr/bin/env python3
"""Outcome-free, thermally guarded deterministic LLM dry run for v12.5.6."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "paper" / "input" / "results" / "llm" / "v12_5" / "federal_register_crypto_rights_strict_v12_5_5_1" / "corpus.json"
OUT = ROOT / "paper" / "input" / "results" / "llm" / "v12_5" / "federal_register_llm_dry_run_v12_5_11"
CHECKPOINT = OUT / "checkpoint.json"
THERMAL_LOG = OUT / "thermal.jsonl"
MODEL = "ministral-3:8b"
MODEL_LIST_DIGEST = "1922accd5827"
SEED = 20260906
SAMPLE_SIZE = 30
REPEAT_COUNT = 3
MAX_DOCUMENT_CHARS = 4000
MAX_EVENT_CHARS = 12000
STOP_C = 75
RESUME_C = 70

SYSTEM = (
    "Read only the supplied regulatory text. Do not use outside facts, prices, "
    "dates, market history, or identifiers. Return only valid JSON matching the "
    "requested schema. The evidence value must be an exact substring of the supplied text."
)
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["policy_stance", "market_scope", "actionability", "btc_relevance", "evidence"],
    "properties": {
        "policy_stance": {"type": "string", "enum": ["restrictive", "permissive", "mixed_or_unclear"]},
        "market_scope": {"type": "string", "enum": ["systemic", "sector_specific", "non_market"]},
        "actionability": {"type": "string", "enum": ["immediate", "prospective", "unclear"]},
        "btc_relevance": {"type": "string", "enum": ["direct", "indirect", "unclear"]},
        "evidence": {"type": "string", "minLength": 1},
    },
}


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_gpu() -> dict[str, int]:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu", "--format=csv,noheader,nounits"],
        check=True, capture_output=True, text=True, timeout=10,
    )
    first = result.stdout.strip().splitlines()[0]
    temperature, utilization = [int(piece.strip().replace("%", "")) for piece in first.split(",")]
    return {"temperature_c": temperature, "utilization_percent": utilization}


def balanced_power_plan() -> bool:
    result = subprocess.run(["powercfg", "/getactivescheme"], check=True, capture_output=True, text=True, timeout=10)
    return "balanced" in result.stdout.lower()


class ThermalGuard:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.over_limit = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        with THERMAL_LOG.open("a", encoding="utf-8") as log:
            while not self.stop.is_set():
                now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                try:
                    reading = read_gpu()
                    record = {"at_utc": now, **reading}
                    if reading["temperature_c"] >= STOP_C:
                        self.over_limit.set()
                        record["hard_stop"] = True
                        subprocess.run(["ollama", "stop", MODEL], capture_output=True, text=True, timeout=30)
                except Exception as error:
                    self.over_limit.set()
                    record = {"at_utc": now, "sensor_error": str(error), "hard_stop": True}
                    subprocess.run(["ollama", "stop", MODEL], capture_output=True, text=True, timeout=30)
                log.write(json.dumps(record, sort_keys=True) + "\n")
                log.flush()
                self.stop.wait(5)

    def __enter__(self) -> "ThermalGuard":
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop.set()
        self.thread.join(timeout=10)


def normalized(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def build_events() -> list[dict[str, str]]:
    docs = json.loads(CORPUS.read_text(encoding="utf-8"))
    by_time: dict[str, list[dict[str, object]]] = defaultdict(list)
    for doc in docs:
        for key in ("id", "available_at_utc", "title", "text", "text_sha256"):
            if key not in doc:
                raise ValueError("missing corpus field: " + key)
        if sha256(normalized(str(doc["text"])).encode("utf-8")) != doc["text_sha256"]:
            raise ValueError("text hash mismatch: " + str(doc["id"]))
        by_time[str(doc["available_at_utc"])].append(doc)

    events = []
    for available_at, group in by_time.items():
        chunks, total = [], 0
        for doc in sorted(group, key=lambda item: str(item["id"])):
            chunk = "TITLE:\n" + normalized(str(doc["title"])) + "\nTEXT:\n" + normalized(str(doc["text"]))[:MAX_DOCUMENT_CHARS]
            if total + len(chunk) > MAX_EVENT_CHARS:
                break
            chunks.append(chunk)
            total += len(chunk)
        if not chunks:
            raise ValueError("empty event after deterministic truncation: " + available_at)
        event_id = "fr-regulatory-" + available_at
        events.append({"event_id": event_id, "available_at_utc": available_at, "prompt_text": "\n\n--- DOCUMENT ---\n\n".join(chunks)})
    if len(events) != 109:
        raise ValueError("expected frozen 109 events, got " + str(len(events)))
    return events


def ask_model(prompt_text: str) -> tuple[dict[str, object] | None, str | None]:
    payload = {
        "model": MODEL,
        "stream": False,
        "format": SCHEMA,
        "options": {"temperature": 0, "top_p": 1, "seed": SEED},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "REGULATORY TEXT START\n" + prompt_text + "\nREGULATORY TEXT END"},
        ],
    }
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result["message"]["content"]
        return json.loads(content), None
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as error:
        return None, str(error)


def validate(output: dict[str, object] | None, prompt_text: str) -> tuple[bool, str | None]:
    if not isinstance(output, dict) or set(output) != set(SCHEMA["required"]):
        return False, "schema"
    for name, spec in SCHEMA["properties"].items():
        value = output.get(name)
        if not isinstance(value, str):
            return False, "non_string_" + name
        if "enum" in spec and value not in spec["enum"]:
            return False, "enum_" + name
    if not output["evidence"] or output["evidence"] not in prompt_text:
        return False, "evidence_not_substring"
    return True, None


def main() -> int:
    if os.environ.get("KLTN_ALLOW_DRY_RUN") != "YES":
        raise SystemExit("set KLTN_ALLOW_DRY_RUN=YES after reviewing this frozen executor")
    OUT.mkdir(parents=True, exist_ok=True)
    if not balanced_power_plan():
        raise SystemExit("active Windows power plan is not Balanced")
    start_gpu = read_gpu()
    if start_gpu["temperature_c"] > RESUME_C:
        raise SystemExit("GPU exceeds 70C pre-start")
    listed = subprocess.run(["ollama", "list"], check=True, capture_output=True, text=True, timeout=20).stdout
    if MODEL_LIST_DIGEST not in listed:
        raise SystemExit("model digest is not pinned in ollama list")

    events = sorted(build_events(), key=lambda item: sha256(item["event_id"].encode("utf-8")))
    selected = events[:SAMPLE_SIZE]
    state = json.loads(CHECKPOINT.read_text(encoding="utf-8")) if CHECKPOINT.exists() else {"selected_event_ids": [item["event_id"] for item in selected], "runs": {}}
    if state["selected_event_ids"] != [item["event_id"] for item in selected]:
        raise SystemExit("checkpoint selection differs from frozen hash selection")

    manifest = {
        "status": "DRY_RUN_IN_PROGRESS",
        "model": MODEL,
        "model_list_digest": MODEL_LIST_DIGEST,
        "seed": SEED,
        "sample_size": SAMPLE_SIZE,
        "repeat_count": REPEAT_COUNT,
        "corpus_path": str(CORPUS.relative_to(ROOT)).replace("\\", "/"),
        "corpus_declared_sha256": "a0ab4923badb52665b9deaae077e578b42e9ef1490b88422079183bbed8fab53",
        "market_data_accessed_by_executor": False,
        "target_materialized": False,
        "start_gpu": start_gpu,
    }
    atomic_json(OUT / "manifest.json", manifest)

    try:
        with ThermalGuard() as guard:
            for item in selected + selected[:REPEAT_COUNT]:
                key = item["event_id"] if item["event_id"] not in state["runs"] else item["event_id"] + "#repeat"
                if key in state["runs"]:
                    continue
                if guard.over_limit.is_set():
                    raise RuntimeError("thermal hard stop")
                output, transport_error = ask_model(item["prompt_text"])
                valid, error = validate(output, item["prompt_text"])
                state["runs"][key] = {
                    "event_id": item["event_id"],
                    "prompt_sha256": sha256(item["prompt_text"].encode("utf-8")),
                    "output": output,
                    "valid": valid,
                    "error": transport_error or error,
                }
                atomic_json(CHECKPOINT, state)
                print("DONE", key, "valid=" + str(valid), flush=True)
                if guard.over_limit.is_set():
                    raise RuntimeError("thermal hard stop")
    except Exception as error:
        manifest["status"] = "DRY_RUN_STOPPED"
        manifest["stop_reason"] = str(error)
        atomic_json(OUT / "manifest.json", manifest)
        subprocess.run(["ollama", "stop", MODEL], capture_output=True, text=True, timeout=30)
        return 2

    primary = [state["runs"][item["event_id"]] for item in selected]
    repeats = [state["runs"][item["event_id"] + "#repeat"] for item in selected[:REPEAT_COUNT]]
    repeatable = all(primary[index]["output"] == repeats[index]["output"] for index in range(REPEAT_COUNT))
    valid_rate = sum(item["valid"] for item in primary) / SAMPLE_SIZE
    manifest.update({
        "status": "DRY_RUN_PASS" if valid_rate >= 0.95 and repeatable else "DRY_RUN_FAIL",
        "valid_count": sum(item["valid"] for item in primary),
        "valid_rate": valid_rate,
        "repeatable_first_three": repeatable,
        "end_gpu": read_gpu(),
    })
    atomic_json(OUT / "manifest.json", manifest)
    subprocess.run(["ollama", "stop", MODEL], capture_output=True, text=True, timeout=30)
    return 0 if manifest["status"] == "DRY_RUN_PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
