"""Freeze v11 evaluation after coverage-only audit and before model metrics."""
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path


FOLDS = [
    {"fold": 1, "train_end": "2023-06-30T23:59:59+00:00", "valid_start": "2023-07-01T00:00:00+00:00", "valid_end": "2023-12-31T23:59:59+00:00"},
    {"fold": 2, "train_end": "2023-12-31T23:59:59+00:00", "valid_start": "2024-01-01T00:00:00+00:00", "valid_end": "2024-06-30T23:59:59+00:00"},
    {"fold": 3, "train_end": "2024-06-30T23:59:59+00:00", "valid_start": "2024-07-01T00:00:00+00:00", "valid_end": "2024-12-31T23:59:59+00:00"},
]


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def item(path): return {"path": path, "sha256": digest(path)}


def main():
    panel = Path("paper/input/results/llm/v11/open_fed_policy_panel_v11.json")
    audit = json.loads(Path("paper/input/results/llm/v11/open_fed_policy_panel_v11_audit.json").read_text(encoding="utf-8"))
    rows = json.loads(panel.read_text(encoding="utf-8"))["records"]
    folds = []
    for fold in FOLDS:
        train = sum(row["decision_at"] <= fold["train_end"] for row in rows)
        valid = sum(fold["valid_start"] <= row["decision_at"] <= fold["valid_end"] for row in rows)
        if not train or not valid: raise ValueError("empty fold")
        folds.append({**fold, "train_records": train, "valid_records": valid})
    payload = {
        "schema_version": "open-fed-policy-evaluation-predeclaration-v11", "predeclared_at": datetime.now(timezone.utc).isoformat(),
        "status": "FROZEN_AFTER_COVERAGE_ONLY_BEFORE_METRICS", "development_only": True, "strict_point_in_time": False,
        "sources": {"panel": {"path": str(panel), "sha256": digest(panel)}, "panel_audit": item("paper/input/results/llm/v11/open_fed_policy_panel_v11_audit.json")},
        "code": {"evaluator": item("tools/llm/evaluate_open_fed_policy_v11.py"), "tests": item("tools/llm/test_evaluate_open_fed_policy_v11.py")},
        "coverage_only_audit": {"labeled_buckets": audit["labeled_buckets"], "target_distribution_consulted": False},
        "arms": ["training-fold target mean prior", "generic LLM sentiment", "event-conditioned LLM policy representation"],
        "model": {"family": "linear-ridge", "alpha": 10.0, "standardization": "train fold only", "hyperparameter_tuning": False},
        "folds": folds, "bootstrap": {"iterations": 5000, "block_length_records": 5, "seed": 20260905},
        "gate": {"minimum_fold_wins": 2, "requires": ["event MSE improvement CI lower > 0 versus prior", "event MSE improvement CI lower > 0 versus generic", "event Pearson CI lower > 0", "event wins at least 2/3 folds versus both comparators"]},
        "on_fail": "freeze negative result and stop before threshold/action/backtest/sealed holdout",
    }
    output = Path("paper/input/results/llm/v11/open_fed_policy_evaluation_v11_predeclared.json"); output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8"); print(json.dumps({"output": str(output), "sha256": digest(output), "folds": folds}, indent=2))


if __name__ == "__main__": main()
