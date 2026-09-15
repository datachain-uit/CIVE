"""Freeze v8 folds and predictive gate after coverage-only panel audit."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def item(path: str) -> dict:
    return {"path": path, "sha256": sha256(Path(path))}


FOLD_BOUNDARIES = [
    {"fold": 1, "train_end": "2023-12-31T20:00:00+00:00", "valid_start": "2024-01-01T04:00:00+00:00", "valid_end": "2024-04-30T20:00:00+00:00"},
    {"fold": 2, "train_end": "2024-04-30T20:00:00+00:00", "valid_start": "2024-05-01T04:00:00+00:00", "valid_end": "2024-08-31T20:00:00+00:00"},
    {"fold": 3, "train_end": "2024-08-31T20:00:00+00:00", "valid_start": "2024-09-01T04:00:00+00:00", "valid_end": "2024-12-31T20:00:00+00:00"},
    {"fold": 4, "train_end": "2024-12-31T20:00:00+00:00", "valid_start": "2025-01-01T04:00:00+00:00", "valid_end": "2025-04-30T20:00:00+00:00"},
    {"fold": 5, "train_end": "2025-04-30T20:00:00+00:00", "valid_start": "2025-05-01T04:00:00+00:00", "valid_end": "2025-08-27T20:00:00+00:00"},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    panel = json.loads(args.panel.read_text(encoding="utf-8"))
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    records = panel["records"]
    decisions = [row["decision_at"] for row in records]
    folds = []
    for boundary in FOLD_BOUNDARIES:
        train_records = sum(value <= boundary["train_end"] for value in decisions)
        valid_records = sum(boundary["valid_start"] <= value <= boundary["valid_end"] for value in decisions)
        if not train_records or not valid_records:
            raise ValueError(f"empty fold {boundary['fold']}")
        folds.append({**boundary, "train_records": train_records, "valid_records": valid_records})
    required_oos = sum(fold["valid_records"] for fold in folds)
    payload = {
        "schema_version": "llm-only-event-response-predeclaration-v8",
        "experiment_id": "llm-only-short-horizon-event-response-v8-development",
        "predeclared_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Post-v7 development branch; publication-time four-hour response; not sealed confirmation.",
        "prior_v3_v7_outcomes_consulted": True,
        "v8_target_distribution_or_model_outcomes_consulted": False,
        "technical_or_market_features_allowed": False,
        "protocol": item("paper/working/protocols/LLM_Only_Short_Horizon_Event_Response_Protocol_v8.md"),
        "code": {
            "evaluator": item("tools/llm/evaluate_llm_only_event_response_v8.py"),
            "tests": item("tools/llm/test_evaluate_llm_only_event_response_v8.py"),
            "ridge_and_guard_dependency": item("tools/llm/evaluate_llm_only_event_conditioned_v7.py"),
        },
        "tests": {"status": "3 evaluator tests and 4 panel tests passed before predictive evaluation"},
        "sources": {
            "panel": {"path": str(args.panel), "sha256": sha256(args.panel)},
            "panel_audit": {"path": str(args.audit), "sha256": sha256(args.audit)},
            "panel_predeclaration": item("paper/input/results/llm/v8/llm_only_event_response_panel_v8_predeclared.json"),
        },
        "data_gate": {
            "required_panel_records": len(records),
            "required_eligible_events": audit["counts"]["eligible_events"],
            "required_oos_records": required_oos,
        },
        "target": {"field": "target_h4_return", "asset": "BTCUSDT", "horizon_hours": 4, "role": "single primary target"},
        "arms": {
            "prior": "training-fold target mean; diagnostic only",
            "sentiment": "generic LLM sentiment; direct comparator",
            "event": "LLM event-conditioned representation; single treatment",
        },
        "feature_contract": {
            "sentiment_feature_names": audit["sentiment_feature_names"],
            "event_feature_names": audit["event_feature_names"],
            "prohibited": ["OHLCV", "lagged returns", "volatility", "volume", "funding", "breadth", "regime", "technical indicators", "deterministic text metadata"],
        },
        "model": {"family": "linear-ridge", "alpha": 10.0, "standardization": "training-fold mean/std only", "hyperparameter_tuning": False},
        "folds": folds,
        "bootstrap": {"method": "paired moving-block within fold", "iterations": 5000, "block_length_records": 42, "seed": 20260908, "confidence_level": 0.95},
        "gate": {
            "required_oos_records": required_oos,
            "minimum_fold_wins": 3,
            "all_required_checks": [
                "paired MSE(sentiment)-MSE(event) 95% CI lower bound > 0",
                "event prediction Pearson 95% CI lower bound > 0",
                "event MSE wins at least 3 of 5 folds",
                "required OOS predictions and nonconstant event predictions",
            ],
        },
        "on_fail": "Freeze negative result and stop before threshold, action mapping, backtest, or sealed holdout.",
        "on_pass": "Authorize only a separate LLM-only development backtest predeclaration.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output), "folds": folds, "required_oos_records": required_oos}, indent=2))


if __name__ == "__main__":
    main()
