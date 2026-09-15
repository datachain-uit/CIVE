"""Post-evaluation descriptive risk audit for HYB-009 v1.1.

This audit does not alter the frozen economic gate. It separates mechanical
exposure reduction from model-selective risk attenuation by comparing each
primary arm with Tech, its shuffled-weight placebo, and constant 0.75 sizing.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "paper/input/results/hybrid/hyb009_model_substitution_v1_1_evaluation.json"
OUTPUT = ROOT / "paper/input/results/hybrid/hyb009_model_substitution_v1_1_risk_audit.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(returns: list[float]) -> dict[str, float | int]:
    equity = peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, 1.0 - equity / peak)
    tail_n = max(1, math.ceil(0.10 * len(returns)))
    ordered = sorted(returns)
    return {
        "n": len(returns),
        "compounded_return": equity - 1.0,
        "closed_trade_max_drawdown": max_drawdown,
        "es10_trade_return": sum(ordered[:tail_n]) / tail_n,
        "worst_trade_return": ordered[0],
        "tail_trade_count": tail_n,
    }


def main() -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    output: dict = {
        "schema_version": 1,
        "experiment_id": "HYB-009-v1.1-post-evaluation-risk-audit",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETE",
        "scope": "post-outcome descriptive audit; not a predeclared risk gate, validation, holdout, or live evidence",
        "interpretation_rule": "Risk improvement relative to Tech is insufficient by itself because every arm reduces exposure. Model-selective evidence additionally requires improvement over both shuffled weights and constant-0.75 sizing on the same metric; this is descriptive and not confirmatory.",
        "source": {"path": str(SOURCE), "sha256": sha256(SOURCE)},
        "models": {},
    }
    for name, arms in payload["results"].items():
        rows = arms["primary"]["paired_rows"]
        tech = metrics([float(row["tech_net_return"]) for row in rows])
        arm_metrics = {}
        for arm_name, arm in arms.items():
            arm_metrics[arm_name] = metrics([float(row["hybrid_net_return"]) for row in arm["paired_rows"]])
        primary = arm_metrics["primary"]
        shuffled = arm_metrics["shuffled"]
        constant = arm_metrics["constant_075"]
        selective = {
            "closed_trade_max_drawdown": (
                primary["closed_trade_max_drawdown"] < tech["closed_trade_max_drawdown"]
                and primary["closed_trade_max_drawdown"] < shuffled["closed_trade_max_drawdown"]
                and primary["closed_trade_max_drawdown"] < constant["closed_trade_max_drawdown"]
            )
        }
        # Tail-return metrics are better when they are less negative (numerically greater).
        for metric in ("es10_trade_return", "worst_trade_return"):
            selective[metric] = (
                primary[metric] > tech[metric]
                and primary[metric] > shuffled[metric]
                and primary[metric] > constant[metric]
            )
        output["models"][name] = {
            "tech": tech,
            "arms": arm_metrics,
            "primary_minus_tech": {
                "compounded_return": primary["compounded_return"] - tech["compounded_return"],
                "closed_trade_max_drawdown": primary["closed_trade_max_drawdown"] - tech["closed_trade_max_drawdown"],
                "es10_trade_return": primary["es10_trade_return"] - tech["es10_trade_return"],
                "worst_trade_return": primary["worst_trade_return"] - tech["worst_trade_return"],
            },
            "descriptive_model_selective_flags": selective,
        }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({n: {"primary_minus_tech": x["primary_minus_tech"], "selective": x["descriptive_model_selective_flags"]} for n, x in output["models"].items()}, indent=2))


if __name__ == "__main__":
    main()
