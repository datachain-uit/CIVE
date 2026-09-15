"""Audit the frozen HYB-003 Stage-D v3.1 implementation contract.

This script never fits a model.  It records why the existing v3.1 Stage-D
artifact cannot be treated as an evaluation of its frozen Stage-C contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--predeclaration",
        type=Path,
        default=root / "paper/input/results/hybrid/hyb003_stage_c_predeclared_v3_1.json",
    )
    parser.add_argument(
        "--panel",
        type=Path,
        default=root / "paper/input/results/hybrid/tech_llm_conditional_state_fusion_v3_panel.json",
    )
    parser.add_argument(
        "--stage-d",
        type=Path,
        default=root / "paper/input/results/hybrid/hyb003_stage_d_development_v3_1.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "paper/input/results/hybrid/hyb003_stage_d_v3_1_protocol_deviation_audit.json",
    )
    args = parser.parse_args()

    pre = load(args.predeclaration)
    panel = load(args.panel)
    panel_features = sorted(panel["rows"][0]["features"])

    deviations = [
        {
            "id": "feature_contract_not_implemented",
            "detail": (
                "The evaluator omits frozen asset_identity_fold_encoded and "
                "tech_rank_score, maps realized/funding features to different "
                "materialized quantities, and does not document those mappings."
            ),
        },
        {
            "id": "interaction_contract_not_implemented",
            "detail": (
                "The evaluator omits dominant_stage*range and direct_scope*asset, "
                "changes the registered 4h-horizon interaction into a distance-to-stop "
                "condition, and adds adverse/supportive*range interactions."
            ),
        },
        {
            "id": "net_target_cost_counted_again",
            "detail": (
                "net_action_value already includes overlay execution cost, fees and "
                "funding, but the action rule adds overlay_cost again to the threshold."
            ),
        },
        {
            "id": "half_exposure_effect_scaled_twice",
            "detail": (
                "The panel target is already the PnL difference produced by reducing "
                "the frozen position by one half; the evaluator multiplies it by 0.5 again."
            ),
        },
        {
            "id": "primary_contrast_not_paired",
            "detail": (
                "The registered T3-T1 estimand is paired by row, but v3.1 subtracts two "
                "arm means and reuses the T3-vs-zero confidence interval."
            ),
        },
    ]
    payload = {
        "schema_version": "hyb003-stage-d-v3.1-protocol-deviation-audit-v1",
        "experiment_id": "HYB-003",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "status": "PROTOCOL_DEVIATION_RESULT_NOT_REPORTABLE_AS_FROZEN_STAGE_D",
        "outcomes_consulted": True,
        "research_role": (
            "Implementation audit after v3.1 development outcomes were observed. "
            "It invalidates the frozen-contract interpretation; it is not a new result."
        ),
        "frozen_contract": {
            "t1_features": pre["t1_features"],
            "t3_additional_text_features": pre["t3_additional_text_features"],
            "t3_registered_interactions": pre["t3_registered_interactions"],
        },
        "materialized_panel_feature_keys": panel_features,
        "deviations": deviations,
        "decision": {
            "v3_1_performance_claim_withdrawn": True,
            "stage_e_authorized": False,
            "reason": (
                "The implementation differs materially from the frozen contract. "
                "Any corrected evaluation is post-outcome remediation and remains exploratory."
            ),
        },
        "inputs": {
            "predeclaration": {"path": str(args.predeclaration), "sha256": sha256(args.predeclaration)},
            "panel": {"path": str(args.panel), "sha256": sha256(args.panel)},
            "stage_d_v3_1": {"path": str(args.stage_d), "sha256": sha256(args.stage_d)},
            "auditor": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__))},
        },
    }
    write_atomic(args.output, payload)
    print(json.dumps({"output": str(args.output), "status": payload["status"]}, indent=2))


if __name__ == "__main__":
    main()
