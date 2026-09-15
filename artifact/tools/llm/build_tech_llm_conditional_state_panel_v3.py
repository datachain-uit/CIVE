"""Materialize the Stage-A HYB-003 Tech-state panel and text extraction inputs.

The builder is post-outcome exploratory infrastructure.  It does not fit a
model, choose a policy, or evaluate HYB-003 performance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audit_tech_llm_intratrade_shock_shield_v2_replay import (
    FEE_RATE, FOUR_H_MS, SLIP_RATE, atr, lifecycle, load_market, read_json,
    replay_shadow, sha256, trade_id, verify_frozen_inputs, write_json,
)


def parse_ms(value: str) -> int:
    return int(datetime.fromisoformat(value).astimezone(timezone.utc).timestamp() * 1000)


def iso(stamp: int) -> str:
    return datetime.fromtimestamp(stamp / 1000, tz=timezone.utc).isoformat()


def safe_return(newer: float, older: float) -> float:
    return newer / older - 1 if older else 0.0


def features_at(
    series: list[list[float]], index: int, trade: dict[str, Any], replay_trade: dict[str, Any],
    peak_before: float, funding: dict[int, float],
) -> dict[str, float | int | str]:
    row = series[index]
    stamp, opening = int(row[0]), float(row[1])
    entry_index = next(i for i, candidate in enumerate(series) if int(candidate[0]) == int(trade["entry_time"]))
    active_stop = max(
        replay_trade["entry_price"] - 3.0 * replay_trade["entry_atr"],
        peak_before - 4.0 * replay_trade["entry_atr"],
    )
    prior_close = float(series[index - 1][4])

    def past_return(bars_back: int) -> float:
        older_index = index - 1 - bars_back
        return safe_return(prior_close, float(series[older_index][4])) if older_index >= 0 else 0.0

    def average_range(count: int) -> float:
        window = series[max(0, index - count):index]
        values = [(float(x[2]) - float(x[3])) / float(x[4]) for x in window if float(x[4])]
        return statistics.fmean(values) if values else 0.0

    prior_funding = [rate for time, rate in funding.items() if stamp - 86_400_000 <= time < stamp]
    return {
        "symbol": trade["symbol"],
        "trade_age_4h": index - entry_index,
        "open_to_raw_entry_return": safe_return(opening, replay_trade["raw_entry"]),
        "distance_to_active_stop_atr": (opening - active_stop) / replay_trade["entry_atr"],
        "entry_atr_over_open": replay_trade["entry_atr"] / opening,
        "past_return_4h": past_return(1),
        "past_return_12h": past_return(3),
        "past_return_24h": past_return(6),
        "past_average_range_12h": average_range(3),
        "past_average_range_24h": average_range(6),
        "last_observed_funding_rate": prior_funding[-1] if prior_funding else 0.0,
        "past_funding_sum_24h": sum(prior_funding),
    }


def counterfactual_label(
    stamp: int, trade: dict[str, Any], replay_trade: dict[str, Any],
    bars: dict[int, list[float]], funding: dict[int, float], denominator: float,
) -> dict[str, float | int | bool]:
    end = stamp + FOUR_H_MS
    if end > int(trade["exit_time"]):
        raise ValueError("eligible decision extends beyond shadow exit")
    half = 0.5 * replay_trade["quantity"]
    raw_sell = float(bars[stamp][1])
    sell_fill = raw_sell * (1 - SLIP_RATE)
    rebalance_at_end = end == int(trade["exit_time"]) and trade["reason"] == "rebalance"
    if rebalance_at_end:
        raw_end = replay_trade["raw_exit"]
        end_fill = raw_end * (1 - SLIP_RATE)
        net_dollars = half * (sell_fill - end_fill)
        net_dollars += -half * sell_fill * FEE_RATE + half * end_fill * FEE_RATE
        overlay_cost = half * sell_fill * FEE_RATE - half * end_fill * FEE_RATE
    else:
        raw_end = float(bars[end][1])
        end_fill = raw_end * (1 + SLIP_RATE)
        net_dollars = half * (sell_fill - end_fill)
        net_dollars -= half * (sell_fill + end_fill) * FEE_RATE
        overlay_cost = half * (raw_sell + raw_end) * (SLIP_RATE + FEE_RATE)
    saved_funding = sum(
        half * float(bars[time][4]) * rate
        for time, rate in funding.items() if stamp <= time < end
    )
    net_dollars += saved_funding
    gross_dollars = half * (raw_sell - raw_end)
    return {
        "window_end": end,
        "rebalance_exit_at_window_end": rebalance_at_end,
        "gross_action_value": gross_dollars / denominator,
        "net_action_value": net_dollars / denominator,
        "funding_saved": saved_funding / denominator,
        "overlay_cost": overlay_cost / denominator,
    }


def cluster_robust_se(values: list[tuple[str, float]]) -> float:
    mean = statistics.fmean(value for _, value in values)
    groups: dict[str, float] = {}
    for key, value in values:
        groups[key] = groups.get(key, 0.0) + value - mean
    count, clusters = len(values), len(groups)
    if clusters < 2:
        return math.inf
    variance = clusters / (clusters - 1) * sum(total * total for total in groups.values()) / (count * count)
    return math.sqrt(variance)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--hyb2-predeclared", type=Path, default=root / "paper/input/results/hybrid/tech_llm_intratrade_shock_shield_v2_predeclared.json")
    parser.add_argument("--panel", type=Path, default=root / "paper/input/results/hybrid/tech_llm_conditional_state_fusion_v3_panel.json")
    parser.add_argument("--text-inputs", type=Path, default=root / "paper/input/results/hybrid/tech_llm_conditional_state_fusion_v3_text_inputs.json")
    parser.add_argument("--audit", type=Path, default=root / "paper/input/results/hybrid/tech_llm_conditional_state_fusion_v3_data_power_audit.json")
    args = parser.parse_args()

    frozen = read_json(args.hyb2_predeclared)
    verify_frozen_inputs(frozen)
    tech = read_json(Path(frozen["inputs"]["tech_result"]["path"]))
    trades = lifecycle(frozen, tech)
    market_rows, bars, funding = load_market(frozen)
    shadow = replay_shadow(trades, market_rows, bars, funding)
    replayed = {row["trade_id"]: row for row in shadow["trades"]}
    indexes = {symbol: {int(row[0]): i for i, row in enumerate(series)} for symbol, series in market_rows.items()}

    trade_start_equity: dict[str, float] = {}
    equity = 10_000.0
    for item in shadow["trades"]:
        trade_start_equity[item["trade_id"]] = equity
        equity += item["net_pnl"]

    panel_rows = []
    decision_context: dict[int, dict[str, Any]] = {}
    for trade in trades:
        tid, symbol = trade_id(trade), trade["symbol"]
        replay_trade = replayed[tid]
        entry_index = indexes[symbol][int(trade["entry_time"])]
        replay_trade["entry_atr"] = atr(market_rows[symbol], entry_index)
        peak = replay_trade["entry_price"]
        for index in range(entry_index, indexes[symbol][int(trade["exit_time"])]):
            stamp = int(market_rows[symbol][index][0])
            if stamp > int(trade["entry_time"]):
                row_id = hashlib.sha256(f"{tid}|{stamp}".encode()).hexdigest()
                feature_row = features_at(
                    market_rows[symbol], index, trade, replay_trade, peak, funding.get(symbol, {})
                )
                label = counterfactual_label(
                    stamp, trade, replay_trade, bars[symbol], funding.get(symbol, {}),
                    trade_start_equity[tid],
                )
                panel_rows.append({
                    "row_id": row_id, "trade_id": tid, "decision_time": stamp,
                    "decision_time_iso": iso(stamp), "features": feature_row, "target": label,
                })
                decision_context[stamp] = {"trade_id": tid, "symbol": symbol, "decision_time_iso": iso(stamp)}
            peak = max(peak, float(market_rows[symbol][index][2]))

    raw_inputs = read_json(Path(frozen["inputs"]["extraction_inputs"]["path"]))
    text_rows = []
    for source in raw_inputs["records"]:
        available = parse_ms(source["available_at"])
        decision = ((available + FOUR_H_MS - 1) // FOUR_H_MS) * FOUR_H_MS
        context = decision_context.get(decision)
        if context is None or not (decision - FOUR_H_MS < available <= decision):
            continue
        context_id = hashlib.sha256(f"{context['trade_id']}|{decision}|{source['headline_id']}".encode()).hexdigest()
        text_rows.append({
            "context_id": context_id, **context,
            "headline_id": source["headline_id"], "available_at": source["available_at"],
            "source_domain": source["source_domain"], "headline": source["headline"],
        })

    panel_payload = {
        "schema_version": "tech-llm-conditional-state-fusion-v3-panel",
        "status": "post-outcome-development-panel-not-model-evaluation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": panel_rows,
    }
    text_payload = {
        "schema_version": "tech-llm-conditional-state-fusion-v3-text-inputs",
        "status": "outcome-blind-extraction-inputs-pending-schema-and-reliability-gate",
        "selection_rule": "All raw headlines first available in the preceding 4h interval for an eligible post-entry Tech decision; no market outcome used in headline selection.",
        "forbidden_model_inputs": ["future prices", "counterfactual target", "trade PnL", "HYB-003 outcome"],
        "required_output_fields": [
            "affected_asset_scope", "held_long_pressure", "mechanism", "event_stage",
            "horizon_mass_4h_12h_24h_72h", "novelty", "confidence", "evidence_span",
        ],
        "records": text_rows,
    }
    write_json(args.panel, panel_payload)
    write_json(args.text_inputs, text_payload)

    label_values = [(row["trade_id"], float(row["target"]["net_action_value"])) for row in panel_rows]
    se = cluster_robust_se(label_values)
    clusters = len({key for key, _ in label_values})
    audit_payload = {
        "schema_version": "tech-llm-conditional-state-fusion-v3-data-power-audit",
        "status": "STAGE_A_TECH_PANEL_MATERIALIZED_STAGE_B_POWER_DIAGNOSTIC_ONLY",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_role": "post-outcome development feasibility; no HYB-003 model or policy was fit",
        "counts": {
            "frozen_trades": len(trades), "eligible_trade_clusters": clusters,
            "eligible_post_entry_4h_rows": len(panel_rows),
            "outcome_blind_text_context_rows": len(text_rows),
            "decision_rows_with_new_text": len({row["decision_time_iso"] for row in text_rows}),
        },
        "integrity": {
            "shadow_max_abs_component_error": shadow["max_abs_component_error"],
            "unique_panel_row_ids": len({row["row_id"] for row in panel_rows}) == len(panel_rows),
            "unique_text_context_ids": len({row["context_id"] for row in text_rows}) == len(text_rows),
            "text_selection_used_outcomes": False,
            "model_fit_performed": False,
            "performance_evaluation_performed": False
        },
        "planning_diagnostic": {
            "cluster_robust_standard_error_of_always_downsize_net_action_value": se,
            "normal_approximation_mde_80pct_power_two_sided_5pct": (1.96 + 0.84) * se,
            "warning": "This observed-variance MDE is a planning diagnostic, not a HYB-003 result. Policy sparsity and model estimation error can make actual power worse.",
            "power_gate_decision": "PENDING_ECONOMIC_MDE_AND_TEXT_PREVALENCE_FREEZE"
        },
        "files": {
            "panel": {"path": str(args.panel.resolve()), "sha256": sha256(args.panel)},
            "text_inputs": {"path": str(args.text_inputs.resolve()), "sha256": sha256(args.text_inputs)},
            "builder": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).resolve())},
            "hyb2_predeclared": {"path": str(args.hyb2_predeclared.resolve()), "sha256": sha256(args.hyb2_predeclared)},
        },
        "next_gate": "Freeze and test a text-state extraction schema on an outcome-blind reliability sample before any HYB-003 model fit."
    }
    write_json(args.audit, audit_payload)
    print(json.dumps({"audit": str(args.audit), **audit_payload["counts"], **audit_payload["planning_diagnostic"]}, indent=2))


if __name__ == "__main__":
    main()
