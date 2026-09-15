"""Freeze the corrected historical HYB-007 before its own evaluation."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[2]
    protocol = root / "paper/working/protocols/Tech_LLM_Historical_Risk_Attenuation_Protocol_HYB007.md"
    v20 = root / "paper/input/results/llm/v20/llm_only_multicoin_short_panel_v20.json"
    tech = root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_daily_panel.json"
    audit = root / "tools/llm/audit_hyb007_historical_risk_attenuation.py"
    evaluate = root / "tools/llm/evaluate_hyb007_historical_risk_attenuation.py"
    payload = {
        "schema_version": 1,
        "experiment_id": "HYB-007",
        "status": "FROZEN_BEFORE_HYB007_EVALUATION",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "research_role": "historical exploratory development transfer; not prospective, validation, holdout or live evidence",
        "correction": {"reason": "The prior prospective design misread the user's historical-data request and was withdrawn before model or outcome access.", "withdrawn_predeclaration_sha256": "e1b6a846056043b1dbf19e8ca56723d697263a1b1b54df9044df7e8347db42de"},
        "researcher_outcomes_previously_seen": True,
        "hyb007_outcome_evaluated_before_freeze": False,
        "comparator": "HYB-006 predecessor Tech rank-pair selection, equal 0.5/0.5 weights",
        "treatment": "For a qualifying selected ETH/SOL warning, reduce that asset from 0.5 to 0.25 cash for three 4h bars.",
        "warning_rule": {"negative_fraction_min": 0.5, "severity_max_min": 0.7, "confidence_max_min": 0.8, "event_types": ["exchange_security", "fraud_legal", "network_protocol", "liquidation_leverage"]},
        "sample_gate": {"qualifying_buckets_min": 120, "independent_clusters_min": 60, "clusters_each_third_min": 15, "clusters_each_asset_min": 20, "coverage_days_min": 720},
        "evaluation": {"duration_4h_bars": 3, "cost_bps_per_one_way_turnover": 10, "bootstrap_clusters": 10000, "bootstrap_seed": 20260913, "folds": 5, "net_noninferiority_tolerance_per_cluster": -0.0005, "placebos": ["delayed_24h", "supportive_sign", "metadata_hash_matched"], "separate_verdicts": ["economic_increment", "risk_control_increment"]},
        "inputs": {"protocol": {"path": str(protocol), "sha256": sha(protocol)}, "v20_panel": {"path": str(v20), "sha256": sha(v20)}, "tech_assignments": {"path": str(tech), "sha256": sha(tech)}, "audit_script": {"path": str(audit), "sha256": sha(audit)}, "evaluation_script": {"path": str(evaluate), "sha256": sha(evaluate)}},
        "next_authorized_action": "Run outcome-free historical effective-sample audit only.",
    }
    out = root / "paper/input/results/hybrid/hyb007_historical_risk_attenuation_predeclared.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(out), "sha256": sha(out)}, indent=2))


if __name__ == "__main__":
    main()
