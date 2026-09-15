"""Run v3.4 strict-schema event extraction with deterministic evidence alignment."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


OUTPUT_KEYS = {
    "headline_id", "btc_relevance", "event_type", "affected_assets", "direction",
    "severity", "reported_surprise", "expected_horizon", "confidence", "evidence_span",
}
ORDINAL_OUTPUT_KEYS = (OUTPUT_KEYS - {"headline_id"}) | {"item_id"}


def align_evidence_span(headline: str, evidence: str) -> str:
    if evidence in headline:
        return evidence
    substitutions = str.maketrans({
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u00a0": " ",
    })
    normalized_headline = headline.translate(substitutions)
    normalized_evidence = evidence.translate(substitutions)
    start = normalized_headline.find(normalized_evidence)
    if start >= 0:
        return headline[start:start + len(evidence)]

    # Expand only ordered, exact fragments when the model abbreviates source text.
    ellipsis_fragments = [
        fragment.strip() for fragment in normalized_evidence.replace("\u2026", "...").split("...")
        if fragment.strip()
    ]
    if len(ellipsis_fragments) >= 2:
        first = normalized_headline.find(ellipsis_fragments[0])
        if first >= 0:
            cursor = first + len(ellipsis_fragments[0])
            end = cursor
            for fragment in ellipsis_fragments[1:]:
                fragment_start = normalized_headline.find(fragment, cursor)
                if fragment_start < 0:
                    break
                end = fragment_start + len(fragment)
                cursor = end
            else:
                return headline[first:end]

    def searchable(value: str) -> tuple[str, list[int]]:
        characters: list[str] = []
        source_indexes: list[int] = []
        for index, character in enumerate(value.translate(substitutions)):
            if character in ",.;:!?":
                continue
            characters.append(character)
            source_indexes.append(index)
        return "".join(characters), source_indexes

    searchable_headline, source_indexes = searchable(headline)
    searchable_evidence, _ = searchable(evidence)
    start = searchable_headline.find(searchable_evidence)
    if start < 0:
        raise ValueError("evidence_span is not an exact or punctuation-normalized headline substring")
    end = start + len(searchable_evidence) - 1
    return headline[source_indexes[start]:source_indexes[end] + 1]


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


def validate_item(item: object, expected: dict, identifier_mode: str = "headline_id") -> dict:
    required_keys = ORDINAL_OUTPUT_KEYS if identifier_mode == "ordinal_item_id" else OUTPUT_KEYS
    if not isinstance(item, dict) or set(item) != required_keys:
        raise ValueError("event item keys do not match the frozen contract")
    identifier_key = "item_id" if identifier_mode == "ordinal_item_id" else "headline_id"
    expected_identifier = expected[identifier_key]
    if item[identifier_key] != expected_identifier:
        raise ValueError(f"{identifier_key} or output order mismatch")
    if item["btc_relevance"] not in {"direct", "systemic", "indirect", "none"}:
        raise ValueError("invalid btc_relevance")
    if item["event_type"] not in {
        "macro_liquidity", "regulation", "etf_institutional_flow", "exchange_security",
        "liquidation_leverage", "network_protocol", "fraud_legal", "adoption_business",
        "market_commentary", "other",
    }:
        raise ValueError("invalid event_type")
    if item["direction"] not in {"positive", "negative", "mixed", "unclear"}:
        raise ValueError("invalid direction")
    if item["expected_horizon"] not in {"4h", "12h", "24h", "72h", "unknown"}:
        raise ValueError("invalid expected_horizon")
    assets = item["affected_assets"]
    if not isinstance(assets, list) or len(assets) > 12 or len(set(assets)) != len(assets):
        raise ValueError("invalid affected_assets")
    if any(not isinstance(value, str) or not value.strip() or len(value) > 32 for value in assets):
        raise ValueError("invalid affected asset value")
    for key in ("severity", "reported_surprise", "confidence"):
        if isinstance(item[key], bool) or not isinstance(item[key], (int, float)):
            raise ValueError(f"{key} must be numeric")
        if not 0 <= float(item[key]) <= 1:
            raise ValueError(f"{key} outside [0,1]")
    evidence = item["evidence_span"]
    if not isinstance(evidence, str) or not evidence or len(evidence) > 240:
        raise ValueError("invalid evidence_span")
    aligned_evidence = align_evidence_span(expected["headline"], evidence)
    if item["btc_relevance"] == "direct" and not any(
        value.upper() in {"BTC", "BITCOIN"} for value in assets
    ):
        raise ValueError("direct BTC relevance requires BTC or Bitcoin in affected_assets")
    validated = {**item, "evidence_span": aligned_evidence}
    if identifier_mode == "ordinal_item_id":
        return {"headline_id": expected["headline_id"], **{
            key: value for key, value in validated.items() if key != "item_id"
        }}
    return validated


def parse_batch(raw: str, expected: list[dict], identifier_mode: str = "headline_id") -> list[dict]:
    payload = json.loads(raw)
    if not isinstance(payload, dict) or set(payload) != {"results"}:
        raise ValueError("batch response must contain only results")
    results = payload["results"]
    if not isinstance(results, list) or len(results) != len(expected):
        raise ValueError("batch output count mismatch")
    return [validate_item(item, source, identifier_mode) for item, source in zip(results, expected)]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.25 * (attempt + 1))


def save(output: Path, config: dict, config_hash: str, input_hash: str,
         run_id: str, records: list[dict]) -> None:
    contract = config["frozen_contract"]
    write_json(output, {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config["experiment_id"],
        "run_id": run_id,
        "model": config["candidate"]["model"],
        "model_digest": config["candidate"]["digest"],
        "config_sha256": config_hash,
        "input_sha256": input_hash,
        "prompt_sha256": contract["prompt"]["sha256"],
        "response_schema_sha256": contract["response_schema"]["sha256"],
        "batch_size": contract["batch_size"],
        "workers": 1,
        "outcomes_consulted": False,
        "records": records,
        "summary": {
            "attempted": len(records),
            "success": sum(item["status"] == "success" for item in records),
            "errors": sum(item["status"] == "error" for item in records),
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
    config_hash = sha256(args.config)
    input_hash = sha256(args.input)
    if input_hash != contract["stage1_sample"]["sha256"]:
        raise ValueError("Stage 1 sample hash differs from predeclaration")
    for key in ("prompt", "response_schema", "postprocessor"):
        if key not in contract:
            continue
        path = Path(contract[key]["path"])
        if sha256(path) != contract[key]["sha256"]:
            raise ValueError(f"{key} hash differs from predeclaration")
    installed_digest = model_digest(config["candidate"]["model"])
    if installed_digest != config["candidate"]["digest"]:
        raise ValueError("installed model digest differs from predeclaration")

    source = json.loads(args.input.read_text(encoding="utf-8"))["records"]
    expected_records = contract["stage1_sample"]["records"]
    if len(source) != expected_records:
        raise ValueError("Stage 1 sample count differs from predeclaration")
    prompt = Path(contract["prompt"]["path"]).read_text(encoding="utf-8")
    schema = json.loads(Path(contract["response_schema"]["path"]).read_text(encoding="utf-8"))

    scored: list[dict] = []
    if args.output.exists():
        checkpoint = json.loads(args.output.read_text(encoding="utf-8"))
        frozen = {
            "model_digest": config["candidate"]["digest"], "config_sha256": config_hash,
            "input_sha256": input_hash, "prompt_sha256": contract["prompt"]["sha256"],
            "response_schema_sha256": contract["response_schema"]["sha256"],
        }
        if any(checkpoint.get(key) != value for key, value in frozen.items()):
            raise ValueError("checkpoint differs from frozen model/config/input/prompt/schema")
        scored = checkpoint.get("records", [])
    completed = len(scored)
    if completed > len(source) or scored and [item["headline_id"] for item in scored] != [
        item["headline_id"] for item in source[:completed]
    ]:
        raise ValueError("checkpoint order or count is invalid")

    batch_size = int(contract["batch_size"])
    identifier_mode = contract.get("identifier_mode", "headline_id")
    for start in range(completed, len(source), batch_size):
        batch = source[start:start + batch_size]
        expected_batch = [
            {**item, "item_id": str(offset + 1)} for offset, item in enumerate(batch)
        ] if identifier_mode == "ordinal_item_id" else batch
        user_payload = [{
            ("item_id" if identifier_mode == "ordinal_item_id" else "headline_id"):
                item["item_id"] if identifier_mode == "ordinal_item_id" else item["headline_id"],
            "published_at": item["published_at"],
            "available_at": item["available_at"], "source_domain": item["source_domain"],
            "coin_type": item["coin_type"], "headline": item["headline"],
        } for item in expected_batch]
        raw = None
        try:
            response = api("/api/chat", {
                "model": config["candidate"]["model"], "stream": False, "format": schema,
                "think": False, "keep_alive": "5m",
                "options": {"temperature": 0, "seed": contract["seed"]},
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
            })
            raw = response["message"]["content"]
            parsed = parse_batch(raw, expected_batch, identifier_mode)
            scored.extend({
                **item, "status": "success", "error": None,
                "information_date": expected["information_date"],
            } for item, expected in zip(parsed, batch))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            scored.extend({
                "headline_id": item["headline_id"], "information_date": item["information_date"],
                "status": "error", "error": error, "raw_response": raw,
            } for item in batch)
        save(args.output, config, config_hash, input_hash, args.run_id, scored)
        print(f"{len(scored)}/{len(source)} batch={start // batch_size + 1} errors="
              f"{sum(item['status'] == 'error' for item in scored)}", flush=True)
        if any(item["status"] == "error" for item in scored):
            return
        if start + batch_size < len(source) and args.request_delay_seconds > 0:
            time.sleep(args.request_delay_seconds)


if __name__ == "__main__":
    main()
