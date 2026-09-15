"""Build the machine-readable EXT-002 audit from frozen project artifacts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HYBRID = ROOT / "paper/input/results/hybrid"
OUT = HYBRID / "ext002_external_tech_llm_baseline_comparison.json"


def load(name):
    path = HYBRID / name
    return json.loads(path.read_text(encoding="utf-8")), path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def src(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}


def main():
    h4, p4 = load("hyb004_bennett_adaptive_eth_transfer_v1_1_remediation.json")
    h6, p6 = load("hyb006_rank_pair_reallocation_evaluation.json")
    h7, p7 = load("hyb007_historical_risk_attenuation_evaluation.json")
    h8, p8 = load("hyb008_conditional_downside_evaluation.json")
    h1, p1 = load("tech_llm_conditional_overlay_v1_development.json")
    h2, p2 = load("tech_llm_intratrade_shock_shield_v2_development.json")
    bennett = {
        "experiment": "HYB-004 v1.1", "role": "external_method_transfer",
        "source_method": "Bennett et al. (2024) adaptive recent-MSFE component",
        "asset_horizon": "ETHUSDT, 24h", "oos_units": len(h4["records"]),
        "predictive_metric": "MSE", "tech_value": h4["overall"]["tech"]["mse"],
        "hybrid_value": h4["overall"]["fusion"]["mse"],
        "improvement_positive_is_better": h4["fusion_minus_tech"]["delta_mse"],
        "improvement_95_ci": h4["fusion_minus_tech"]["delta_mse_95_ci"],
        "mean_net_delta": h4["fusion_minus_tech"]["mean_daily_net_delta"],
        "mean_net_delta_95_ci": h4["fusion_minus_tech"]["mean_daily_net_delta_95_ci"],
        "positive_or_winning_folds": h4["fusion_minus_tech"]["mse_fold_wins"], "folds": 5,
        "tech_total_return": h4["overall"]["strategy_tech"]["compounded_net_return"],
        "hybrid_total_return": h4["overall"]["strategy_fusion"]["compounded_net_return"],
        "tech_max_drawdown": h4["overall"]["strategy_tech"]["max_drawdown"],
        "hybrid_max_drawdown": h4["overall"]["strategy_fusion"]["max_drawdown"],
        "status": h4["status"], "directly_comparable_to_tech": True, "source": src(p4),
    }
    evidence = [bennett,
        {"experiment":"HYB-001","role":"internal_conditional_overlay","asset_horizon":"Frozen Tech trade opportunities","oos_units":h1["results"]["tech_llm"]["n"],"mean_net_delta":h1["results"]["tech_llm"]["mean_paired_net_difference"],"mean_net_delta_95_ci":h1["results"]["tech_llm"]["paired_net_difference_ci95"],"positive_or_winning_folds":h1["results"]["tech_llm"]["positive_folds"],"folds":3,"tech_total_return":h1["results"]["tech_only"]["compounded_net_return"],"hybrid_total_return":h1["results"]["tech_llm"]["compounded_net_return"],"tech_max_drawdown":h1["results"]["tech_only"]["closed_trade_max_drawdown"],"hybrid_max_drawdown":h1["results"]["tech_llm"]["closed_trade_max_drawdown"],"status":h1["status"],"directly_comparable_to_tech":True,"source":src(p1)},
        {"experiment":"HYB-002","role":"internal_intratrade_shield","asset_horizon":"Frozen Tech intratrade windows","oos_units":h2["arms"]["primary"]["trade_clusters"],"mean_net_delta":h2["arms"]["primary"]["mean_paired_net_difference"],"mean_net_delta_95_ci":h2["arms"]["primary"]["cluster_bootstrap_ci95"],"positive_or_winning_folds":sum(x>0 for x in h2["arms"]["primary"]["fold_mean_net_differences"]),"folds":3,"status":h2["status"],"directly_comparable_to_tech":True,"source":src(p2)},
        {"experiment":"HYB-006","role":"internal_rank_pair_reallocation","asset_horizon":"Multi-asset daily","oos_units":1081,"mean_net_delta":h6["primary_contrast"]["mean_daily_net_delta"],"mean_net_delta_95_ci":h6["primary_contrast"]["block_bootstrap_95_ci"],"positive_or_winning_folds":h6["primary_contrast"]["positive_folds"],"folds":5,"tech_total_return":h6["arms"]["tech"]["total_return"],"hybrid_total_return":h6["arms"]["primary"]["total_return"],"tech_max_drawdown":h6["arms"]["tech"]["max_drawdown"],"hybrid_max_drawdown":h6["arms"]["primary"]["max_drawdown"],"status":h6["status"],"directly_comparable_to_tech":False,"source":src(p6)},
        {"experiment":"HYB-007","role":"internal_historical_risk_attenuation","asset_horizon":"ETH/SOL, 4h intervention","oos_units":h7["arms"]["primary"]["clusters"],"mean_net_delta":h7["arms"]["primary"]["mean_net_delta"],"mean_net_delta_95_ci":h7["arms"]["primary"]["net_delta_bootstrap_95_ci"],"positive_or_winning_folds":h7["arms"]["primary"]["positive_folds"],"folds":5,"worst_bar_improvement":h7["arms"]["primary"]["mean_worst_bar_improvement"],"worst_bar_improvement_95_ci":h7["arms"]["primary"]["worst_bar_improvement_bootstrap_95_ci"],"tech_es10":h7["arms"]["primary"]["tech_cluster_es10"],"hybrid_es10":h7["arms"]["primary"]["llm_cluster_es10"],"status":h7["status"],"directly_comparable_to_tech":False,"source":src(p7)},
        {"experiment":"HYB-008","role":"internal_downside_information_gate","asset_horizon":"ETH/SOL selected event rows","oos_units":h8["oos_rows"],"predictive_metric":"Brier","tech_value":h8["arms"]["tech"]["brier"],"hybrid_value":h8["arms"]["event"]["brier"],"improvement_positive_is_better":h8["arms"]["tech"]["brier"]-h8["arms"]["event"]["brier"],"semantic_vs_generic_improvement":h8["primary_generic_minus_event_brier"],"semantic_vs_generic_95_ci":h8["primary_date_cluster_bootstrap_95_ci"],"positive_or_winning_folds":h8["positive_folds"],"folds":5,"status":h8["status"],"directly_comparable_to_tech":False,"source":src(p8)}]
    result = {
        "schema_version":1,"experiment_id":"EXT-002-external-tech-llm-baseline-transfer-audit",
        "built_at":datetime.now(timezone.utc).isoformat(),"research_role":"post-outcome development audit and evidence synthesis; not validation",
        "admissibility":[
            {"candidate":"Bennett et al. (2024)","admitted":True,"implementation":"HYB-004 v1.1","claim":"adaptive recent-MSFE component transfer; not replication"},
            {"candidate":"FinMem","admitted":False,"reason":"missing official input and embedding credential"},
            {"candidate":"FinAgent","admitted":False,"reason":"insufficient implementation/data for same-testbed end-to-end transfer"},
            {"candidate":"Jung and Lee (2026)","admitted":False,"reason":"three-day original horizon and incompatible agent contract"},
            {"candidate":"Kirtac and Germano (2024)","admitted":False,"reason":"LLM-only sentiment strategy, not a Tech+LLM fusion method"}],
        "same_context_external_baseline":bennett,"hybrid_evidence_map":evidence,
        "protocol_realism":{"project_common_strengths":["causal available_at","action delay","walk-forward OOS","fees/adverse execution","funding where applicable","frozen artifacts and hashes","stop rules"],"not_uniform_across_all_hybs":["effective-sample gate","placebos","intrabar risk materialization","same asset/horizon/comparator"],"sealed_or_live_evidence":False},
        "regime_coverage":{"chronological_fold_stability_available":True,"common_predeclared_bull_bear_volatility_regimes_available":False,"status":"MISSING_DO_NOT_CHERRY_PICK_POST_HOC_WINNING_PERIODS"},
        "conclusion":{"external_baselines_admitted":1,"external_baseline_passes_incremental_value_gate":0,"performance_claim":"No verified predictive or economic incremental value for the admitted external transfer.","risk_claim":"HYB-007 shows local tail attenuation, but economic non-inferiority fails and semantic causation is not verified.","protocol_claim":"The project supports stronger causal/audit discipline than naive backtests; this is not evidence of superior returns."}}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"output":str(OUT),"sha256":digest(OUT),"conclusion":result["conclusion"]},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
