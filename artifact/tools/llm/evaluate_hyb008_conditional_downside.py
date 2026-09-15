"""Stage-A historical conditional downside information evaluation for HYB-008."""
from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from hyb008_conditional_downside_common import SYMBOLS, build_population, read, sha, write


def percentile(values, q):
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] if lo == hi else ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)


def feature_parts(row):
    tech = dict(row["tech"])
    metadata = {**tech, **{f"m::{k}": float(v) for k, v in row["metadata"].items()}}
    generic = {**tech, **{f"g::{k}": float(v) for k, v in row["generic"].items()}}
    semantic = {f"e::{k}": float(v) for k, v in row["event"].items() if k not in row["generic"]}
    return tech, metadata, generic, semantic


def fit_predict(train_dicts, train_y, test_dicts):
    vectorizer = DictVectorizer(sparse=False, sort=True)
    train_x = vectorizer.fit_transform(train_dicts)
    test_x = vectorizer.transform(test_dicts)
    model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, penalty="l2", solver="lbfgs", max_iter=2000))
    model.fit(train_x, train_y)
    return model.predict_proba(test_x)[:, 1]


def shifted_semantics(parts, shift=17):
    if not parts:
        return []
    shift %= len(parts)
    return parts[-shift:] + parts[:-shift] if shift else list(parts)


def cluster_bootstrap_ci(records, draws=10000, seed=20260914):
    grouped = defaultdict(list)
    for row in records:
        grouped[row["utc_date"]].append((row["label"] - row["p_generic"]) ** 2 - (row["label"] - row["p_event"]) ** 2)
    date_values = [sum(values) / len(values) for values in grouped.values()]
    rng = random.Random(seed)
    means = [sum(date_values[rng.randrange(len(date_values))] for _ in date_values) / len(date_values) for _ in range(draws)]
    return [percentile(means, 0.025), percentile(means, 0.975)]


