"""Freeze Stage C predeclaration for HYB-003 v3.1.

This script hashes all upstream artifacts and writes a single machine-readable
predeclaration that locks:
  - all feature names for T1 and T3
  - the counterfactual net-action-value target
  - the regularized linear learner specification
  - the three expanding time-based folds with embargo
  - registered round-trip cost components and the uncertainty deadband
  - the three placebo definitions
  - the exact evaluation outcomes/gates required for PASS

Nothing in this script reads or fits any outcome data.  Running it is
the last authorised action before Stage D (development evaluation).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_atomic(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return sha256(path)


# ---------------------------------------------------------------------------
# frozen design constants (must not change after this script runs)
# ---------------------------------------------------------------------------

# ---- T1 features (Tech-state only) ----------------------------------------
T1_FEATURES = [
    "asset_identity_fold_encoded",      # OHE from training fold only
    "trade_age_bars",                   # bars since Tech-Control entry
    "return_from_entry",                # (close - entry_price) / entry_price
    "dist_to_stop_over_atr",            # (price - shadow_stop) / ATR
    "atr_over_price",                   # normalised volatility
    "realized_range_4h",                # high-low over prior 4h bar
    "realized_range_24h",               # high-low over prior 24h
    "return_4h_lag1",                   # close return, 1-bar lag
    "return_12h_lag1",                  # close return, 12h lag
    "return_24h_lag1",                  # close return, 24h lag
    "funding_current",                  # current 8h funding rate
    "funding_mean_24h",                 # mean funding, past 24h
    "tech_rank_score",                  # frozen momentum rank if PIT-materializable
]

# ---- Additional T3 text-state features (on top of T1) ----------------------
T3_TEXT_FEATURES = [
    "adverse_mass",                     # weighted adverse pressure sum
    "supportive_mass",                  # weighted supportive pressure sum
    "adverse_h4_mass",                  # adverse mass projected to 4h horizon
    "supportive_h4_mass",               # supportive mass projected to 4h horizon
    "applicable_headline_count",        # direct_held + crypto_systemic count
    "adverse_headline_count",
    "supportive_headline_count",
    "source_domain_count",
    "novel_signature_count",            # distinct (scope|pressure|mechanism|evidence) not seen before bar
    "text_available_this_bar",          # boolean: any new text in this 4h window
    "dominant_stage_encoded",           # OHE of dominant event stage from training fold
    "dominant_mechanism_encoded",       # OHE of dominant mechanism from training fold
]

# ---- Registered T3-only interactions (must not be added post-evaluation) ---
T3_INTERACTIONS = [
    "adverse_mass * dist_to_stop_over_atr",
    "supportive_mass * dist_to_stop_over_atr",
    "novel_signature_count * trade_age_bars",
    "dominant_stage_encoded * realized_range_24h",
    "adverse_h4_mass * (action horizon == 4h indicator)",
    "asset_scope_direct * asset_identity_fold_encoded",
]

# ---- Target definition -----------------------------------------------------
TARGET = {
    "name": "net_action_value",
    "definition": (
        "Counterfactual net PnL of exposure 0.5 minus exposure 1.0 "
        "from current 4h bar open to next 4h open or earlier shadow exit, "
        "after adverse execution, fees and funding. "
        "Already materialized in panel rows['target']['net_action_value']."
    ),
    "units": "fraction of notional",
    "label_source": "paper/input/results/hybrid/tech_llm_conditional_state_fusion_v3_panel.json",
    "grouping": "shadow_trade cluster (trade_id field)",
}

# ---- Learner specification --------------------------------------------------
LEARNER = {
    "family": "Ridge regression (regularized linear)",
    "implementation": "sklearn.linear_model.Ridge",
    "regularization_search": "nested 3-fold CV inside each expanding training window",
    "alpha_grid": [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0],
    "standardization": "StandardScaler fit on training window only",
    "capacity_rule": (
        "T1 and T3 use the same alpha grid, CV budget and training window. "
        "T3 must not have a larger regularization budget than T1."
    ),
    "inference": "cluster-bootstrap with 10000 draws; cluster = trade_id",
    "seed": 20260911,
}

# ---- Temporal folds with embargo -------------------------------------------
# Three expanding chronological folds.
# The embargo is at least max_target_horizon (72h) + 1 bar (4h) = 76h.
FOLDS = [
    {
        "fold_id": 1,
        "train_end_iso": "2024-03-31T23:59:59+00:00",
        "eval_start_iso": "2024-04-04T04:00:00+00:00",   # + 76h embargo
        "eval_end_iso":   "2024-08-31T23:59:59+00:00",
    },
    {
        "fold_id": 2,
        "train_end_iso": "2024-08-31T23:59:59+00:00",
        "eval_start_iso": "2024-09-04T04:00:00+00:00",
        "eval_end_iso":   "2024-12-31T23:59:59+00:00",
    },
    {
        "fold_id": 3,
        "train_end_iso": "2024-12-31T23:59:59+00:00",
        "eval_start_iso": "2025-01-04T04:00:00+00:00",
        "eval_end_iso":   "2025-08-28T23:59:59+00:00",
    },
]

# ---- Registered cost components (must match panel execution semantics) ------
COST_CONTRACT = {
    "round_trip_fee_fraction": "2 * taker_fee as recorded in panel overlay_cost",
    "adverse_execution_slippage": "included in panel overlay_cost per row",
    "funding_portion": "included in panel overlay_cost per row",
    "uncertainty_deadband_rule": (
        "Take action w=0.5 only when the ridge estimate of net_action_value "
        "exceeds overlay_cost for that row plus one cluster-robust standard error "
        "estimated from the training fold. Otherwise hold w=1.0 (no-action default)."
    ),
    "note": "overlay_cost is already materialized; no post-hoc cost adjustment is permitted.",
}

# ---- Placebo definitions ----------------------------------------------------
PLACEBOS = [
    {
        "name": "timestamp_shuffled_text",
        "description": (
            "Shuffle decision-row timestamps within each fold, keeping the "
            "text-state vector fixed, to destroy the causal signal while "
            "preserving the marginal feature distribution."
        ),
        "expectation": "T3 must beat this placebo for the text signal to be non-spurious.",
    },
    {
        "name": "metadata_only_text",
        "description": (
            "Replace all text-derived features with only headline count and "
            "source domain count; set all mass/pressure/mechanism/stage fields "
            "to zero. This tests whether raw volume rather than content drives any result."
        ),
        "expectation": "T3 must beat this placebo to claim content-level signal.",
    },
    {
        "name": "delayed_text_24h",
        "description": (
            "Shift every text record's available_at timestamp forward by exactly "
            "24h before aggregation; this makes the state causally invalid "
            "but preserves the distribution of content. "
            "Represents a strict PIT failure scenario."
        ),
        "expectation": "T3 must beat this placebo to confirm the PIT advantage of causally available text.",
    },
]

# ---- Development PASS criteria (all six must hold simultaneously) -----------
PASS_CRITERIA = [
    "lower bound of 95% cluster-bootstrap CI for T3-T1 paired net utility > 0",
    "lower bound of 95% cluster-bootstrap CI for T3-T0 paired net portfolio utility > 0",
    "T3 net contrast positive in at least 2 of 3 chronological folds (both T3-T1 and T3-T0)",
    "T3 beats all three placebos on paired mean net utility at the same eligible timestamps",
    "T3 portfolio intrabar MDD <= T0 intrabar MDD under the one frozen MDD definition below",
    "effective independent trade clusters >= minimum set in Stage B power audit",
]

MDD_DEFINITION = (
    "Maximum drop from equity peak to trough within any shadow trade window, "
    "measured at 4h close marks, aggregated across the full evaluation period. "
    "This definition is frozen here and must not change after Stage C."
)

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Produce the Stage C freeze predeclaration for HYB-003 v3.1."
    )
    parser.add_argument("--panel",        type=Path, required=True, help="tech_llm_conditional_state_fusion_v3_panel.json")
    parser.add_argument("--state",        type=Path, required=True, help="tech_llm_conditional_state_v3_1.json")
    parser.add_argument("--stage-b-pred", type=Path, required=True, help="tech_llm_conditional_state_stage_b_v3_1_predeclared.json")
    parser.add_argument("--stage-b-audit",type=Path, required=True, help="tech_llm_conditional_state_stage_b_power_audit_v3_1.json")
    parser.add_argument("--extraction",   type=Path, required=True, help="hyb003_text_state_full_v3_1/extraction.json")
    parser.add_argument("--full-gate",    type=Path, required=True, help="hyb003_text_state_full_v3_1/gate.json")
    parser.add_argument("--output",       type=Path, required=True, help="destination predeclaration JSON")
    args = parser.parse_args()

    # Verify Stage B passed before proceeding
    stage_b_audit = json.loads(args.stage_b_audit.read_text(encoding="utf-8"))
    if stage_b_audit.get("status") != "stage-b-power-pass-freeze-authorized" or not stage_b_audit.get("passed"):
        raise ValueError("Stage B power audit has not passed — Stage C freeze is not authorised.")

    # Verify full extraction gate passed
    full_gate = json.loads(args.full_gate.read_text(encoding="utf-8"))
    if not full_gate.get("passed"):
        raise ValueError("Full extraction gate has not passed.")

    predeclaration = {
        "schema_version": "hyb003-stage-c-predeclaration-v3.1",
        "experiment_id": "HYB-003",
        "stage": "C_freeze",
        "status": "frozen-before-any-model-fit",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "research_role": (
            "This predeclaration locks the full experimental design. "
            "No T1/T2/T3 fitting, metric reading or action mapping is permitted "
            "before this file is committed and hashed. Any deviation constitutes a "
            "protocol violation and the affected results must not be reported as development."
        ),
        "upstream_artifacts": {
            "panel": {
                "path": str(args.panel),
                "sha256": sha256(args.panel),
            },
            "text_state": {
                "path": str(args.state),
                "sha256": sha256(args.state),
            },
            "stage_b_predeclaration": {
                "path": str(args.stage_b_pred),
                "sha256": sha256(args.stage_b_pred),
            },
            "stage_b_power_audit": {
                "path": str(args.stage_b_audit),
                "sha256": sha256(args.stage_b_audit),
            },
            "full_extraction": {
                "path": str(args.extraction),
                "sha256": sha256(args.extraction),
            },
            "full_extraction_gate": {
                "path": str(args.full_gate),
                "sha256": sha256(args.full_gate),
            },
        },
        "arms": {
            "T0": "Frozen Tech-Control execution — no learned overlay.",
            "T1": "Tech-state-only regularized linear model.",
            "T2": "Text-state-only diagnostic arm — not primary comparator.",
            "T3": "Tech-state + causal text-state regularized linear model with registered interactions.",
        },
        "primary_contrast": "T3 minus T1 paired mean net utility at identical eligible timestamps",
        "system_contrast":  "T3 minus T0 net portfolio performance under identical execution contract",
        "target": TARGET,
        "t1_features": T1_FEATURES,
        "t3_additional_text_features": T3_TEXT_FEATURES,
        "t3_registered_interactions": T3_INTERACTIONS,
        "learner": LEARNER,
        "folds": FOLDS,
        "cost_contract": COST_CONTRACT,
        "placebos": PLACEBOS,
        "mdd_definition": MDD_DEFINITION,
        "development_pass_criteria": PASS_CRITERIA,
        "prohibited_actions": [
            "Adding, removing or renaming features after reading any Stage D metric",
            "Adding interaction terms after reading any Stage D metric",
            "Changing fold boundaries after this file is written",
            "Adjusting the deadband rule after reading any outcome",
            "Reporting Stage D results as validation, holdout or live evidence",
            "Selecting placebos after reading any Stage D metric",
            "Giving T3 a larger tuning budget than T1",
        ],
        "stage_b_summary": {
            "panel_trade_clusters": stage_b_audit["counts"]["panel_trade_clusters"],
            "new_text_trade_clusters": stage_b_audit["counts"]["new_text_trade_clusters"],
            "active_applicable_trade_clusters": stage_b_audit["counts"]["active_applicable_trade_clusters"],
            "new_text_decisions": stage_b_audit["counts"]["new_text_decisions"],
            "all_decision_mde": stage_b_audit["planning_diagnostic"]["all_decision_mde_80pct_two_sided_5pct"],
            "applicable_text_mde": stage_b_audit["planning_diagnostic"]["applicable_text_mde_80pct_two_sided_5pct"],
            "median_overlay_cost": stage_b_audit["planning_diagnostic"]["median_one_bar_overlay_cost"],
        },
    }

    out_hash = write_atomic(args.output, predeclaration)
    print(json.dumps({"output": str(args.output), "sha256": out_hash, "status": "stage-c-frozen"}, indent=2))


if __name__ == "__main__":
    main()
