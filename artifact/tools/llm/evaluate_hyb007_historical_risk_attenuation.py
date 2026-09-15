"""Evaluate frozen HYB-007 on historical 4h data after sample PASS."""
from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from audit_hyb007_historical_risk_attenuation import cluster, effective_selection, qualifies, read, sha, write

BAR = timedelta(hours=4)


def percentile(values, q):
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lo, hi = math.floor(position), math.ceil(position)
    return ordered[lo] if lo == hi else ordered[lo] * (hi - position) + ordered[hi] * (position - lo)


def bootstrap_ci(values, seed, draws=10000):
    rng = random.Random(seed)
    means = [sum(values[rng.randrange(len(values))] for _ in values) / len(values) for _ in range(draws)]
    return [percentile(means, 0.025), percentile(means, 0.975)]


def es10(values):
    n = max(1, math.ceil(len(values) * 0.10))
    return sum(sorted(values)[:n]) / n


def selected_triggers(panel, selection, direction):
    output = []
    for symbol, asset in panel["assets"].items():
        for row in asset["records"]:
            when = datetime.fromisoformat(row["decision_at"]).astimezone(timezone.utc)
            if symbol in selection.get(when.date().isoformat(), set()) and qualifies(row["features"]["event"], direction):
                output.append({"symbol": symbol, "decision_at": when.isoformat()})
    return output


def hash_placebo(panel, selection, primary):
    primary_keys = {(r["symbol"], r["decision_at"]) for r in primary}
    desired = {symbol: sum(r["symbol"] == symbol for r in primary) for symbol in panel["assets"]}
    output = []
    for symbol, asset in panel["assets"].items():
        candidates = []
        for row in asset["records"]:
            when = datetime.fromisoformat(row["decision_at"]).astimezone(timezone.utc)
            key = (symbol, when.isoformat())
            if symbol in selection.get(when.date().isoformat(), set()) and key not in primary_keys:
                digest = hashlib.sha256(f"HYB007|{symbol}|{when.isoformat()}".encode()).hexdigest()
                candidates.append((digest, {"symbol": symbol, "decision_at": when.isoformat()}))
        output.extend(item for _, item in sorted(candidates)[:desired[symbol]])
    return output


def evaluate_clusters(triggers, bars, selection, cost_rate):
    by_symbol = {}
    for trigger in triggers:
        by_symbol.setdefault(trigger["symbol"], []).append(datetime.fromisoformat(trigger["decision_at"]))
    results = []
    for group in cluster(triggers):
        symbol = group["symbol"]
        start, last = datetime.fromisoformat(group["start"]), datetime.fromisoformat(group["end"])
        relevant = [t for t in by_symbol[symbol] if start <= t <= last]
        end = last + 3 * BAR
        current, delta_previous = start, 0.0
        tech_gross, llm_gross, extra_cost = [], [], 0.0
        while current < end:
            ms = int(current.timestamp() * 1000)
            if ms not in bars[symbol] or ms + 4 * 3600 * 1000 not in bars[symbol]:
                current += BAR
                continue
            active = symbol in selection.get(current.date().isoformat(), set())
            base = 0.5 if active else 0.0
            warning = active and any(t <= current < t + 3 * BAR for t in relevant)
            treated = 0.25 if warning else base
            delta_weight = treated - base
            extra_cost += abs(delta_weight - delta_previous) * cost_rate
            delta_previous = delta_weight
            r = float(bars[symbol][ms + 4 * 3600 * 1000][1]) / float(bars[symbol][ms][1]) - 1.0
            tech_gross.append(base * r)
            llm_gross.append(treated * r)
            current += BAR
        extra_cost += abs(delta_previous) * cost_rate
        if not tech_gross:
            continue
        tech_net = sum(tech_gross)
        llm_net = sum(llm_gross) - extra_cost
        results.append({
            "symbol": symbol,
            "start": group["start"],
            "end": end.isoformat(),
            "trigger_count": group["triggers"],
            "tech_cluster_return": tech_net,
            "llm_cluster_net_return": llm_net,
            "net_delta": llm_net - tech_net,
            "worst_bar_improvement": min(llm_gross) - min(tech_gross),
            "extra_turnover_cost": extra_cost,
        })
    return sorted(results, key=lambda x: x["start"])


