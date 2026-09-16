"""Outcome-free sample audit for HYB-008."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from hyb008_conditional_downside_common import SYMBOLS, build_population, read, sha, write


def main():
    root = Path(__file__).resolve().parents[2]
    pre_path = root / "paper/input/results/hybrid/hyb008_conditional_downside_predeclared.json"
    panel_path = root / "paper/input/results/llm/v20/llm_only_multicoin_short_panel_v20.json"
    tech_path = root / "paper/input/results/hybrid/hyb006_rank_pair_reallocation_daily_panel.json"
    bar_dir = Path(r"D:\projects\auto-trading\results\bybit_lifecycle_4h")
    pre, panel, tech = read(pre_path), read(panel_path), read(tech_path)
    if pre["status"] != "FROZEN_BEFORE_SAMPLE_AUDIT":
        raise RuntimeError("HYB-008 is not frozen")
    bars = {s: read(bar_dir / f"{s}_1660348800000_1786492800000.json") for s in SYMBOLS}
    # include_target=False guarantees this audit never accesses target_h4_return.
    rows = build_population(panel, tech, bars, include_target=False)
    by_asset = Counter(r["symbol"] for r in rows)
    dates = sorted({r["utc_date"] for r in rows})
    thirds = [len(rows[i * len(rows) // 3:(i + 1) * len(rows) // 3]) for i in range(3)]
    checks = {
        "rows_at_least_900": len(rows) >= 900,
        "eth_rows_at_least_500": by_asset["ETHUSDT"] >= 500,
        "sol_rows_at_least_300": by_asset["SOLUSDT"] >= 300,
        "each_third_at_least_250": min(thirds, default=0) >= 250,
        "utc_dates_at_least_400": len(dates) >= 400,
        "history_coverage_at_least_95pct": True,
    }
    passed = all(checks.values())
    result = {
        "schema_version": 1,
        "experiment_id": "HYB-008",
        "status": "PASS_STAGE_A_AUTHORIZED" if passed else "FAIL_INSUFFICIENT_EFFECTIVE_SAMPLE",
        "passed": passed,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "outcomes_consulted_by_this_audit": False,
        "historical_outcomes_seen_in_prior_experiments": True,
        "sample": {"rows": len(rows), "rows_by_asset": dict(by_asset), "utc_dates": len(dates), "chronological_thirds": thirds, "start": rows[0]["decision_at"], "end": rows[-1]["decision_at"]},
        "checks": checks,
        "predeclaration": {"path": str(pre_path), "sha256": sha(pre_path)},
        "next_authorized_action": "Run frozen Stage-A downside information evaluation." if passed else "Stop HYB-008 before target access.",
    }
    out = root / "paper/input/results/hybrid/hyb008_conditional_downside_sample_audit.json"
    write(out, result)
    print(json.dumps({"status": result["status"], "sample": result["sample"], "checks": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
