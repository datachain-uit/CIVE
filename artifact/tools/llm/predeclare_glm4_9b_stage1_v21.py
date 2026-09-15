"""Freeze the GLM-4 9B Q3_K_M Stage-1 reliability contract before inference."""
from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "runtime/glm4_9b_challenger/configs/llm_event_extractor_glm4_9b_v21_stage1_predeclared.json"
MODEL = "glm4:9b-chat-q3_K_M"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def installed_model() -> dict:
    request = urllib.request.Request("http://127.0.0.1:11434/api/tags")
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    for item in payload.get("models", []):
        if item.get("name") == MODEL or item.get("model") == MODEL:
            return item
    raise RuntimeError(f"Model is not installed: {MODEL}")


def main() -> None:
    sample = ROOT / "paper/input/results/llm/v3/llm_event_extractor_stage1_sample_v3_frozen.json"
    full_input = ROOT / "paper/input/results/llm/v3/llm_event_extraction_inputs_v3_development.json"
    sampler = ROOT / "tools/llm/build_llm_event_reliability_sample_v3.py"
    prompt = ROOT / "tools/llm/prompts/llm_event_extractor_v3.txt"
    schema = ROOT / "tools/llm/schemas/llm_event_extraction_batch_v3.schema.json"
    model = installed_model()
    payload = {
        "schema_version": 1,
        "experiment_id": "LLM-085-glm4-9b-q3km-event-extractor-stage1-reliability",
        "status": "predeclared-before-event-extractor-inference",
        "predeclared_at": datetime.now(timezone(timedelta(hours=7))).isoformat(),
        "research_role": "article-level structured event extraction; no return forecast and no trading action",
        "selection_basis": (
            "Preselected local challenger from an untested GLM model family; the exact 5.1 GB Q3_K_M artifact fits the "
            "available 6 GB GPU. Selection was made before this model produced any project output and was not based on returns."
        ),
        "candidate": {
            "model": MODEL,
            "digest": model["digest"],
            "architecture": model.get("details", {}).get("family", "glm4"),
            "parameters": model.get("details", {}).get("parameter_size", "9B"),
            "quantization": model.get("details", {}).get("quantization_level", "Q3_K_M"),
            "license": "glm-4-9b License; academic research use permitted",
        },
        "frozen_contract": {
            "full_input": {"path": str(full_input.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(full_input), "records": 39393},
            "stage1_sample": {"path": str(sample.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(sample), "records": 114, "strata": 38},
            "sampler": {"path": str(sampler.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(sampler)},
            "prompt": {"path": str(prompt.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(prompt)},
            "response_schema": {"path": str(schema.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(schema)},
            "batch_size": 4,
            "expected_batches_per_run": 29,
            "temperature": 0.0,
            "seed": 20260823,
            "workers": 1,
            "request_delay_seconds": 10,
        },
        "stage1_gate": {
            "independent_runs": 2,
            "required": {
                "schema_success_each_run": 114,
                "headline_count_match_each_run": 114,
                "headline_id_and_order_match_each_run": 114,
                "evidence_exact_substring_each_run": 114,
                "btc_relevance_exact_agreement_min": 108,
                "event_type_exact_agreement_min": 103,
                "direction_exact_agreement_min": 103,
                "expected_horizon_exact_agreement_min": 97,
                "affected_assets_mean_jaccard_min": 0.9,
                "severity_mean_absolute_difference_max": 0.05,
                "reported_surprise_mean_absolute_difference_max": 0.05,
                "confidence_mean_absolute_difference_max": 0.05,
                "continuous_field_max_absolute_difference_max": 0.25,
            },
            "decision": "all requirements must pass before full-corpus extraction",
        },
        "stage2_only_if_stage1_passes": {
            "scope": "one full extraction over 39393 articles; no outcome join, predictive test, threshold selection, backtest, or Tech overlay",
            "required": {"schema_success": 39393, "headline_id_match": 39393, "evidence_exact_substring": 39393},
        },
        "prohibited": [
            "changing prompt, schema, model digest, sample, batch size, or gate thresholds after Stage 1 begins",
            "joining market outcomes before the full extraction artifact is complete and frozen",
            "creating action, position size, or Tech overlay fields in the extractor",
            "running more than one LLM worker",
            "continuing compute at NVIDIA GPU temperature 75 C or above",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps({"output": str(OUTPUT), "sha256": sha256(OUTPUT), "model_digest": model["digest"]}, indent=2))


if __name__ == "__main__":
    main()
