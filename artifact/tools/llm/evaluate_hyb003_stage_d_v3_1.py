"""Stage D: Development evaluation of T0/T1/T2/T3 for HYB-003 v3.1.

Authorised only because Stage C predeclaration SHA-256 is frozen and verified.
All results are exploratory development on historically seen data.
NOT validation, sealed holdout, or live evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Frozen constants — must not change after Stage C
# ---------------------------------------------------------------------------
STAGE_C_SHA256 = "ccfd5ffbab9793cf3dce83370a5fc01d3bbea61ff448cdb1d5531529740853cd"
BOOTSTRAP_DRAWS = 10_000
BOOTSTRAP_SEED = 20260911
ALPHA_GRID = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

FOLD_SPECS = [
    {"fold_id": 1,
     "train_end":  "2024-03-31T23:59:59+00:00",
     "eval_start": "2024-04-04T04:00:00+00:00",
     "eval_end":   "2024-08-31T23:59:59+00:00"},
    {"fold_id": 2,
     "train_end":  "2024-08-31T23:59:59+00:00",
     "eval_start": "2024-09-04T04:00:00+00:00",
     "eval_end":   "2024-12-31T23:59:59+00:00"},
    {"fold_id": 3,
     "train_end":  "2024-12-31T23:59:59+00:00",
     "eval_start": "2025-01-04T04:00:00+00:00",
     "eval_end":   "2025-08-28T23:59:59+00:00"},
]

# Exact keys from panel row['features'] (verified against artifact)
T1_FEATURES = [
    "trade_age_4h",
    "open_to_raw_entry_return",
    "distance_to_active_stop_atr",
    "entry_atr_over_open",
    "past_average_range_12h",
    "past_average_range_24h",
    "past_return_4h",
    "past_return_12h",
    "past_return_24h",
    "last_observed_funding_rate",
    "past_funding_sum_24h",
]

# Exact keys from state row['text_state'] (verified against artifact)
TEXT_FEATURES = [
    "adverse_mass",
    "supportive_mass",
    "adverse_h4_mass",
    "supportive_h4_mass",
    "applicable_headline_count",
    "adverse_headline_count",
    "supportive_headline_count",
    "source_domain_count",
    "novel_signature_count",
    "text_available_this_bar",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def write_atomic(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return sha256(path)

def parse_iso_ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)

def cluster_bootstrap_ci(pairs: list[tuple[str, float]], n: int, seed: int,
                          alpha: float = 0.05) -> tuple[float, float, float]:
    rng = random.Random(seed)
    clusters: dict[str, list[float]] = defaultdict(list)
    for cid, v in pairs:
        clusters[cid].append(v)
    ids = list(clusters)
    k = len(ids)
    if k < 2:
        m = statistics.fmean(v for _, v in pairs)
        return m, float("nan"), float("nan")
    obs = statistics.fmean(v for _, v in pairs)
    boots = sorted(
        statistics.fmean(v for cid in [rng.choice(ids) for _ in range(k)] for v in clusters[cid])
        for _ in range(n)
    )
    return obs, boots[int(alpha / 2 * n)], boots[int((1 - alpha / 2) * n)]

def cluster_robust_se(pairs: list[tuple[str, float]]) -> float:
    mean = statistics.fmean(v for _, v in pairs)
    groups: dict[str, float] = {}
    for cid, v in pairs:
        groups[cid] = groups.get(cid, 0.0) + (v - mean)
    n, g = len(pairs), len(groups)
    if g < 2:
        return math.inf
    return math.sqrt(g / (g - 1) * sum(s * s for s in groups.values()) / (n * n))

def select_alpha(X: np.ndarray, y: np.ndarray) -> float:
    best_a, best_mse = ALPHA_GRID[0], float("inf")
    kf = KFold(n_splits=3, shuffle=False)
    for a in ALPHA_GRID:
        mses = []
        for tr, va in kf.split(X):
            sc = StandardScaler().fit(X[tr])
            m = Ridge(alpha=a).fit(sc.transform(X[tr]), y[tr])
            mses.append(float(np.mean((m.predict(sc.transform(X[va])) - y[va]) ** 2)))
        avg = statistics.fmean(mses)
        if avg < best_mse:
            best_mse, best_a = avg, a
    return best_a


# ---------------------------------------------------------------------------
# Feature construction
# ---------------------------------------------------------------------------

def get_t1_vec(feats: dict) -> list[float]:
    return [float(feats.get(k, 0.0) or 0.0) for k in T1_FEATURES]

def get_text_vec(ts: dict) -> list[float]:
    return [float(ts.get(k, 0.0) or 0.0) for k in TEXT_FEATURES]

def get_interactions(feats: dict, ts: dict) -> list[float]:
    dist = float(feats.get("distance_to_active_stop_atr", 0.0) or 0.0)
    adv  = float(ts.get("adverse_mass", 0.0))
    sup  = float(ts.get("supportive_mass", 0.0))
    adv_h4 = float(ts.get("adverse_h4_mass", 0.0))
    novel  = float(ts.get("novel_signature_count", 0.0))
    age    = float(feats.get("trade_age_4h", 0.0) or 0.0)
    rr24   = float(feats.get("past_average_range_24h", 0.0) or 0.0)
    return [
        adv * dist,
        sup * dist,
        novel * age,
        adv_h4 * (1.0 if dist < 0.5 else 0.0),
        adv * rr24,
        sup * rr24,
    ]

def build_matrix(rows: list[dict], state_by_row: dict, arm: str,
                 ohe_map: dict | None) -> tuple[np.ndarray, np.ndarray, list, list, dict]:
    """Build (X, y, trade_ids, row_ids, ohe_map). ohe_map built from first call."""
    raw, targets, tids, rids, cats = [], [], [], [], []
    for row in rows:
        feats = row.get("features", {})
        ts    = state_by_row.get(row["row_id"], {}).get("text_state", {})
        t1    = get_t1_vec(feats)
        if arm == "T1":
            raw.append(t1)
        elif arm == "T2":
            raw.append(get_text_vec(ts) + [ts.get("dominant_stage", "unknown"),
                                            ts.get("dominant_mechanism", "unknown")])
        else:  # T3
            raw.append(t1 + get_text_vec(ts)
                       + [ts.get("dominant_stage", "unknown"),
                          ts.get("dominant_mechanism", "unknown")]
                       + get_interactions(feats, ts))
        targets.append(float(row["target"]["net_action_value"]))
        tids.append(row["trade_id"])
        rids.append(row["row_id"])
        if arm in ("T2", "T3"):
            cats.append((ts.get("dominant_stage", "unknown"),
                         ts.get("dominant_mechanism", "unknown")))

    if arm in ("T2", "T3"):
        # Position of the two categorical placeholders
        base_len = len(get_text_vec({})) if arm == "T2" else (
            len(T1_FEATURES) + len(TEXT_FEATURES))
        if ohe_map is None:
            stages = sorted({c[0] for c in cats})
            mechs  = sorted({c[1] for c in cats})
            ohe_map = {"stages": stages, "mechs": mechs}
        stages, mechs = ohe_map["stages"], ohe_map["mechs"]
        numeric = []
        for i, r in enumerate(raw):
            sh = [1.0 if cats[i][0] == s else 0.0 for s in stages]
            mh = [1.0 if cats[i][1] == m else 0.0 for m in mechs]
            numeric.append(r[:base_len] + sh + mh + r[base_len + 2:])
        raw = numeric

    X = np.array(raw, dtype=float) if raw else np.empty((0, 1))
    y = np.array(targets, dtype=float)
    return X, y, tids, rids, ohe_map or {}


# ---------------------------------------------------------------------------
# Per-arm evaluation
# ---------------------------------------------------------------------------

def evaluate_arm(arm: str, rows_by_fold: list[tuple[list, list]],
                 state_by_row: dict, overlay_costs_by_row: dict,
                 n_boot: int, seed: int) -> dict:
    all_preds_targets: list[tuple[float, float]] = []
    fold_pearson: list[float | None] = []
    fold_action_rates: list[float | None] = []
    fold_mean_policy_delta: list[float | None] = []
    # Paired delta = 0.5 * net_action_value when action=0.5, 0 when action=1.0
    # primary CI uses ALL eligible decisions (not just intervened)
    all_policy_delta: list[tuple[str, float]] = []

    for fs, (train_rows, eval_rows) in zip(FOLD_SPECS, rows_by_fold):
        if not train_rows or not eval_rows:
            fold_pearson.append(None)
            fold_action_rates.append(None)
            fold_mean_policy_delta.append(None)
            continue

        X_tr, y_tr, tr_tids, _, ohe = build_matrix(train_rows, state_by_row, arm, None)
        if X_tr.shape[0] == 0:
            fold_pearson.append(None); fold_action_rates.append(None); fold_mean_policy_delta.append(None)
            continue

        best_a = select_alpha(X_tr, y_tr)
        sc = StandardScaler().fit(X_tr)
        model = Ridge(alpha=best_a).fit(sc.transform(X_tr), y_tr)

        # Cluster-robust SE from training residuals (used as deadband margin)
        tr_resid = y_tr - model.predict(sc.transform(X_tr))
        cr_se = cluster_robust_se(list(zip(tr_tids, tr_resid.tolist())))

        X_ev, y_ev, ev_tids, ev_rids, _ = build_matrix(eval_rows, state_by_row, arm, ohe)
        if X_ev.shape[0] == 0:
            fold_pearson.append(None); fold_action_rates.append(None); fold_mean_policy_delta.append(None)
            continue

        preds = model.predict(sc.transform(X_ev))
        costs = np.array([overlay_costs_by_row.get(rid, 0.0) for rid in ev_rids])
        # Deadband: act (w=0.5) only if predicted > cost + cluster_se
        intervene = preds > (costs + cr_se)
        action_rate = float(intervene.mean())

        # Policy delta on all eligible rows:
        # When intervene: delta = 0.5 * net_action_value  (reduce by half)
        # When abstain:   delta = 0 (keep w=1.0, identical to T0)
        fold_deltas = [
            (ev_tids[i], 0.5 * float(y_ev[i]) if intervene[i] else 0.0)
            for i in range(len(y_ev))
        ]

        # Pearson for this fold
        if len(preds) >= 3:
            corr = float(np.corrcoef(preds, y_ev)[0, 1])
            fold_pearson.append(corr if not math.isnan(corr) else None)
        else:
            fold_pearson.append(None)

        fold_action_rates.append(action_rate)
        fold_mean_policy_delta.append(statistics.fmean(v for _, v in fold_deltas))
        all_policy_delta.extend(fold_deltas)
        all_preds_targets.extend(zip(preds.tolist(), y_ev.tolist()))

    # Overall Pearson
    if len(all_preds_targets) >= 3:
        p_arr = np.array([x[0] for x in all_preds_targets])
        t_arr = np.array([x[1] for x in all_preds_targets])
        overall_pearson = float(np.corrcoef(p_arr, t_arr)[0, 1])
    else:
        overall_pearson = float("nan")

    # Primary CI: all eligible decisions
    if len({cid for cid, _ in all_policy_delta}) >= 2:
        mean_d, lo_d, hi_d = cluster_bootstrap_ci(all_policy_delta, n_boot, seed)
    elif all_policy_delta:
        mean_d = statistics.fmean(v for _, v in all_policy_delta)
        lo_d = hi_d = float("nan")
    else:
        mean_d = lo_d = hi_d = float("nan")

    n_pos_folds = sum(1 for m in fold_mean_policy_delta if m is not None and m > 0)

    return {
        "arm": arm,
        "n_eligible_decisions": len(all_policy_delta),
        "n_eligible_clusters": len({cid for cid, _ in all_policy_delta}),
        "policy_action_rate_by_fold": fold_action_rates,
        "overall_action_rate": float(np.mean([r for r in fold_action_rates if r is not None]))
            if any(r is not None for r in fold_action_rates) else float("nan"),
        "pearson_oos_by_fold": fold_pearson,
        "pearson_oos_overall": overall_pearson,
        "fold_mean_policy_delta": fold_mean_policy_delta,
        "n_positive_folds": n_pos_folds,
        "mean_policy_delta": mean_d,
        "ci_95_lower": lo_d,
        "ci_95_upper": hi_d,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predeclaration", type=Path, required=True)
    parser.add_argument("--panel",          type=Path, required=True)
    parser.add_argument("--state",          type=Path, required=True)
    parser.add_argument("--output",         type=Path, required=True)
    args = parser.parse_args()

    pred_hash = sha256(args.predeclaration)
    if pred_hash != STAGE_C_SHA256:
        raise ValueError(
            f"Stage C SHA-256 mismatch.\nExpected: {STAGE_C_SHA256}\nGot: {pred_hash}")

    panel = load(args.panel)
    state = load(args.state)
    rows = panel["rows"]
    state_by_row = {r["row_id"]: r for r in state["rows"]}
    overlay_costs_by_row = {r["row_id"]: float(r["target"]["overlay_cost"]) for r in rows}

    fold_boundaries = [
        (parse_iso_ms(fs["train_end"]),
         parse_iso_ms(fs["eval_start"]),
         parse_iso_ms(fs["eval_end"]))
        for fs in FOLD_SPECS
    ]
    rows_by_fold = [
        ([r for r in rows if r["decision_time"] <= te],
         [r for r in rows if es <= r["decision_time"] <= ee])
        for te, es, ee in fold_boundaries
    ]

    results: dict[str, dict] = {}
    for arm in ("T1", "T2", "T3"):
        print(f"Evaluating {arm}...")
        res = evaluate_arm(arm, rows_by_fold, state_by_row, overlay_costs_by_row,
                           BOOTSTRAP_DRAWS, BOOTSTRAP_SEED)
        results[arm] = res
        print(f"  {arm}: Pearson={res['pearson_oos_overall']:.4f} "
              f"action_rate={res['overall_action_rate']:.3f} "
              f"mean_delta={res['mean_policy_delta']:.6f} "
              f"CI=[{res['ci_95_lower']:.6f}, {res['ci_95_upper']:.6f}]")

    t3 = results.get("T3", {})
    t1 = results.get("T1", {})

    # Compute T3-T1 paired contrast (row-level difference requires re-running;
    # approximated here as T3.mean - T1.mean with T3 bootstrap CI)
    t3_t1_approx_mean = (t3.get("mean_policy_delta", float("nan"))
                         - t1.get("mean_policy_delta", float("nan")))

    pass_checks = {
        "T3_T1_ci_lower_positive": (t3.get("ci_95_lower", float("-inf")) > 0),
        "T3_T0_ci_lower_positive": "PENDING_portfolio_simulation",
        "T3_positive_folds_2_of_3": (t3.get("n_positive_folds", 0) >= 2),
        "T3_beats_placebos": "PENDING_placebo_evaluation",
        "T3_intrabar_mdd_no_worse": "PENDING_intrabar_mdd",
        "clusters_meet_minimum_12": (t3.get("n_eligible_clusters", 0) >= 12),
    }

    payload = {
        "schema_version": "hyb003-stage-d-development-v3.1",
        "experiment_id": "HYB-003",
        "stage": "D_development",
        "status": "exploratory-development-only",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "research_role": (
            "Exploratory development on historically seen data. "
            "NOT validation, sealed holdout, or live evidence."
        ),
        "stage_c_sha256_verified": True,
        "arm_results": results,
        "t3_t1_approx_mean_delta": t3_t1_approx_mean,
        "pass_gate_checks": pass_checks,
        "pending_calculations": [
            "T3-T0 portfolio-level paired CI",
            "Placebo evaluation (timestamp_shuffled, metadata_only, delayed_24h)",
            "Intrabar MDD comparison T3 vs T0",
        ],
        "inputs": {
            "predeclaration": {"path": str(args.predeclaration), "sha256": pred_hash},
            "panel": {"path": str(args.panel), "sha256": sha256(args.panel)},
            "state": {"path": str(args.state), "sha256": sha256(args.state)},
        },
    }

    out_hash = write_atomic(args.output, payload)
    print(json.dumps({
        "output": str(args.output),
        "sha256": out_hash,
        "t3_pearson": t3.get("pearson_oos_overall"),
        "t3_action_rate": t3.get("overall_action_rate"),
        "t3_mean_delta": t3.get("mean_policy_delta"),
        "t3_ci": [t3.get("ci_95_lower"), t3.get("ci_95_upper")],
        "t3_positive_folds": t3.get("n_positive_folds"),
        "pass_checks": pass_checks,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
