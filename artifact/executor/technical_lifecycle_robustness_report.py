"""Consolidate lifecycle robustness artifacts into one auditable report."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

def _load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))

def main() -> None:
    grid = _load("technical_lifecycle_robustness_v2.json")
    base = _load("technical_bybit_lifecycle_1x_candidate_hardened.json")
    contributions = [{"symbol": s, "net_pnl": p} for s, p in base["symbol_contribution"].items()]
    contributions.sort(key=lambda row: row["net_pnl"], reverse=True)
    positive_total = sum(max(0, row["net_pnl"]) for row in contributions)
    for row in contributions:
        row["positive_pnl_share_pct"] = round(100 * max(0, row["net_pnl"]) / positive_total, 4)
    hhi = sum((max(0, row["net_pnl"]) / positive_total) ** 2 for row in contributions)
    cost_sweep = []
    for bps in (5, 25, 50, 100, 150, 175, 200):
        payload = base if bps == 5 else _load(f"lifecycle_cost_sweep_v2_{bps}bps.json")
        cost_sweep.append({
            "adverse_execution_bps_per_side": bps,
            "fee_bps_per_side": payload["protocol"]["fee_bps"],
            "return_pct": payload["result"]["return_pct"],
            "max_drawdown_pct": payload["result"]["max_drawdown_pct"],
            "positive_folds": payload["positive_folds"],
        })
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "robustness evidence for frozen candidate; not a new selection or sealed holdout",
        "candidate": grid["candidate"],
        "parameter_neighbourhood": grid["neighbourhood_top1"],
        "selection_risk": grid["selection_risk"],
        "candidate_train_rank_among_eligible": grid["candidate_train_rank_among_eligible"],
        "pnl_decomposition": base["pnl_decomposition"],
        "exit_reasons": base["exit_reasons"],
        "asset_concentration": {
            "assets_with_closed_trades": len(contributions),
            "positive_contribution_hhi": round(hhi, 6),
            "contributions": contributions,
        },
        "cost_sweep": cost_sweep,
        "empirical_breakeven_bracket": {
            "last_positive_adverse_execution_bps_per_side": 150,
            "first_negative_adverse_execution_bps_per_side": 175,
            "fee_bps_per_side": 6,
            "note": "Bracket only; no interpolation claim because position sizing compounds path-dependently.",
        },
        "limitations": [
            "All 54 configurations and the final two folds have been inspected.",
            "DSR/PBO is reported separately from aligned daily returns and remains development-sample evidence.",
            "Asset contribution is concentrated and is not a leave-one-asset-out rerun.",
            "No new sealed holdout exists.",
        ],
    }
    output = RESULTS / "technical_lifecycle_robustness_report_v2.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
