"""Checkpointed one-worker LLM scoring for the outcome-blind v11 policy corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


EVENT_TYPES = {
    "rate_or_balance_sheet", "liquidity_or_emergency", "bank_capital_or_stress",
    "supervision_or_enforcement", "payments_or_access",
    "administrative_or_information", "other",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def api(path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:11434{path}", data=data,
        headers={"Content-Type": "application/json"}, method="GET" if data is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def model_digest(model: str) -> str:
    for item in api("/api/tags").get("models", []):
        if item.get("name") == model:
            return item["digest"]
    raise ValueError(f"model is not installed: {model}")


def validate(result: object, expected: dict) -> dict:
    keys = {
        "event_id", "generic_direction", "generic_intensity", "event_type",
        "policy_direction", "policy_intensity", "surprise_language", "systemic_scope",
        "confidence", "evidence_span",
    }
    if not isinstance(result, dict) or set(result) != keys:
        raise ValueError("result keys differ from frozen schema")
    if result["event_id"] != expected["event_id"]:
        raise ValueError("event_id or output order mismatch")
    if result["event_type"] not in EVENT_TYPES:
        raise ValueError("invalid event_type")
    for key in ("generic_direction", "policy_direction"):
        if isinstance(result[key], bool) or not isinstance(result[key], (int, float)) or not -1 <= float(result[key]) <= 1:
            raise ValueError(f"invalid {key}")
    for key in ("generic_intensity", "policy_intensity", "surprise_language", "systemic_scope", "confidence"):
        if isinstance(result[key], bool) or not isinstance(result[key], (int, float)) or not 0 <= float(result[key]) <= 1:
            raise ValueError(f"invalid {key}")
    evidence = result["evidence_span"]
    if not isinstance(evidence, str) or not evidence or len(evidence) > 240 or evidence not in expected["text"]:
        raise ValueError("evidence_span is not an exact text substring")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request-delay-seconds", type=float, default=2)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    source_path = Path(config["sources"]["events"]["path"])
    prompt_path = Path(config["contract"]["prompt"]["path"])
    schema_path = Path(config["contract"]["schema"]["path"])
    for path, expected in ((source_path, config["sources"]["events"]["sha256"]), (prompt_path, config["contract"]["prompt"]["sha256"]), (schema_path, config["contract"]["schema"]["sha256"])):
        if sha256(path) != expected:
            raise ValueError(f"frozen hash mismatch: {path}")
    if model_digest(config["model"]["name"]) != config["model"]["digest"]:
        raise ValueError("installed model digest differs from freeze")
    events = json.loads(source_path.read_text(encoding="utf-8"))
    prompt = prompt_path.read_text(encoding="utf-8")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    records = []
    if args.output.exists():
        checkpoint = json.loads(args.output.read_text(encoding="utf-8"))
        if checkpoint.get("config_sha256") != sha256(args.config):
            raise ValueError("checkpoint config hash mismatch")
        records = checkpoint["records"]
        if [row["event_id"] for row in records] != [row["event_id"] for row in events[:len(records)]]:
            raise ValueError("checkpoint order mismatch")
    batch_size = int(config["contract"]["batch_size"])
    for start in range(len(records), len(events), batch_size):
        batch = events[start:start + batch_size]
        raw = None
        try:
            response = api("/api/chat", {
                "model": config["model"]["name"], "stream": False, "format": schema,
                "think": False, "keep_alive": "5m",
                "options": {"temperature": 0, "seed": config["contract"]["seed"]},
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps([{"event_id": row["event_id"], "text": row["text"]} for row in batch], ensure_ascii=False)},
                ],
            })
            raw = response["message"]["content"]
            payload = json.loads(raw)
            if set(payload) != {"results"} or len(payload["results"]) != len(batch):
                raise ValueError("batch output count mismatch")
            parsed = [validate(item, expected) for item, expected in zip(payload["results"], batch)]
            records.extend({**item, "status": "success", "error": None} for item in parsed)
        except Exception as exc:
            records.extend({"event_id": row["event_id"], "status": "error", "error": f"{type(exc).__name__}: {exc}", "raw_response": raw} for row in batch)
        write_json(args.output, {
            "schema_version": "open-fed-policy-llm-output-v11", "generated_at": datetime.now(timezone.utc).isoformat(),
            "config_sha256": sha256(args.config), "model": config["model"], "outcomes_consulted": False,
            "workers": 1, "records": records,
            "summary": {"attempted": len(records), "success": sum(x["status"] == "success" for x in records), "errors": sum(x["status"] == "error" for x in records)},
        })
        print(f"{len(records)}/{len(events)} errors={sum(x['status'] == 'error' for x in records)}", flush=True)
        if any(x["status"] == "error" for x in records):
            return
        if start + batch_size < len(events):
            time.sleep(args.request_delay_seconds)


if __name__ == "__main__":
    main()
