"""Outcome-free sample and assignment audit for HYB-009 model substitution."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = {
    "finbert": ROOT / "results/llm_daily_full_finbert_v1_development.json",
    "cryptobert": ROOT / "paper/input/results/llm/llm_cryptobert_full_v1_development.json",
    "ministral_direct": ROOT / "runtime/ministral3_8b_challenger/results/llm_daily_full_ministral3_8b_v1_development.json",
}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def bearish_percentile(history: list[float], current: float) -> float:
    return (sum(x > current for x in history) + 0.5 * sum(x == current for x in history)) / len(history)

def main() -> None:
    source = ROOT / "paper/input/results/hybrid/tech_llm_conditional_overlay_v1_predeclared.json"
    opportunities = json.loads(source.read_text(encoding="utf-8"))["feature_audit"]
    assignments, diagnostics, checks = {}, {}, {"opportunities_are_24": len(opportunities) == 24}
    for name, path in MODELS.items():
        records = json.loads(path.read_text(encoding="utf-8"))["records"]
        rows = sorted((r for r in records if r.get("status") == "success"), key=lambda r: r["information_date"])
        by_date = {r["information_date"]: r for r in rows}
        arm, audit = {}, []
        for opportunity in opportunities:
            date = opportunity["information_date"]
            entry = datetime.fromisoformat(opportunity["entry_time_iso"])
            start = (entry - timedelta(days=365)).date().isoformat()
            history = [float(r["score"]) for r in rows if start <= r["information_date"] < date and datetime.fromisoformat(r["available_at"]) <= entry]
            current = by_date.get(date)
            if current is None or datetime.fromisoformat(current["available_at"]) > entry or len(history) < 180:
                continue
            risk = bearish_percentile(history, float(current["score"]))
            weight = 0.0 if risk >= 0.85 else (0.5 if risk >= 0.70 else 1.0)
            key = f"{opportunity['entry_time']}::{opportunity['symbol']}"
            arm[key] = weight
            audit.append({"key": key, "information_date": date, "score": float(current["score"]), "history_n": len(history), "bearish_percentile": risk, "weight": weight})
        assignments[name] = arm
        active = sum(v < 1 for v in arm.values())
        diagnostics[name] = {"covered": len(arm), "active": active, "veto": sum(v == 0 for v in arm.values()), "downsize": sum(v == 0.5 for v in arm.values()), "rows": audit}
        checks[name + "_coverage_24"] = len(arm) == 24
        checks[name + "_active_at_least_6"] = active >= 6
    payload = {
        "schema_version": 1, "experiment_id": "HYB-009-model-substitution-family",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "outcomes_consulted_by_audit": False,
        "policy": {"calibration": "trailing 365 calendar days, available before entry, minimum 180 observations", "risk": "empirical lower-tail percentile of raw bullish score", "confirm": "<0.70", "downsize": "[0.70,0.85)", "veto": ">=0.85"},
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks, "diagnostics": diagnostics, "assignments": assignments,
        "sources": {"opportunities": {"path": str(source), "sha256": sha(source)}, **{n: {"path": str(p), "sha256": sha(p)} for n,p in MODELS.items()}},
    }
    out = ROOT / "paper/input/results/hybrid/hyb009_model_substitution_sample_audit.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "diagnostics": {n:{k:v for k,v in d.items() if k!="rows"} for n,d in diagnostics.items()}, "checks": checks}, indent=2))

if __name__ == "__main__":
    main()