def main():
    root = Path(__file__).resolve().parents[2]
    pre_path = root / "paper/input/results/hybrid/hyb008_conditional_downside_predeclared.json"
    audit_path = root / "paper/input/results/hybrid/hyb008_conditional_downside_sample_audit.json"
    panel_path = root / "paper/input/results/llm/v20/llm_only_multicoin_short_panel_v20.json"
    tech_path = root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_daily_panel.json"
    bar_dir = root / "results/bybit_lifecycle_4h"
    pre, audit, panel, tech = read(pre_path), read(audit_path), read(panel_path), read(tech_path)
    if audit.get("status") != "PASS_STAGE_A_AUTHORIZED" or audit.get("passed") is not True:
        raise RuntimeError("HYB-008 sample gate did not authorize Stage A")
    if audit["predeclaration"]["sha256"] != sha(pre_path):
        raise RuntimeError("predeclaration changed after sample audit")
    expected = {item["path"]: item["sha256"] for item in pre["inputs"]["scripts"]}
    current_script = Path(__file__).resolve()
    if expected[str(current_script)] != sha(current_script):
        raise RuntimeError("evaluation script changed after freeze")
    bars = {s: read(bar_dir / f"{s}_1660348800000_1786492800000.json") for s in SYMBOLS}
    rows = build_population(panel, tech, bars, include_target=True)
    if len(rows) != audit["sample"]["rows"]:
        raise RuntimeError("evaluated population differs from audited population")
    dates = sorted({r["utc_date"] for r in rows})
    initial = math.ceil(len(dates) * 0.30)
    remaining = dates[initial:]
    predictions, fold_metrics, all_two_classes = [], [], True
    for fold in range(5):
        test_dates = set(remaining[fold * len(remaining) // 5:(fold + 1) * len(remaining) // 5])
        test_start = min(test_dates)
        train_rows = [r for r in rows if r["utc_date"] < test_start]
        test_rows = [r for r in rows if r["utc_date"] in test_dates]
        thresholds = {}
        for symbol in SYMBOLS:
            values = sorted(r["target_h4_return"] for r in train_rows if r["symbol"] == symbol)
            thresholds[symbol] = percentile(values, 0.10)
        train_y = np.array([int(r["target_h4_return"] <= thresholds[r["symbol"]]) for r in train_rows])
        test_y = np.array([int(r["target_h4_return"] <= thresholds[r["symbol"]]) for r in test_rows])
        all_two_classes &= len(set(train_y.tolist())) == 2 and len(set(test_y.tolist())) == 2
        train_parts = [feature_parts(r) for r in train_rows]
        test_parts = [feature_parts(r) for r in test_rows]
        train_sem_shift = shifted_semantics([x[3] for x in train_parts], 17)
        test_sem_shift = shifted_semantics([x[3] for x in test_parts], 17)
        arm_train = {
            "tech": [x[0] for x in train_parts],
            "metadata": [x[1] for x in train_parts],
            "generic": [x[2] for x in train_parts],
            "event": [{**x[2], **x[3]} for x in train_parts],
            "permuted": [{**x[2], **s} for x, s in zip(train_parts, train_sem_shift, strict=True)],
        }
        arm_test = {
            "tech": [x[0] for x in test_parts],
            "metadata": [x[1] for x in test_parts],
            "generic": [x[2] for x in test_parts],
            "event": [{**x[2], **x[3]} for x in test_parts],
            "permuted": [{**x[2], **s} for x, s in zip(test_parts, test_sem_shift, strict=True)],
        }
        probs = {name: fit_predict(arm_train[name], train_y, arm_test[name]) for name in arm_train}
        metrics = {name: {"brier": brier_score_loss(test_y, p), "auc": roc_auc_score(test_y, p), "log_loss": log_loss(test_y, p)} for name, p in probs.items()}
        fold_metrics.append({"fold": fold + 1, "train_rows": len(train_rows), "test_rows": len(test_rows), "test_dates": [min(test_dates), max(test_dates)], "tail_thresholds": thresholds, "positive_rate": float(test_y.mean()), "arms": metrics, "generic_minus_event_brier": metrics["generic"]["brier"] - metrics["event"]["brier"]})
        for i, row in enumerate(test_rows):
            predictions.append({"fold": fold + 1, "symbol": row["symbol"], "decision_at": row["decision_at"], "utc_date": row["utc_date"], "target_h4_return": row["target_h4_return"], "tail_threshold": thresholds[row["symbol"]], "label": int(test_y[i]), **{f"p_{name}": float(values[i]) for name, values in probs.items()}})
    labels = np.array([r["label"] for r in predictions])
    arm_summary = {}
    for name in ("tech", "metadata", "generic", "event", "permuted"):
        p = np.array([r[f"p_{name}"] for r in predictions])
        arm_summary[name] = {"brier": brier_score_loss(labels, p), "auc": roc_auc_score(labels, p), "log_loss": log_loss(labels, p), "prediction_std": float(p.std())}
    ci = cluster_bootstrap_ci(predictions)
    checks = {
        "generic_minus_event_brier_ci_lower_positive": ci[0] > 0,
        "event_brier_better_than_all_comparators": all(arm_summary["event"]["brier"] < arm_summary[x]["brier"] for x in ("tech", "metadata", "generic", "permuted")),
        "event_beats_generic_at_least_3_of_5_folds": sum(f["generic_minus_event_brier"] > 0 for f in fold_metrics) >= 3,
        "event_auc_above_generic": arm_summary["event"]["auc"] > arm_summary["generic"]["auc"],
        "event_predictions_nonconstant": arm_summary["event"]["prediction_std"] > 1e-9,
        "both_classes_in_every_fold": bool(all_two_classes),
    }
    passed = all(checks.values())
    prediction_path = root / "paper/input/results/hybrid/hyb008_conditional_downside_predictions.json"
    write(prediction_path, {"schema_version": 1, "experiment_id": "HYB-008", "rows": predictions})
    result = {
        "schema_version": 1,
        "experiment_id": "HYB-008",
        "status": "STAGE_A_INFORMATION_PASS_STAGE_B_DESIGN_AUTHORIZED" if passed else "STAGE_A_INFORMATION_FAIL_STOP_BEFORE_POLICY",
        "passed": passed,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "research_role": pre["research_role"],
        "oos_rows": len(predictions),
        "oos_dates": len({r["utc_date"] for r in predictions}),
        "positive_rate": float(labels.mean()),
        "arms": arm_summary,
        "primary_generic_minus_event_brier": arm_summary["generic"]["brier"] - arm_summary["event"]["brier"],
        "primary_date_cluster_bootstrap_95_ci": ci,
        "folds": fold_metrics,
        "positive_folds": sum(f["generic_minus_event_brier"] > 0 for f in fold_metrics),
        "checks": checks,
        "predictions": {"path": str(prediction_path), "sha256": sha(prediction_path)},
        "interpretation": "Stage A tests conditional downside information only; it is not a trading-performance or live-value result.",
        "next_authorized_action": "Freeze a separate cost-aware Stage-B policy." if passed else "Stop HYB-008 before policy/backtest; do not tune on these outcomes.",
    }
    out = root / "paper/input/results/hybrid/hyb008_conditional_downside_evaluation.json"
    write(out, result)
    print(json.dumps({k: result[k] for k in ("status", "oos_rows", "oos_dates", "positive_rate", "arms", "primary_generic_minus_event_brier", "primary_date_cluster_bootstrap_95_ci", "positive_folds", "checks", "next_authorized_action")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
