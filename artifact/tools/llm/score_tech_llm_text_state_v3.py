"""Thermal-wrapper-compatible Ollama scorer for HYB-003 text-state extraction."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUTPUT_KEYS = {
    "item_id", "affected_asset_scope", "held_long_pressure", "mechanism",
    "event_stage", "horizon_mass", "confidence", "evidence_span",
}
SCOPES = {"direct_held", "crypto_systemic", "other", "unknown"}
PRESSURES = {"adverse", "supportive", "two_sided", "unknown"}
MECHANISMS = {
    "forced_long_selling", "forced_short_buying", "solvency", "security_loss",
    "protocol_outage", "legal_restriction", "flow_demand", "other",
}
STAGES = {"rumor", "initial_announcement", "escalation", "ongoing", "resolution", "retrospective", "unknown"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def align_evidence(headline: str, evidence: str) -> tuple[str, bool]:
    if evidence in headline:
        return evidence, False
    substitutions = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u00a0": " "})
    normalized_headline = headline.translate(substitutions)
    normalized_evidence = evidence.translate(substitutions)
    start = normalized_headline.find(normalized_evidence)
    if start >= 0:
        return headline[start:start + len(evidence)], False
    return headline, True


def validate_item(item: Any, expected: dict[str, Any], ordinal: int) -> dict[str, Any]:
    if not isinstance(item, dict) or set(item) != OUTPUT_KEYS:
        raise ValueError("output keys do not match frozen text-state contract")
    if item["item_id"] != ordinal:
        raise ValueError("item_id/order mismatch")
    if item["affected_asset_scope"] not in SCOPES:
        raise ValueError("invalid affected_asset_scope")
    if item["held_long_pressure"] not in PRESSURES:
        raise ValueError("invalid held_long_pressure")
    if item["mechanism"] not in MECHANISMS:
        raise ValueError("invalid mechanism")
    if item["event_stage"] not in STAGES:
        raise ValueError("invalid event_stage")
    horizon = item["horizon_mass"]
    if not isinstance(horizon, dict) or set(horizon) != {"h4", "h12", "h24", "h72"}:
        raise ValueError("invalid horizon_mass keys")
    for key, value in horizon.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            raise ValueError(f"invalid horizon_mass.{key}")
    if abs(sum(float(value) for value in horizon.values()) - 1.0) > 0.001:
        raise ValueError("horizon_mass must sum to one")
    confidence = item["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        raise ValueError("invalid confidence")
    evidence = item["evidence_span"]
    if not isinstance(evidence, str) or not evidence or len(evidence) > 240:
        raise ValueError("invalid evidence_span")
    aligned, fallback = align_evidence(expected["headline"], evidence)
    return {
        "context_id": expected["context_id"], "trade_id": expected["trade_id"],
        "symbol": expected["symbol"], "decision_time_iso": expected["decision_time_iso"],
        "headline_id": expected["headline_id"], "available_at": expected["available_at"],
        "source_domain": expected["source_domain"], "headline": expected["headline"],
        **{key: value for key, value in item.items() if key != "item_id"},
        "evidence_span": aligned, "evidence_fallback": fallback,
    }


def parse_batch(raw: str, expected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = json.loads(raw)
    if not isinstance(payload, dict) or set(payload) != {"records"}:
        raise ValueError("batch response must contain only records")
    records = payload["records"]
    if not isinstance(records, list) or len(records) != len(expected):
        raise ValueError("batch output count mismatch")
    return [validate_item(item, source, ordinal) for ordinal, (item, source) in enumerate(zip(records, expected))]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.25 * (attempt + 1))


def save(output: Path, config: dict, config_hash: str, input_hash: str, run_id: str, records: list[dict]) -> None:
    contract = config["frozen_contract"]
    write_json(output, {
        "schema_version": "tech-llm-text-state-extraction-v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"], "run_id": run_id,
        "model": config["candidate"]["model"], "model_digest": config["candidate"]["digest"],
        "config_sha256": config_hash, "input_sha256": input_hash,
        "prompt_sha256": contract["prompt"]["sha256"],
        "response_schema_sha256": contract["response_schema"]["sha256"],
        "batch_size": contract["batch_size"], "workers": 1,
        "outcomes_consulted": False, "records": records,
        "summary": {
            "attempted": len(records),
            "success": sum(row["status"] == "success" for row in records),
            "errors": sum(row["status"] == "error" for row in records),
            "evidence_fallbacks": sum(row.get("evidence_fallback") is True for row in records),
        },
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--request-delay-seconds", type=float, default=10)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    contract = config["frozen_contract"]
    config_hash, input_hash = sha256(args.config), sha256(args.input)
    if input_hash != contract["stage1_sample"]["sha256"]:
        raise ValueError("Stage 1 input hash differs from predeclaration")
    for key in ("prompt", "response_schema", "postprocessor", "audit"):
        path = Path(contract[key]["path"])
        if sha256(path) != contract[key]["sha256"]:
            raise ValueError(f"{key} hash differs from predeclaration")
    if model_digest(config["candidate"]["model"]) != config["candidate"]["digest"]:
        raise ValueError("installed model digest differs from predeclaration")
    source = json.loads(args.input.read_text(encoding="utf-8"))["records"]
    if len(source) != contract["stage1_sample"]["records"]:
        raise ValueError("Stage 1 record count differs from predeclaration")
    prompt = Path(contract["prompt"]["path"]).read_text(encoding="utf-8")
    schema = json.loads(Path(contract["response_schema"]["path"]).read_text(encoding="utf-8"))
    scored = []
    if args.output.exists():
        checkpoint = json.loads(args.output.read_text(encoding="utf-8"))
        expected_metadata = {
            "model_digest": config["candidate"]["digest"], "config_sha256": config_hash,
            "input_sha256": input_hash, "prompt_sha256": contract["prompt"]["sha256"],
            "response_schema_sha256": contract["response_schema"]["sha256"],
        }
        if any(checkpoint.get(key) != value for key, value in expected_metadata.items()):
            raise ValueError("checkpoint metadata differs from frozen contract")
        scored = checkpoint.get("records", [])
    completed = len(scored)
    if completed > len(source) or scored and [row["context_id"] for row in scored] != [row["context_id"] for row in source[:completed]]:
        raise ValueError("checkpoint order/count mismatch")
    batch_size = int(contract["batch_size"])
    for start in range(completed, len(source), batch_size):
        batch = source[start:start + batch_size]
        user_payload = {"items": [
            {"item_id": ordinal, "held_asset": row["symbol"], "headline": row["headline"]}
            for ordinal, row in enumerate(batch)
        ]}
        raw = None
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
            raw = response["message"]["content"]
            parsed = parse_batch(raw, batch)
            scored.extend({**row, "status": "success", "error": None} for row in parsed)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            scored.extend({
                "context_id": row["context_id"], "trade_id": row["trade_id"],
                "symbol": row["symbol"], "decision_time_iso": row["decision_time_iso"],
                "headline_id": row["headline_id"], "status": "error", "error": error,
                "raw_response": raw,
            } for row in batch)
        save(args.output, config, config_hash, input_hash, args.run_id, scored)
        errors = sum(row["status"] == "error" for row in scored)
        print(f"{len(scored)}/{len(source)} batch={start // batch_size + 1} errors={errors}", flush=True)
        if errors:
            return
        if start + batch_size < len(source) and args.request_delay_seconds > 0:
            time.sleep(args.request_delay_seconds)


if __name__ == "__main__":
    main()
