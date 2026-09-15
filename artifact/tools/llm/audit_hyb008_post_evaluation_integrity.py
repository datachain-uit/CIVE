"""Independent post-evaluation integrity checks for HYB-008 artifacts."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from sklearn.metrics import brier_score_loss, roc_auc_score

from hyb008_conditional_downside_common import SYMBOLS, build_population, read, selection_map, sha, write


def main():
    root = Path(__file__).resolve().parents[2]
    panel = read(root / "paper/input/results/llm/v20/llm_only_multicoin_short_panel_v20.json")
    tech = read(root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_daily_panel.json")
    pre_path = root / "paper/input/results/hybrid/hyb008_conditional_downside_predeclared.json"
    sample_path = root / "paper/input/results/hybrid/hyb008_conditional_downside_sample_audit.json"
    pred_path = root / "paper/input/results/hybrid/hyb008_conditional_downside_predictions.json"
    eval_path = root / "paper/input/results/hybrid/hyb008_conditional_downside_evaluation.json"
    pre, sample, predictions, evaluation = read(pre_path), read(sample_path), read(pred_path)["rows"], read(eval_path)
    selected = selection_map(tech["rows"])
    eligible_before_history = []
    for symbol in SYMBOLS:
        for row in panel["assets"][symbol]["records"]:
            when = datetime.fromisoformat(row["decision_at"]).astimezone(timezone.utc)
            if symbol in selected.get(when.date().isoformat(), []):
                eligible_before_history.append((symbol, when.isoformat()))
    bar_dir = root / "results/bybit_lifecycle_4h"
    bars = {s: read(bar_dir / f"{s}_1660348800000_1786492800000.json") for s in SYMBOLS}
    retained = build_population(panel, tech, bars, include_target=False)
    keys = [(r["symbol"], r["decision_at"]) for r in predictions]
    labels = np.array([r["label"] for r in predictions])
    recomputed = {}
    for arm in ("tech", "metadata", "generic", "event", "permuted"):
        probs = np.array([r[f"p_{arm}"] for r in predictions])
        recomputed[arm] = {"brier": brier_score_loss(labels, probs), "auc": roc_auc_score(labels, probs)}
    metric_match = all(abs(recomputed[a][m] - evaluation["arms"][a][m]) < 1e-12 for a in recomputed for m in recomputed[a])
    fold_ranges = [(f["test_dates"][0], f["test_dates"][1]) for f in evaluation["folds"]]
    checks = {
        "history_coverage_100pct": len(retained) == len(eligible_before_history) == 1008,
        "sample_count_matches": sample["sample"]["rows"] == len(retained),
        "prediction_keys_unique": len(keys) == len(set(keys)),
        "prediction_count_matches": len(predictions) == evaluation["oos_rows"] == 692,
        "fold_test_ranges_nonoverlap": all(fold_ranges[i][1] < fold_ranges[i + 1][0] for i in range(4)),
        "metrics_recompute_exactly": metric_match,
        "predeclaration_hash_matches_sample": sample["predeclaration"]["sha256"] == sha(pre_path),
        "stage_b_not_authorized": evaluation["passed"] is False and "STOP_BEFORE_POLICY" in evaluation["status"],
    }
    result = {
        "schema_version": 1,
        "experiment_id": "HYB-008",
        "status": "POST_EVALUATION_INTEGRITY_PASS" if all(checks.values()) else "POST_EVALUATION_INTEGRITY_FAIL",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "eligible_selected_rows_before_history_filter": len(eligible_before_history),
        "rows_retained_after_18bar_history_requirement": len(retained),
        "history_coverage_fraction": len(retained) / len(eligible_before_history),
        "prediction_rows_by_fold": dict(Counter(str(r["fold"]) for r in predictions)),
        "recomputed_metrics": recomputed,
        "checks": checks,
        "source_hashes": {"predeclaration": sha(pre_path), "sample_audit": sha(sample_path), "predictions": sha(pred_path), "evaluation": sha(eval_path)},
        "interpretation": "Confirms artifact integrity and the missing history-coverage denominator; it does not change the frozen Stage-A result.",
    }
    out = root / "paper/input/results/hybrid/hyb008_post_evaluation_integrity_audit.json"
    write(out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
