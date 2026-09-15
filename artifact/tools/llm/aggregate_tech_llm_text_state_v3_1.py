"""Materialize outcome-blind causal text state and Stage-B feasibility audit for HYB-003."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUR_H_MS = 4 * 60 * 60 * 1000
HORIZONS = ((4, "h4"), (12, "h12"), (24, "h24"), (72, "h72"))
SCOPE_WEIGHT = {"direct_held": 1.0, "crypto_systemic": 0.75, "other": 0.0, "unknown": 0.0}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def cluster_se(values: list[tuple[str, float]]) -> float:
    mean = statistics.fmean(value for _, value in values)
    groups: dict[str, float] = {}
    for key, value in values:
        groups[key] = groups.get(key, 0.0) + value - mean
    n, g = len(values), len(groups)
    if n == 0 or g < 2:
        return math.inf
    return math.sqrt(g / (g - 1) * sum(total * total for total in groups.values()) / (n * n))


def decay_mass(record: dict[str, Any], age_hours: float) -> float:
    """Mass still actionable at a decision, using only prior text and registered horizons."""
    if age_hours < 0 or age_hours >= 72:
        return 0.0
    return sum(float(record["horizon_mass"][key]) for horizon, key in HORIZONS if age_hours < horizon)


def normalize_evidence(value: str) -> str:
    return " ".join(value.lower().split())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--extraction", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--state-output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()

    config, panel, extraction, gate = map(load, (args.config, args.panel, args.extraction, args.gate))
    required = config["frozen_contract"]
    if gate.get("passed") is not True or gate.get("status") != "full-extraction-pass-power-freeze-authorized":
        raise ValueError("full extraction gate does not authorize Stage B")
    expected = required["extraction"]
    if sha256(args.extraction) != expected["sha256"]:
        raise ValueError("extraction hash differs from frozen Stage-B contract")
    if sha256(args.panel) != required["panel"]["sha256"]:
        raise ValueError("panel hash differs from frozen Stage-B contract")
    rows = panel["rows"]
    records = extraction["records"]
    if len(records) != required["extraction"]["records"] or any(item.get("status") != "success" for item in records):
        raise ValueError("full extraction is not entirely successful")

    seen_ids: set[str] = set()
    records_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        if item["headline_id"] in seen_ids:
            continue
        seen_ids.add(item["headline_id"])
        item = dict(item)
        item["available_ms"] = parse_ms(item["available_at"])
        item["signature"] = "|".join((item["affected_asset_scope"], item["held_long_pressure"], item["mechanism"], normalize_evidence(item["evidence_span"])))
        records_by_symbol[item["symbol"]].append(item)
    for items in records_by_symbol.values():
        items.sort(key=lambda item: (item["available_ms"], item["headline_id"]))

    state_rows: list[dict[str, Any]] = []
    for row in rows:
        stamp = int(row["decision_time"])
        symbol = row["features"]["symbol"]
        active = [item for item in records_by_symbol[symbol] if 0 <= stamp - item["available_ms"] < 72 * 60 * 60 * 1000]
        domains = {item["source_domain"] for item in active}
        adverse_mass = supportive_mass = adverse_h4 = supportive_h4 = 0.0
        applicable = adverse_items = supportive_items = 0
        stage_score: dict[str, float] = defaultdict(float)
        mechanism_score: dict[str, float] = defaultdict(float)
        prior_signatures = set()
        novel_signatures = set()
        for item in active:
            age_h = (stamp - item["available_ms"]) / 3_600_000
            remaining = decay_mass(item, age_h)
            weight = float(item["confidence"]) * SCOPE_WEIGHT[item["affected_asset_scope"]] * remaining
            if SCOPE_WEIGHT[item["affected_asset_scope"]] > 0:
                applicable += 1
            if item["available_ms"] < stamp:
                prior_signatures.add(item["signature"])
            elif item["signature"] not in prior_signatures:
                novel_signatures.add(item["signature"])
            if item["held_long_pressure"] == "adverse" and weight > 0:
                adverse_items += 1
                adverse_mass += weight
                adverse_h4 += weight * float(item["horizon_mass"]["h4"])
                stage_score[item["event_stage"]] += weight
                mechanism_score[item["mechanism"]] += weight
            if item["held_long_pressure"] == "supportive" and weight > 0:
                supportive_items += 1
                supportive_mass += weight
                supportive_h4 += weight * float(item["horizon_mass"]["h4"])
                stage_score[item["event_stage"]] += weight
                mechanism_score[item["mechanism"]] += weight
        dominant = lambda scores: max(scores, key=lambda key: (scores[key], key)) if scores else "unknown"
        state_rows.append({
            "row_id": row["row_id"], "trade_id": row["trade_id"], "decision_time": stamp,
            "decision_time_iso": row["decision_time_iso"], "symbol": symbol,
            "text_state": {
                "active_headline_count": len(active), "source_domain_count": len(domains),
                "applicable_headline_count": applicable, "adverse_headline_count": adverse_items,
                "supportive_headline_count": supportive_items, "adverse_mass": adverse_mass,
                "supportive_mass": supportive_mass, "adverse_h4_mass": adverse_h4,
                "supportive_h4_mass": supportive_h4, "dominant_stage": dominant(stage_score),
                "dominant_mechanism": dominant(mechanism_score),
                "novel_signature_count": len(novel_signatures),
                "text_available_this_bar": any(item["available_ms"] <= stamp and item["available_ms"] > stamp - FOUR_H_MS for item in active),
            },
        })

    power = config["power_gate"]
    all_values = [(row["trade_id"], float(row["target"]["net_action_value"])) for row in rows]
    active_ids = {row["row_id"] for row in state_rows if row["text_state"]["applicable_headline_count"] > 0}
    active_values = [(row["trade_id"], float(row["target"]["net_action_value"])) for row in rows if row["row_id"] in active_ids]
    new_text_ids = {row["row_id"] for row in state_rows if row["text_state"]["text_available_this_bar"]}
    adverse_ids = {row["row_id"] for row in state_rows if row["text_state"]["adverse_mass"] >= power["minimum_adverse_mass"]}
    overlay_costs = [float(row["target"]["overlay_cost"]) for row in rows]
    baseline_mde = (1.96 + 0.84) * cluster_se(all_values)
    active_mde = (1.96 + 0.84) * cluster_se(active_values)
    counts = {
        "panel_decisions": len(rows), "panel_trade_clusters": len({row["trade_id"] for row in rows}),
        "extraction_records": len(records), "deduplicated_headline_ids": len(seen_ids),
        "new_text_decisions": len(new_text_ids), "new_text_trade_clusters": len({row["trade_id"] for row in state_rows if row["row_id"] in new_text_ids}),
        "active_applicable_decisions": len(active_ids), "active_applicable_trade_clusters": len({row["trade_id"] for row in state_rows if row["row_id"] in active_ids}),
        "adverse_active_decisions": len(adverse_ids), "adverse_active_trade_clusters": len({row["trade_id"] for row in state_rows if row["row_id"] in adverse_ids}),
    }
    economic_mde = statistics.median(overlay_costs)
    checks = {
        "panel_clusters": counts["panel_trade_clusters"] >= power["minimum_panel_trade_clusters"],
        "text_trade_clusters": counts["new_text_trade_clusters"] >= power["minimum_text_trade_clusters"],
        "new_text_decisions": counts["new_text_decisions"] >= power["minimum_new_text_decisions"],
        "applicable_trade_clusters": counts["active_applicable_trade_clusters"] >= power["minimum_applicable_trade_clusters"],
        "economic_mde": baseline_mde <= economic_mde,
    }
    state_payload = {
        "schema_version": "tech-llm-conditional-state-v3.1", "status": "outcome-blind-text-state-materialized",
        "generated_at": datetime.now(timezone.utc).isoformat(), "outcomes_consulted": False,
        "deduplication": "Exact headline_id only; no semantic multi-domain event clustering was applied.",
        "forward_decay": "At a later bar, retain only horizon mass whose horizon exceeds elapsed time; no future text is used.",
        "rows": state_rows,
        "inputs": {"extraction": {"path": str(args.extraction.resolve()), "sha256": sha256(args.extraction)}, "panel": {"path": str(args.panel.resolve()), "sha256": sha256(args.panel)}},
    }
    write(args.state_output, state_payload)
    audit_payload = {
        "schema_version": "tech-llm-conditional-state-stage-b-power-audit-v3.1",
        "status": "stage-b-power-pass-freeze-authorized" if all(checks.values()) else "stage-b-insufficient-data-stop-before-model-fit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_role": "Post-outcome exploratory feasibility only; no T1/T2/T3 fit, policy mapping or performance evaluation was performed.",
        "counts": counts,
        "planning_diagnostic": {
            "all_decision_cluster_robust_se": cluster_se(all_values), "all_decision_mde_80pct_two_sided_5pct": baseline_mde,
            "applicable_text_cluster_robust_se": cluster_se(active_values), "applicable_text_mde_80pct_two_sided_5pct": active_mde,
            "median_one_bar_overlay_cost": economic_mde,
            "warning": "MDE is an observed-variance planning diagnostic. It does not account for model estimation error, selection uncertainty or policy sparsity and is not a HYB-003 performance result.",
        },
        "thresholds": power, "checks": checks, "passed": all(checks.values()),
        "outcomes_consulted": True, "model_fit_performed": False, "performance_evaluation_performed": False,
        "inputs": {"config": {"path": str(args.config.resolve()), "sha256": sha256(args.config)}, "state": {"path": str(args.state_output.resolve()), "sha256": sha256(args.state_output)}},
    }
    write(args.audit_output, audit_payload)
    print(json.dumps({"state": str(args.state_output), "audit": str(args.audit_output), "passed": audit_payload["passed"], "counts": counts, "checks": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
