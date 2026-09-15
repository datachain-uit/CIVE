"""Freeze HYB-007 before prospective collection begins."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "paper/input/results/hybrid/hyb007_prospective_risk_attenuation_predeclared.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def item(relative: str) -> dict:
    path = ROOT / relative
    return {"path": relative.replace("\\", "/"), "sha256": digest(path)}


def main() -> None:
    if OUTPUT.exists():
        raise SystemExit(f"Refusing to overwrite frozen predeclaration: {OUTPUT}")
    payload = {
        "schema_version": 1,
        "experiment_id": "HYB-007",
        "status": "FROZEN_BEFORE_PROSPECTIVE_COLLECTION_NO_OUTCOME_ACCESS",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "research_role": "Prospective shadow Tech+LLM risk attenuation; conditional incremental value, not standalone alpha or live evidence.",
        "sequence_prerequisite": {
            "llm_only_eth_sample_audit": "PASS before target join in LLM-072",
            "llm_only_eth_transfer_diagnostic": "FAIL on 699 OOS predictions; 0/5 positive event-vs-generic MSE folds",
            "llm_only_branch": "closed through v21 before HYB-007 freeze",
        },
        "frozen_files": {
            "protocol": item("paper/working/protocols/Tech_LLM_Prospective_Risk_Attenuation_Protocol_HYB007.md"),
            "collector": item("tools/llm/collect_hyb007_prospective_news.py"),
            "collector_test": item("tools/llm/test_collect_hyb007_prospective_news.py"),
            "v3_9_stage1_contract": item("paper/input/results/llm/v3/llm_event_extractor_v3_9_stage1_predeclared.json"),
            "v3_9_full_gate": item("paper/input/results/llm/v3/llm_event_extractor_v3_9_full_gate.json"),
            "prompt": item("tools/llm/prompts/llm_event_extractor_v3_2.txt"),
            "schema": item("tools/llm/schemas/llm_event_extraction_batch_v3_2.schema.json"),
            "postprocessor": item("tools/llm/score_llm_event_extractor_v3_9.py"),
        },
        "source_registry": {"cointelegraph": "https://cointelegraph.com/rss"},
        "candidate": {
            "model": "ministral-3:8b",
            "digest": "1922accd5827ebe6829e536369195db25eaf664528dc66206d646ea3bb386b71",
            "quantization": "Q4_K_M",
            "temperature": 0.0,
            "seed": 20260823,
            "batch_size": 4,
            "workers": 1,
        },
        "sample_gate": {
            "independent_clusters_min": 30,
            "calendar_span_days_min": 90,
            "clusters_each_chronological_third_min": 8,
            "direct_asset_clusters_min": 15,
            "assets_with_at_least_five_clusters_min": 2,
            "collector_gap_hours_max_without_documented_incident": 48,
            "outcome_access_before_pass": "prohibited",
        },
        "treatment": {
            "authority": "multiply current Tech exposure magnitude by 0.5; never select, open, reverse or extend a Tech position",
            "duration_4h_bars": 3,
            "negative_only": True,
            "severity_min": 0.70,
            "confidence_min": 0.80,
            "event_types": ["exchange_security", "fraud_legal", "network_protocol", "liquidation_leverage"],
        },
        "primary_estimand": "paired mean net return T1 minus T0 over union of prospective intervention windows",
        "placebos": ["delayed_24h", "supportive_sign", "metadata_hash"],
        "prohibited": [
            "backfilling any URL present at collector initialization",
            "reading forward return, PnL, MDD or adverse excursion before effective-sample PASS",
            "changing source, alias, threshold, horizon, event type, placebo or pass rule after freeze",
            "using HYB-001 through HYB-006 outcomes to tune HYB-007",
            "calling shadow evidence live trading evidence",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps({"output": str(OUTPUT), "sha256": digest(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

