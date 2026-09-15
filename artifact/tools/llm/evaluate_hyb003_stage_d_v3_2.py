"""Outcome-aware remediation diagnostic for HYB-003 Stage D.

Version 3.2 does not pretend to be the frozen v3.1 evaluation.  It uses only
features already materialized before the v3.1 outcome was inspected, applies a
causal cluster-level inner split, treats the net half-downsize target exactly
once, and computes the registered primary contrast row by row.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

BOOTSTRAP_DRAWS = 10_000
BOOTSTRAP_SEED = 20260911
ALPHA_GRID = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
MINIMUM_OOS_CLUSTERS = 12

FOLD_SPECS = [
    {"fold_id": 1, "train_end": "2024-03-31T23:59:59+00:00", "eval_start": "2024-04-04T04:00:00+00:00", "eval_end": "2024-08-31T23:59:59+00:00"},
    {"fold_id": 2, "train_end": "2024-08-31T23:59:59+00:00", "eval_start": "2024-09-04T04:00:00+00:00", "eval_end": "2024-12-31T23:59:59+00:00"},
    {"fold_id": 3, "train_end": "2024-12-31T23:59:59+00:00", "eval_start": "2025-01-04T04:00:00+00:00", "eval_end": "2025-08-28T23:59:59+00:00"},
]

T1_NUMERIC = [
    "trade_age_4h", "open_to_raw_entry_return", "distance_to_active_stop_atr",
    "entry_atr_over_open", "past_average_range_12h", "past_average_range_24h",
    "past_return_4h", "past_return_12h", "past_return_24h",
    "last_observed_funding_rate", "past_funding_sum_24h",
]
TEXT_NUMERIC = [
    "adverse_mass", "supportive_mass", "adverse_h4_mass", "supportive_h4_mass",
    "applicable_headline_count", "adverse_headline_count", "supportive_headline_count",
    "source_domain_count", "novel_signature_count", "text_available_this_bar",
]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_atomic(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return sha256(path)


def parse_iso_ms(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def cluster_se(pairs: list[tuple[str, float]]) -> float:
    if not pairs:
        return math.inf
    mean = statistics.fmean(value for _, value in pairs)
    groups: dict[str, float] = defaultdict(float)
    for cluster, value in pairs:
        groups[cluster] += value - mean
    n, g = len(pairs), len(groups)
    if g < 2:
        return math.inf
    return math.sqrt(g / (g - 1) * sum(value * value for value in groups.values()) / (n * n))


def cluster_bootstrap(pairs: list[tuple[str, float]], draws: int, seed: int) -> dict[str, float]:
    groups: dict[str, list[float]] = defaultdict(list)
    for cluster, value in pairs:
        groups[cluster].append(value)
    ids = sorted(groups)
    observed = statistics.fmean(value for _, value in pairs) if pairs else math.nan
    if len(ids) < 2:
        return {"mean": observed, "ci_95_lower": math.nan, "ci_95_upper": math.nan}
    rng = random.Random(seed)
    samples = sorted(
        statistics.fmean(value for cluster in [rng.choice(ids) for _ in ids] for value in groups[cluster])
        for _ in range(draws)
    )
    return {
        "mean": observed,
        "ci_95_lower": samples[int(0.025 * draws)],
        "ci_95_upper": samples[int(0.975 * draws)],
    }


def make_encoding(rows: list[dict], state_by_row: dict[str, dict]) -> dict[str, list[str]]:
    return {
        "symbols": sorted({row["features"]["symbol"] for row in rows}),
        "stages": sorted({state_by_row[row["row_id"]]["text_state"]["dominant_stage"] for row in rows}),
        "mechanisms": sorted({state_by_row[row["row_id"]]["text_state"]["dominant_mechanism"] for row in rows}),
    }


def one_hot(value: str, levels: list[str]) -> list[float]:
    return [1.0 if value == level else 0.0 for level in levels]


def build_matrix(rows: list[dict], state_by_row: dict[str, dict], arm: str, encoding: dict[str, list[str]]) -> tuple[np.ndarray, np.ndarray, list[str], list[str]]:
    matrix: list[list[float]] = []
    targets: list[float] = []
    clusters: list[str] = []
    row_ids: list[str] = []
    for row in rows:
        features = row["features"]
        text = state_by_row[row["row_id"]]["text_state"]
        tech = [float(features[key] or 0.0) for key in T1_NUMERIC]
        tech += one_hot(features["symbol"], encoding["symbols"])
        text_vector = [float(text[key] or 0.0) for key in TEXT_NUMERIC]
        text_vector += one_hot(text["dominant_stage"], encoding["stages"])
        text_vector += one_hot(text["dominant_mechanism"], encoding["mechanisms"])
        if arm == "T1":
            vector = tech
        elif arm == "T2":
            vector = text_vector
        elif arm == "T3":
            vector = tech + text_vector
        else:
            raise ValueError(f"unknown arm: {arm}")
        matrix.append(vector)
        targets.append(float(row["target"]["net_action_value"]))
        clusters.append(row["trade_id"])
        row_ids.append(row["row_id"])
    return np.asarray(matrix, dtype=float), np.asarray(targets, dtype=float), clusters, row_ids


def expanding_cluster_splits(clusters: list[str]) -> list[tuple[np.ndarray, np.ndarray]]:
    ordered: list[str] = []
    for cluster in clusters:
        if cluster not in ordered:
            ordered.append(cluster)
    if len(ordered) < 4:
        return []
    blocks = [list(block) for block in np.array_split(np.asarray(ordered, dtype=object), 4)]
    splits = []
    for index in range(1, 4):
        train_ids = {item for block in blocks[:index] for item in block}
        valid_ids = set(blocks[index])
        train = np.asarray([i for i, cluster in enumerate(clusters) if cluster in train_ids], dtype=int)
        valid = np.asarray([i for i, cluster in enumerate(clusters) if cluster in valid_ids], dtype=int)
        if len(train) and len(valid):
            splits.append((train, valid))
    return splits


def select_alpha(x: np.ndarray, y: np.ndarray, clusters: list[str]) -> float:
    splits = expanding_cluster_splits(clusters)
    if not splits:
        return ALPHA_GRID[-1]
    best_alpha, best_mse = ALPHA_GRID[0], math.inf
    for alpha in ALPHA_GRID:
        losses = []
        for train, valid in splits:
            scaler = StandardScaler().fit(x[train])
            model = Ridge(alpha=alpha).fit(scaler.transform(x[train]), y[train])
            prediction = model.predict(scaler.transform(x[valid]))
            losses.append(float(np.mean((prediction - y[valid]) ** 2)))
        mean_loss = statistics.fmean(losses)
        if mean_loss < best_mse:
            best_alpha, best_mse = alpha, mean_loss
    return best_alpha


def policy_action(prediction: float, uncertainty_margin: float) -> bool:
    """Target is already net of costs, so only uncertainty remains in the deadband."""
    return prediction > uncertainty_margin


def evaluate_arm(arm: str, fold_rows: list[tuple[list[dict], list[dict]]], state_by_row: dict[str, dict]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    fold_results = []
    for specification, (train_rows, eval_rows) in zip(FOLD_SPECS, fold_rows):
        encoding = make_encoding(train_rows, state_by_row)
        x_train, y_train, train_clusters, _ = build_matrix(train_rows, state_by_row, arm, encoding)
        x_eval, y_eval, eval_clusters, eval_ids = build_matrix(eval_rows, state_by_row, arm, encoding)
        alpha = select_alpha(x_train, y_train, train_clusters)
        scaler = StandardScaler().fit(x_train)
        model = Ridge(alpha=alpha).fit(scaler.transform(x_train), y_train)
        train_prediction = model.predict(scaler.transform(x_train))
        margin = cluster_se(list(zip(train_clusters, (y_train - train_prediction).tolist())))
        prediction = model.predict(scaler.transform(x_eval))
        actions = [policy_action(float(value), margin) for value in prediction]
        deltas = [float(y_eval[i]) if actions[i] else 0.0 for i in range(len(y_eval))]
        pearson = float(np.corrcoef(prediction, y_eval)[0, 1]) if len(y_eval) >= 3 else math.nan
        for i, row_id in enumerate(eval_ids):
            records.append({
                "row_id": row_id, "trade_id": eval_clusters[i], "fold_id": specification["fold_id"],
                "prediction": float(prediction[i]), "target_net_half_downsize_delta": float(y_eval[i]),
                "uncertainty_margin": margin, "intervene": actions[i], "policy_delta": deltas[i],
            })
        fold_results.append({
            "fold_id": specification["fold_id"], "alpha": alpha, "n_eval": len(eval_rows),
            "n_eval_clusters": len(set(eval_clusters)), "pearson": pearson,
            "action_rate": statistics.fmean(float(value) for value in actions),
            "mean_policy_delta": statistics.fmean(deltas), "uncertainty_margin": margin,
        })
    prediction = np.asarray([row["prediction"] for row in records])
    target = np.asarray([row["target_net_half_downsize_delta"] for row in records])
    pairs = [(row["trade_id"], row["policy_delta"]) for row in records]
    inference = cluster_bootstrap(pairs, BOOTSTRAP_DRAWS, BOOTSTRAP_SEED)
    return {
        "arm": arm, "n_eligible_decisions": len(records),
        "n_eligible_clusters": len({row["trade_id"] for row in records}),
        "overall_action_rate": statistics.fmean(float(row["intervene"]) for row in records),
        "pearson_oos_overall": float(np.corrcoef(prediction, target)[0, 1]),
        "policy_vs_t0": inference, "folds": fold_results, "row_results": records,
    }


def paired_contrast(left: dict[str, Any], right: dict[str, Any]) -> dict[str, float]:
    right_by_id = {row["row_id"]: row for row in right["row_results"]}
    pairs = []
    for row in left["row_results"]:
        comparator = right_by_id[row["row_id"]]
        if row["trade_id"] != comparator["trade_id"]:
            raise ValueError("paired rows disagree on trade cluster")
        pairs.append((row["trade_id"], row["policy_delta"] - comparator["policy_delta"]))
    return cluster_bootstrap(pairs, BOOTSTRAP_DRAWS, BOOTSTRAP_SEED)


def validate_inputs(panel: dict[str, Any], state: dict[str, Any]) -> None:
    panel_ids = {row["row_id"] for row in panel["rows"]}
    state_ids = {row["row_id"] for row in state["rows"]}
    if panel_ids != state_ids:
        raise ValueError("panel/state row IDs differ")
    feature_keys = set(panel["rows"][0]["features"])
    missing = set(T1_NUMERIC + ["symbol"]) - feature_keys
    if missing:
        raise ValueError(f"missing materialized Tech features: {sorted(missing)}")
    text_keys = set(state["rows"][0]["text_state"])
    missing_text = set(TEXT_NUMERIC + ["dominant_stage", "dominant_mechanism"]) - text_keys
    if missing_text:
        raise ValueError(f"missing materialized text features: {sorted(missing_text)}")


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, default=root / "paper/input/results/hybrid/tech_llm_conditional_state_fusion_v3_panel.json")
    parser.add_argument("--state", type=Path, default=root / "paper/input/results/hybrid/tech_llm_conditional_state_v3_1.json")
    parser.add_argument("--deviation-audit", type=Path, default=root / "paper/input/results/hybrid/hyb003_stage_d_v3_1_protocol_deviation_audit.json")
    parser.add_argument("--output", type=Path, default=root / "paper/input/results/hybrid/hyb003_stage_d_remediation_v3_2.json")
    args = parser.parse_args()
    audit = load(args.deviation_audit)
    if audit["status"] != "PROTOCOL_DEVIATION_RESULT_NOT_REPORTABLE_AS_FROZEN_STAGE_D":
        raise ValueError("v3.1 protocol-deviation audit is missing or invalid")
    panel, state = load(args.panel), load(args.state)
    validate_inputs(panel, state)
    state_by_row = {row["row_id"]: row for row in state["rows"]}
    rows = panel["rows"]
    boundaries = [(parse_iso_ms(fold["train_end"]), parse_iso_ms(fold["eval_start"]), parse_iso_ms(fold["eval_end"])) for fold in FOLD_SPECS]
    fold_rows = [
        ([row for row in rows if row["decision_time"] <= train_end],
         [row for row in rows if eval_start <= row["decision_time"] <= eval_end])
        for train_end, eval_start, eval_end in boundaries
    ]
    arms = {arm: evaluate_arm(arm, fold_rows, state_by_row) for arm in ("T1", "T2", "T3")}
    primary = paired_contrast(arms["T3"], arms["T1"])
    oos_clusters = arms["T3"]["n_eligible_clusters"]
    sufficient = oos_clusters >= MINIMUM_OOS_CLUSTERS
    payload = {
        "schema_version": "hyb003-stage-d-remediation-v3.2",
        "experiment_id": "HYB-003",
        "status": "INSUFFICIENT_OOS_CLUSTERS" if not sufficient else "EXPLORATORY_REMEDIATION_EVALUATED",
        "research_role": (
            "Post-outcome remediation diagnostic after the v3.1 implementation deviation. "
            "Not a frozen predeclared result, validation, sealed holdout, or live evidence."
        ),
        "implementation_contract": {
            "tech_features": T1_NUMERIC + ["symbol_train_only_one_hot"],
            "text_features": TEXT_NUMERIC + ["dominant_stage_train_only_one_hot", "dominant_mechanism_train_only_one_hot"],
            "interactions": [],
            "target": "materialized net_action_value for the half-downsize; costs already included",
            "deadband": "intervene iff predicted net_action_value > cluster-robust training-residual SE",
            "policy_delta": "net_action_value exactly once when intervening; zero otherwise",
            "inner_selection": "three expanding, non-overlapping trade-cluster validation blocks",
            "primary_contrast": "row-paired T3 policy delta minus T1 policy delta; bootstrap by trade_id",
        },
        "arm_results": arms,
        "primary_t3_minus_t1": primary,
        "gate": {
            "minimum_oos_clusters": MINIMUM_OOS_CLUSTERS,
            "observed_oos_clusters": oos_clusters,
            "sufficient_oos_clusters": sufficient,
            "stage_e_authorized": False,
            "unrun_after_stop": ["placebos", "T3-T0 portfolio replay", "intrabar MDD"],
        },
        "inputs": {
            "panel": {"path": str(args.panel), "sha256": sha256(args.panel)},
            "state": {"path": str(args.state), "sha256": sha256(args.state)},
            "deviation_audit": {"path": str(args.deviation_audit), "sha256": sha256(args.deviation_audit)},
            "evaluator": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__))},
        },
    }
    output_hash = write_atomic(args.output, payload)
    print(json.dumps({
        "output": str(args.output), "sha256": output_hash, "status": payload["status"],
        "oos_clusters": oos_clusters, "primary_t3_minus_t1": primary,
        "actions": {arm: arms[arm]["overall_action_rate"] for arm in arms},
        "pearson": {arm: arms[arm]["pearson_oos_overall"] for arm in arms},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
