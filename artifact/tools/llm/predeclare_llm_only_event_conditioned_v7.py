"""Freeze the development-only LLM event-conditioned v7 gate."""
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


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build() -> dict:
    return {
        "schema_version": "llm-only-event-conditioned-predeclaration-v7",
        "experiment_id": "llm-only-event-conditioned-v7.0.1-development",
        "predeclared_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Post-v3-v6 development follow-up; LLM-only inputs; not sealed confirmation.",
        "prior_outcomes_consulted_before_design": True,
        "supersedes": "llm-only-event-conditioned-v7-development",
        "operational_correction": "Feature-name guard changed from substring matching to exact token matching after v7.0 aborted before model fit, prediction, metrics, or output artifacts.",
        "known_prior_results": ["v3.1.1 return FAIL", "v3.2 risk FAIL", "v4 transfer FAIL", "v5 full-text FAIL", "v6 contrastive FAIL"],
        "technical_or_market_features_allowed": False,
        "protocol": item("paper/working/protocols/LLM_Only_Event_Conditioned_Protocol_v7.md"),
        "code": {
            "evaluator": item("tools/llm/evaluate_llm_only_event_conditioned_v7.py"),
            "tests": item("tools/llm/test_evaluate_llm_only_event_conditioned_v7.py"),
        },
        "tests": {"status": "5 tests passed before outcome evaluation"},
        "sources": {
            "extraction_gate": item("paper/input/results/llm/v3/llm_event_extractor_v3_9_full_gate.json"),
            "extraction_input": item("paper/input/results/llm/v3/llm_event_extraction_inputs_v3_development.json"),
            "extraction": item("paper/input/results/llm/v3/llm_event_extractor_v3_9_full_development.json"),
            "target_panel": item("paper/input/results/llm/v3/llm_event_risk_target_panel_v3_development.json"),
        },
        "data_gate": {"required_dates": 1079, "required_extraction_records": 39393, "required_oos_records": 699},
        "target": {"field": "h24_return", "asset": "BTCUSDT", "execution_delay_hours": 4, "role": "single primary target"},
        "arms": {
            "prior": "training-fold target mean; diagnostic only",
            "sentiment": "generic LLM sentiment; direct comparator",
            "event": "LLM event-conditioned representation; single treatment",
        },
        "feature_contract": {
            "btc_relevance": ["direct", "systemic", "indirect", "none"],
            "event_types": ["macro_liquidity", "regulation", "etf_institutional_flow", "exchange_security", "liquidation_leverage", "network_protocol", "fraud_legal", "adoption_business", "market_commentary", "other"],
            "directions": ["positive", "negative", "mixed", "unclear"],
            "expected_horizons": ["4h", "12h", "24h", "72h", "unknown"],
            "relevance_weights": {"direct": 1.0, "systemic": 0.75, "indirect": 0.25, "none": 0.0},
            "prohibited": ["OHLCV", "lagged returns", "volatility", "volume", "funding", "breadth", "dispersion", "regime", "technical indicators", "deterministic text metadata"],
        },
        "model": {"family": "linear-ridge", "alpha": 10.0, "standardization": "training-fold mean/std only", "hyperparameter_tuning": False},
        "folds": [
            {"fold": 1, "train_end": "2023-09-11", "valid_start": "2023-09-15", "valid_end": "2024-01-31", "train_records": 365, "valid_records": 139},
            {"fold": 2, "train_end": "2024-01-31", "valid_start": "2024-02-04", "valid_end": "2024-06-21", "train_records": 507, "valid_records": 139},
            {"fold": 3, "train_end": "2024-06-21", "valid_start": "2024-06-25", "valid_end": "2024-11-10", "train_records": 649, "valid_records": 139},
            {"fold": 4, "train_end": "2024-11-10", "valid_start": "2024-11-14", "valid_end": "2025-04-01", "train_records": 791, "valid_records": 139},
            {"fold": 5, "train_end": "2025-04-01", "valid_start": "2025-04-05", "valid_end": "2025-08-27", "train_records": 933, "valid_records": 143},
        ],
        "bootstrap": {"method": "paired moving-block within fold", "iterations": 5000, "block_length_days": 7, "seed": 20260907, "confidence_level": 0.95},
        "gate": {
            "required_oos_records": 699,
            "minimum_fold_wins": 3,
            "all_required_checks": [
                "paired MSE(sentiment)-MSE(event) 95% CI lower bound > 0",
                "event prediction Pearson 95% CI lower bound > 0",
                "event MSE wins at least 3 of 5 folds",
                "699 OOS predictions and nonconstant event predictions",
            ],
        },
        "on_fail": "Freeze negative development result and stop before threshold, action mapping, backtest, or sealed holdout.",
        "on_pass": "Authorize only a separate LLM-only development backtest predeclaration.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build()
    write_json(args.output, payload)
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output)}, indent=2))


if __name__ == "__main__":
    main()
