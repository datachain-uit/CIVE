"""Audit the frozen lifecycle candidate without selecting a new winner."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _name(top_n: int, rank: int, stop: float, trail: float) -> str:
    clean = lambda value: str(value).replace(".", "p")
    return f"top{top_n}_rank{rank}_stop{clean(stop)}_trail{clean(trail)}"


def _run(root: Path, output: Path, top_n: int, rank: int, stop: float, trail: float) -> dict:
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        protocol = existing.get("protocol", {})
        if (
            protocol.get("execution_semantics") == "open_funding_intrabar_v2"
            and protocol.get("top_n") == top_n and protocol.get("rank_days") == rank
            and protocol.get("stop_atr") == stop and protocol.get("trail_atr") == trail
            and existing.get("daily_returns")
        ):
            return existing
    command = [
        sys.executable, str(root / "executor" / "technical_bybit_lifecycle_execution.py"),
        "--top-n", str(top_n), "--rank-days", str(rank), "--gross-leverage", "1",
        "--stop-atr", str(stop), "--trail-atr", str(trail), "--output", str(output),
    ]
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr[-4000:])
    return json.loads(output.read_text(encoding="utf-8"))


def _fold_compound(folds: list[dict]) -> float:
    return (math.prod(1 + fold["return_pct"] / 100 for fold in folds) - 1) * 100


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("results/lifecycle_grid_v2"))
    parser.add_argument("--output", type=Path, default=Path("results/technical_lifecycle_robustness_v2.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    configurations = [
        (top_n, rank, stop, trail)
        for top_n in (1, 2) for rank in (10, 20, 40)
        for stop in (2.0, 2.5, 3.0) for trail in (2.5, 3.0, 4.0)
    ]
    for index, (top_n, rank, stop, trail) in enumerate(configurations, 1):
        name = _name(top_n, rank, stop, trail)
        print(f"[{index}/{len(configurations)}] {name}", flush=True)
        payload = _run(root, output_dir / f"{name}.json", top_n, rank, stop, trail)
        train, inspected = payload["walk_forward_folds"][:6], payload["walk_forward_folds"][6:]
        records.append({
            "name": name, "top_n": top_n, "rank_days": rank,
            "stop_atr": stop, "trail_atr": trail,
            "train_compounded_return_pct": round(_fold_compound(train), 4),
            "train_positive_folds": sum(f["return_pct"] > 0 for f in train),
            "inspected_compounded_return_pct": round(_fold_compound(inspected), 4),
            "inspected_positive_folds": sum(f["return_pct"] > 0 for f in inspected),
            **payload["result"],
        })
    candidate_name = _name(1, 20, 3.0, 4.0)
    candidate = next(record for record in records if record["name"] == candidate_name)
    eligible = [r for r in records if r["train_positive_folds"] >= 4]
    train_rank = 1 + sum(r["train_compounded_return_pct"] > candidate["train_compounded_return_pct"] for r in eligible)
    neighbourhood = [r for r in records if r["top_n"] == 1]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "robustness audit only; candidate is frozen and not reselected",
        "execution_semantics": "open_funding_intrabar_v2",
        "candidate": candidate,
        "candidate_train_rank_among_eligible": f"{train_rank}/{len(eligible)}",
        "neighbourhood_top1": {
            "configurations": len(neighbourhood),
            "positive_full_return": sum(r["return_pct"] > 0 for r in neighbourhood),
            "positive_inspected_period": sum(r["inspected_compounded_return_pct"] > 0 for r in neighbourhood),
            "median_return_pct": round(sorted(r["return_pct"] for r in neighbourhood)[len(neighbourhood)//2], 4),
            "min_return_pct": min(r["return_pct"] for r in neighbourhood),
            "max_return_pct": max(r["return_pct"] for r in neighbourhood),
        },
        "selection_risk": {
            "configurations_tested": len(records),
            "eligible_on_train_gate": len(eligible),
            "warning": "54 configurations were inspected; raw winner performance is selection-biased. See technical_selection_inference_v2.json for exploratory DSR/PBO on the aligned daily return matrix.",
        },
        "records": records,
    }
    output = root / args.output
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("candidate", "candidate_train_rank_among_eligible", "neighbourhood_top1", "selection_risk")}, indent=2))


if __name__ == "__main__":
    main()
