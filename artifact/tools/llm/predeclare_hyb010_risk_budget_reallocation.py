"""Freeze HYB-010 assignments before evaluating the new policy."""
from __future__ import annotations

import hashlib
import json
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HYB009_ASSIGNMENTS = ROOT / "paper/input/results/hybrid/hyb009_model_substitution_sample_audit_v1_1.json"
TECH = ROOT / "results/technical_bybit_lifecycle_1x_candidate_hardened.json"
EVALUATOR = ROOT / "tools/llm/evaluate_hyb010_risk_budget_reallocation.py"
OUTPUT = ROOT / "paper/input/results/hybrid/hyb010_risk_budget_reallocation_predeclared.json"
SEED = 20260914


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    source = json.loads(HYB009_ASSIGNMENTS.read_text(encoding="utf-8"))
    downsize = source["assignments"]["cryptobert"]["primary"]
    keys = list(downsize)

    # HYB-009 used d = 1 - 0.5*q.  HYB-010 restores 0.25 exposure to
    # every opportunity, yielding 1.25 - 0.5*q in [0.75, 1.25].
    primary = {key: float(weight) + 0.25 for key, weight in downsize.items()}
    values = list(primary.values())
    shuffled_values = values.copy()
    random.Random(SEED).shuffle(shuffled_values)
    shuffled = dict(zip(keys, shuffled_values))
    mean_weight = statistics.fmean(values)

    payload = {
        "schema_version": 1,
        "experiment_id": "HYB-010-v1-cryptobert-risk-budget-reallocation",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "research_role": "post-outcome exploratory development; CryptoBERT was selected from the descriptive HYB-009 risk audit",
        "hypothesis": "CryptoBERT bearish percentile can reallocate exposure away from high-downside entries toward low-downside entries, preserving some tail-risk benefit while recovering or increasing return relative to Tech-Control.",
        "policy": {
            "bearish_percentile_recovery": "q = 2 * (1 - HYB009_downsize_weight)",
            "primary_weight": "1.25 - 0.5*q, algebraically HYB009_downsize_weight + 0.25",
            "bounds": [0.75, 1.25],
            "execution": "same frozen Tech entries, directions, exits, costs, funding and stop prices; exposure scales gross PnL and costs linearly",
        },
        "comparators": {
            "tech_control": "constant 1.0 exposure",
            "shuffled_reallocation": f"same primary weights permuted once with seed {SEED}",
            "constant_matched_budget": "constant exposure equal to the primary arm's feature-only mean weight",
        },
        "sample": {
            "n_opportunities": len(keys),
            "primary_mean_weight": mean_weight,
            "primary_min_weight": min(values),
            "primary_max_weight": max(values),
        },
        "gates": {
            "allocation_selectivity": "primary mean net delta and MDD must beat both shuffled and constant-matched-budget arms",
            "return_conversion": "compounded return > Tech; paired-net cluster-bootstrap CI95 lower > 0; at least 2/3 folds positive",
            "risk_preservation": "closed-trade MDD <= Tech, ES10 >= Tech and worst trade >= Tech",
            "strong_pass": "all allocation-selectivity, return-conversion and risk-preservation conditions pass",
        },
        "folds": [
            ["2022-09-13T00:00:00+00:00", "2023-09-01T00:00:00+00:00"],
            ["2023-09-01T00:00:00+00:00", "2024-09-01T00:00:00+00:00"],
            ["2024-09-01T00:00:00+00:00", "2025-08-29T00:00:00+00:00"],
        ],
        "assignments": {
            "tech_control": {key: 1.0 for key in keys},
            "cryptobert_reallocation": primary,
            "shuffled_reallocation": shuffled,
            "constant_matched_budget": {key: mean_weight for key in keys},
        },
        "sources": {
            "hyb009_assignments": {"path": str(HYB009_ASSIGNMENTS), "sha256": sha256(HYB009_ASSIGNMENTS)},
            "tech": {"path": str(TECH), "sha256": sha256(TECH)},
            "evaluator": {"path": str(EVALUATOR), "sha256": sha256(EVALUATOR)},
        },
        "prohibited": [
            "retuning the 0.25 offset or 0.75/1.25 bounds after evaluation",
            "calling this validation, sealed holdout or live evidence",
            "attributing a gain to LLM unless the primary arm also beats the same-budget placebos",
            "claiming intrabar drawdown from closed-trade MDD",
        ],
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "FROZEN", "sample": payload["sample"], "output": str(OUTPUT)}, indent=2))


if __name__ == "__main__":
    main()