def summarize(rows, seed):
    delta = [r["net_delta"] for r in rows]
    risk = [r["worst_bar_improvement"] for r in rows]
    tech = [r["tech_cluster_return"] for r in rows]
    llm = [r["llm_cluster_net_return"] for r in rows]
    folds = []
    for i in range(5):
        part = delta[i * len(delta) // 5:(i + 1) * len(delta) // 5]
        folds.append(sum(part) / len(part))
    return {
        "clusters": len(rows),
        "mean_net_delta": sum(delta) / len(delta),
        "net_delta_bootstrap_95_ci": bootstrap_ci(delta, seed),
        "fold_mean_net_deltas": folds,
        "positive_folds": sum(x > 0 for x in folds),
        "mean_worst_bar_improvement": sum(risk) / len(risk),
        "worst_bar_improvement_bootstrap_95_ci": bootstrap_ci(risk, seed + 1),
        "tech_cluster_es10": es10(tech),
        "llm_cluster_es10": es10(llm),
        "mean_extra_cost": sum(r["extra_turnover_cost"] for r in rows) / len(rows),
    }


def main():
    root = Path(__file__).resolve().parents[2]
    pre_path = root / "paper/input/results/hybrid/hyb007_historical_risk_attenuation_predeclared.json"
    audit_path = root / "paper/input/results/hybrid/hyb007_historical_risk_attenuation_sample_audit.json"
    panel_path = root / "paper/input/results/llm/v20/llm_only_multicoin_short_panel_v20.json"
    tech_path = root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_daily_panel.json"
    pre, audit, panel, tech = read(pre_path), read(audit_path), read(panel_path), read(tech_path)
    if audit.get("status") != "PASS_EVALUATION_AUTHORIZED" or not audit.get("passed"):
        raise RuntimeError("HYB-007 sample gate did not authorize evaluation")
    if audit["inputs"]["predeclaration"]["sha256"] != sha(pre_path):
        raise RuntimeError("predeclaration changed after sample audit")
    if pre["inputs"]["evaluation_script"]["sha256"] != sha(Path(__file__)):
        raise RuntimeError("evaluation script changed after freeze")
    selection = effective_selection(tech["rows"])
    primary = selected_triggers(panel, selection, "negative")
    supportive = selected_triggers(panel, selection, "positive")
    delayed = [{"symbol": r["symbol"], "decision_at": (datetime.fromisoformat(r["decision_at"]) + timedelta(hours=24)).isoformat()} for r in primary]
    hashed = hash_placebo(panel, selection, primary)
    bar_dir = root / "results/bybit_lifecycle_4h"
    bars = {}
    for symbol in panel["assets"]:
        path = bar_dir / f"{symbol}_1660348800000_1786492800000.json"
        bars[symbol] = {int(r[0]): r for r in read(path)}
    arms = {}
    panels = {}
    for i, (name, triggers) in enumerate((("primary", primary), ("delayed_24h", delayed), ("supportive_sign", supportive), ("metadata_hash_matched", hashed))):
        rows = evaluate_clusters(triggers, bars, selection, 10 / 10000)
        panels[name] = rows
        arms[name] = summarize(rows, 20260913 + i * 10)
    p = arms["primary"]
    placebo_names = ("delayed_24h", "supportive_sign", "metadata_hash_matched")
    economic_checks = {
        "net_delta_ci_lower_positive": p["net_delta_bootstrap_95_ci"][0] > 0,
        "positive_folds_at_least_3_of_5": p["positive_folds"] >= 3,
        "mean_net_delta_exceeds_placebos": all(p["mean_net_delta"] > arms[n]["mean_net_delta"] for n in placebo_names),
    }
    risk_checks = {
        "worst_bar_improvement_ci_lower_positive": p["worst_bar_improvement_bootstrap_95_ci"][0] > 0,
        "cluster_es10_improves": p["llm_cluster_es10"] > p["tech_cluster_es10"],
        "net_delta_noninferior_within_5bps": p["net_delta_bootstrap_95_ci"][0] > -0.0005,
        "worst_bar_improvement_exceeds_placebos": all(p["mean_worst_bar_improvement"] > arms[n]["mean_worst_bar_improvement"] for n in placebo_names),
    }
    economic_pass, risk_pass = all(economic_checks.values()), all(risk_checks.values())
    result = {
        "schema_version": 1,
        "experiment_id": "HYB-007",
        "status": "HISTORICAL_INCREMENTAL_VALUE_PASS" if economic_pass or risk_pass else "HISTORICAL_INCREMENTAL_VALUE_FAIL",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "research_role": pre["research_role"],
        "economic_increment_pass": economic_pass,
        "risk_control_increment_pass": risk_pass,
        "incremental_value_evidence": economic_pass or risk_pass,
        "arms": arms,
        "economic_checks": economic_checks,
        "risk_control_checks": risk_checks,
        "interpretation": "Economic and risk-control incremental value are separate claims; a risk PASS is not an alpha claim.",
        "predeclaration": {"path": str(pre_path), "sha256": sha(pre_path)},
        "sample_audit": {"path": str(audit_path), "sha256": sha(audit_path)},
    }
    panel_out = root / "paper/input/results/hybrid/hyb007_historical_risk_attenuation_cluster_panel.json"
    write(panel_out, {"schema_version": 1, "experiment_id": "HYB-007", "arms": panels})
    result["cluster_panel"] = {"path": str(panel_out), "sha256": sha(panel_out)}
    out = root / "paper/input/results/hybrid/hyb007_historical_risk_attenuation_evaluation.json"
    write(out, result)
    print(json.dumps({"status": result["status"], "economic_increment_pass": economic_pass, "risk_control_increment_pass": risk_pass, "primary": p, "economic_checks": economic_checks, "risk_control_checks": risk_checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
