"""Outcome-free effective-sample audit for historical HYB-007."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RISK_TYPES = ("exchange_security", "fraud_legal", "network_protocol", "liquidation_leverage")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def effective_selection(rows):
    return {(date.fromisoformat(r["information_date"]) + timedelta(days=1)).isoformat(): set(r["selected"]) for r in rows}


def qualifies(features, direction="negative") -> bool:
    return (
        float(features.get(f"llm_direction_fraction::{direction}", 0)) >= 0.5
        and float(features.get("llm_severity_max", 0)) >= 0.7
        and float(features.get("llm_confidence_max", 0)) >= 0.8
        and sum(float(features.get(f"llm_event_type_fraction::{kind}", 0)) for kind in RISK_TYPES) > 0
    )


def cluster(triggers):
    groups = []
    for item in sorted(triggers, key=lambda x: (x["symbol"], x["decision_at"])):
        when = datetime.fromisoformat(item["decision_at"])
        if not groups or groups[-1]["symbol"] != item["symbol"] or when - datetime.fromisoformat(groups[-1]["end"]) > timedelta(hours=24):
            groups.append({"symbol": item["symbol"], "start": item["decision_at"], "end": item["decision_at"], "triggers": 1})
        else:
            groups[-1]["end"] = item["decision_at"]
            groups[-1]["triggers"] += 1
    return sorted(groups, key=lambda x: x["start"])


def main():
    root = Path(__file__).resolve().parents[2]
    pre_path = root / "paper/input/results/hybrid/hyb007_historical_risk_attenuation_predeclared.json"
    panel_path = root / "paper/input/results/llm/v20/llm_only_multicoin_short_panel_v20.json"
    tech_path = root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_daily_panel.json"
    pre, panel, tech = read(pre_path), read(panel_path), read(tech_path)
    if pre["status"] != "FROZEN_BEFORE_HYB007_EVALUATION":
        raise RuntimeError("HYB-007 historical design is not frozen")
    selection = effective_selection(tech["rows"])
    triggers = []
    for symbol, asset in panel["assets"].items():
        for row in asset["records"]:
            # Deliberately do not access row['target_h4_return'] in this audit.
            when = datetime.fromisoformat(row["decision_at"]).astimezone(timezone.utc)
            features = row["features"]["event"]
            if symbol in selection.get(when.date().isoformat(), set()) and qualifies(features):
                triggers.append({"symbol": symbol, "decision_at": when.isoformat(), "features": features})
    groups = cluster(triggers)
    thirds = [len(groups[i * len(groups) // 3:(i + 1) * len(groups) // 3]) for i in range(3)]
    by_asset = Counter(g["symbol"] for g in groups)
    span = (datetime.fromisoformat(groups[-1]["start"]) - datetime.fromisoformat(groups[0]["start"])).days if groups else 0
    checks = {
        "qualifying_buckets_at_least_120": len(triggers) >= 120,
        "independent_clusters_at_least_60": len(groups) >= 60,
        "each_third_at_least_15": min(thirds, default=0) >= 15,
        "eth_and_sol_each_at_least_20_clusters": all(by_asset[s] >= 20 for s in ("ETHUSDT", "SOLUSDT")),
        "coverage_at_least_720_days": span >= 720,
    }
    passed = all(checks.values())
    output = {
        "schema_version": 1,
        "experiment_id": "HYB-007",
        "status": "PASS_EVALUATION_AUTHORIZED" if passed else "FAIL_INSUFFICIENT_EFFECTIVE_SAMPLE",
        "passed": passed,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "outcomes_consulted_by_this_audit": False,
        "historical_outcomes_seen_in_prior_experiments": True,
        "sample": {"qualifying_buckets": len(triggers), "independent_clusters": len(groups), "clusters_by_asset": dict(by_asset), "chronological_thirds": thirds, "coverage_days": span},
        "checks": checks,
        "clusters": groups,
        "inputs": {"predeclaration": {"path": str(pre_path), "sha256": sha(pre_path)}, "v20_panel": {"path": str(panel_path), "sha256": sha(panel_path)}, "tech_assignments": {"path": str(tech_path), "sha256": sha(tech_path)}},
        "next_authorized_action": "Run the frozen historical evaluation." if passed else "Stop HYB-007 without evaluation.",
    }
    write(root / "paper/input/results/hybrid/hyb007_historical_risk_attenuation_sample_audit.json", output)
    print(json.dumps({k: output[k] for k in ("status", "sample", "checks")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
