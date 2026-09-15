"""Leave-one-asset-out and causal regime attribution for the frozen candidate."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DAY_MS = 86_400_000
FOLD_MS = 180 * DAY_MS

def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def _run(root: Path, output: Path, excluded: tuple[str, ...]) -> dict:
    command = [
        sys.executable, str(root / "executor" / "technical_bybit_lifecycle_execution.py"),
        "--top-n", "1", "--rank-days", "20", "--gross-leverage", "1",
        "--stop-atr", "3", "--trail-atr", "4", "--exclude-symbols", ",".join(excluded),
        "--output", str(output),
    ]
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr[-4000:])
    return _load(output)

def _latest_daily(cache_dir: Path, symbol: str) -> list[list[float]]:
    return _load(max(cache_dir.glob(f"{symbol}_*.json"), key=lambda p: p.stat().st_mtime))

def _regime_lookup(rows: list[list[float]]) -> tuple[dict[int, dict], float]:
    by_time = {int(row[0]): row for row in rows}
    ordered = sorted(by_time)
    volatilities = []
    lookup = {}
    for index, timestamp in enumerate(ordered):
        if index < 30:
            continue
        closes = [float(by_time[t][4]) for t in ordered[index - 30:index + 1]]
        returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        volatility = statistics.pstdev(returns) * math.sqrt(365)
        volatilities.append(volatility)
        return_14d = closes[-1] / closes[-15] - 1
        lookup[timestamp] = {"btc_return_14d": return_14d, "btc_volatility_30d": volatility}
    return lookup, statistics.median(volatilities)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("results/lifecycle_leave_one_out_v2"))
    parser.add_argument("--output", type=Path, default=Path("results/technical_lifecycle_concentration_regime_v2.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result_dir = root / args.output_dir
    result_dir.mkdir(parents=True, exist_ok=True)
    base = _load(root / "results" / "technical_bybit_lifecycle_1x_candidate_hardened.json")
    traded_assets = tuple(base["symbol_contribution"])
    exclusions = [(symbol,) for symbol in traded_assets] + [("XRPUSDT", "BTCUSDT")]
    leave_out = []
    for excluded in exclusions:
        label = "exclude_" + "_".join(excluded)
        print(label, flush=True)
        payload = _run(root, result_dir / f"{label}.json", excluded)
        leave_out.append({
            "excluded": list(excluded), **payload["result"],
            "return_delta_vs_base_pct_points": round(
                payload["result"]["return_pct"] - base["result"]["return_pct"], 4
            ),
            "positive_folds": payload["positive_folds"],
            "final_two_compounded_return_pct": round(
                (math.prod(1 + f["return_pct"] / 100 for f in payload["walk_forward_folds"][6:]) - 1) * 100, 4
            ),
        })
    btc_rows = _latest_daily(root / "results" / "bybit_lifecycle_daily", "BTCUSDT")
    regimes, median_vol = _regime_lookup(btc_rows)
    start_ms = int(_load(root / "results" / "bybit_lifecycle_universe.json")["protocol"]["start_ms"])
    fold_stats: dict[int, dict] = defaultdict(lambda: {
        "trades": 0, "net_pnl": 0.0, "gross_price_pnl": 0.0,
        "costs": 0.0, "stops": 0, "symbols": defaultdict(float),
        "regimes": defaultdict(lambda: {"trades": 0, "net_pnl": 0.0}),
    })
    for trade in base["closed_trades"]:
        fold = min(7, max(0, (int(trade["entry_time"]) - start_ms) // FOLD_MS))
        decision_day = int(trade["entry_time"]) - DAY_MS
        regime = regimes.get(decision_day)
        trend = "strong_up" if regime and regime["btc_return_14d"] >= 0.10 else "mild_up"
        vol = "high_vol" if regime and regime["btc_volatility_30d"] >= median_vol else "low_vol"
        label = f"{trend}_{vol}"
        stats = fold_stats[fold]
        stats["trades"] += 1
        stats["net_pnl"] += trade["net_pnl"]
        stats["gross_price_pnl"] += trade["gross_price_pnl"]
        stats["costs"] += trade["execution_cost"] + trade["fees"] + trade["funding_paid"]
        stats["stops"] += trade["reason"] == "stop"
        stats["symbols"][trade["symbol"]] += trade["net_pnl"]
        stats["regimes"][label]["trades"] += 1
        stats["regimes"][label]["net_pnl"] += trade["net_pnl"]
    folds = []
    for index, reported in enumerate(base["walk_forward_folds"]):
        stats = fold_stats[index]
        folds.append({
            "fold": index + 1, **reported, "trades": stats["trades"],
            "trade_net_pnl": round(stats["net_pnl"], 4),
            "gross_price_pnl": round(stats["gross_price_pnl"], 4),
            "costs_and_funding": round(stats["costs"], 4), "stop_exits": stats["stops"],
            "symbol_pnl": {k: round(v, 4) for k, v in sorted(stats["symbols"].items())},
            "decision_regime_pnl": {
                k: {"trades": v["trades"], "net_pnl": round(v["net_pnl"], 4)}
                for k, v in sorted(stats["regimes"].items())
            },
        })
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "development robustness; exclusions and final folds are inspected",
        "base": base["result"], "leave_out": leave_out,
        "regime_definition": {
            "decision_cutoff": "entry timestamp minus one completed daily candle",
            "trend": "strong_up if BTC 14d return >=10%, otherwise mild_up",
            "volatility": "high/low split at full-development-sample median BTC 30d annualized volatility",
            "warning": "volatility threshold is descriptive and inspected, not a tradable pre-registered gate",
        },
        "fold_attribution": folds,
    }
    (root / args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
