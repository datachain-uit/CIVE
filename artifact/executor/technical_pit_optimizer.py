"""Two-stage, train-fold-only optimizer for the point-in-time Tech evaluator."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


BASE_COST = {"fee_bps": 6.0, "slippage_bps": 3.0, "spread_bps": 2.0, "impact_bps": 1.0}
COSTS = {
    "base": BASE_COST,
    "stress": {"fee_bps": 10.0, "slippage_bps": 8.0, "spread_bps": 4.0, "impact_bps": 5.0},
    "harsh": {"fee_bps": 15.0, "slippage_bps": 15.0, "spread_bps": 8.0, "impact_bps": 10.0},
}


def _key(config: dict) -> str:
    width = str(config["channel_width"]).replace(".", "p")
    stop = str(config["stop_atr"]).replace(".", "p")
    return (
        f"{config['event_family']}{config['event_lookback']}_w{width}_"
        f"{config['rank_mode']}_r{config['rank_days']}_top{config['top_n']}_"
        f"liq{config['liquidity_size']}x{config['liquidity_lookback']}_stop{stop}"
    )


def _matches(payload: dict, config: dict, cost: dict) -> bool:
    protocol = payload.get("protocol", {})
    return (
        payload.get("missing_funding_events") == 0
        and protocol.get("execution_semantics") == "no_same_bar_reentry_v1"
        and protocol.get("universe_mode") == "point-in-time-liquidity"
        and protocol.get("liquidity_universe_size") == config["liquidity_size"]
        and protocol.get("liquidity_lookback_days") == config["liquidity_lookback"]
        and protocol.get("event_family") == config["event_family"]
        and protocol.get("event_lookback") == config["event_lookback"]
        and protocol.get("rank_mode") == config["rank_mode"]
        and protocol.get("fee_bps") == cost["fee_bps"]
        and protocol.get("slippage_bps") == cost["slippage_bps"]
        and protocol.get("spread_bps") == cost["spread_bps"]
        and protocol.get("impact_bps") == cost["impact_bps"]
        and f"top-N {config['rank_days']}d" in protocol.get("daily_selection", "")
    )


def _run(root: Path, output: Path, config: dict, cost: dict, days: int) -> dict:
    if output.exists():
        try:
            payload = json.loads(output.read_text(encoding="utf-8"))
            if _matches(payload, config, cost):
                return payload
        except (OSError, ValueError, TypeError):
            pass
    command = [
        sys.executable, str(root / "executor" / "technical_cross_asset_execution.py"),
        "--days", str(days), "--gross-leverage", "1",
        "--universe-mode", "point-in-time-liquidity",
        "--liquidity-universe-size", str(config["liquidity_size"]),
        "--liquidity-lookback-days", str(config["liquidity_lookback"]),
        "--event-family", config["event_family"],
        "--event-lookback", str(config["event_lookback"]),
        "--channel-width", str(config["channel_width"]),
        "--rank-mode", config["rank_mode"], "--rank-days", str(config["rank_days"]),
        "--top-n", str(config["top_n"]), "--stop-atr", str(config["stop_atr"]),
        "--trail-atr", "3.0", "--pyramid-mode", "off",
        "--funding-source", "bybit-history", "--fold-days", "180",
        "--fee-bps", str(cost["fee_bps"]), "--slippage-bps", str(cost["slippage_bps"]),
        "--spread-bps", str(cost["spread_bps"]), "--impact-bps", str(cost["impact_bps"]),
        "--output", str(output),
    ]
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"execution failed for {_key(config)}: {completed.stderr[-3000:]}")
    return json.loads(output.read_text(encoding="utf-8"))


def _summary(payload: dict, train_folds: int) -> dict:
    folds = payload["walk_forward_folds"]
    train = folds[:train_folds]
    validation = folds[train_folds:]
    train_log_return = sum(math.log1p(fold["return_pct"] / 100) for fold in train)
    return {
        "train_log_return": round(train_log_return, 8),
        "train_compounded_return_pct": round((math.exp(train_log_return) - 1) * 100, 4),
        "train_positive_folds": sum(fold["return_pct"] > 0 for fold in train),
        "train_max_fold_drawdown_pct": max(fold["max_drawdown_pct"] for fold in train),
        "validation_folds": validation,
        "validation_positive_folds": sum(fold["return_pct"] > 0 for fold in validation),
        "full_result": payload["result"],
    }


def _select(results: dict[str, dict], train_folds: int) -> str:
    eligible = []
    for name, payload in results.items():
        summary = _summary(payload, train_folds)
        if summary["train_positive_folds"] >= 4 and summary["train_max_fold_drawdown_pct"] <= 25:
            eligible.append((summary["train_log_return"], name))
    if not eligible:
        raise RuntimeError("no configuration passes the predeclared train-fold gate")
    return max(eligible)[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Point-in-time Technical train/validation optimizer")
    parser.add_argument("--days", type=int, default=1460)
    parser.add_argument("--train-folds", type=int, default=6)
    parser.add_argument("--output-dir", type=Path, default=Path("results/technical_pit_optimizer"))
    parser.add_argument("--output", type=Path, default=Path("results/technical_pit_optimizer_summary.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "event_family": "channel", "event_lookback": 10, "channel_width": 0.10,
        "rank_mode": "momentum", "rank_days": 20, "top_n": 2,
        "liquidity_size": 5, "liquidity_lookback": 30, "stop_atr": 2.5,
    }

    structural_configs = []
    events = [
        ("channel", 10, 0.08), ("channel", 10, 0.10),
        ("channel", 10, 0.15), ("channel", 20, 0.15),
        ("sr", 10, 0.10), ("sr", 20, 0.10), ("sr", 50, 0.10),
    ]
    for family, lookback, width in events:
        for rank_mode in ("momentum", "oscillator-ensemble"):
            structural_configs.append({
                **base, "event_family": family, "event_lookback": lookback,
                "channel_width": width, "rank_mode": rank_mode,
            })

    structural_results = {}
    configs_by_name = {}
    for number, config in enumerate(structural_configs, 1):
        name = _key(config)
        print(f"[structure {number}/{len(structural_configs)}] {name}", flush=True)
        configs_by_name[name] = config
        structural_results[name] = _run(root, output_dir / f"{name}_base.json", config, BASE_COST, args.days)
    structure_winner_name = _select(structural_results, args.train_folds)
    structure_winner = configs_by_name[structure_winner_name]

    coordinate_configs = [structure_winner]
    for field, values in (
        ("top_n", (1, 2, 3)),
        ("liquidity_size", (4, 5, 7)),
        ("liquidity_lookback", (7, 30, 90)),
        ("stop_atr", (0.0, 1.5, 2.5, 3.5)),
    ):
        coordinate_configs.extend({**structure_winner, field: value} for value in values)
    if structure_winner["rank_mode"] == "momentum":
        coordinate_configs.extend({**structure_winner, "rank_days": value} for value in (10, 20, 40, 60))
    deduped = {_key(config): config for config in coordinate_configs}
    coordinate_results = {}
    for number, (name, config) in enumerate(deduped.items(), 1):
        print(f"[coordinate {number}/{len(deduped)}] {name}", flush=True)
        configs_by_name[name] = config
        coordinate_results[name] = _run(root, output_dir / f"{name}_base.json", config, BASE_COST, args.days)
    coordinate_winner_name = _select(coordinate_results, args.train_folds)
    coordinate_winner = configs_by_name[coordinate_winner_name]

    # Coordinate choices can interact with the ranking rule. Recheck the
    # alternate rank only after the train-fold coordinate winner is locked.
    alternate_rank = (
        "momentum" if coordinate_winner["rank_mode"] == "oscillator-ensemble"
        else "oscillator-ensemble"
    )
    interaction_configs = [coordinate_winner, {**coordinate_winner, "rank_mode": alternate_rank}]
    interaction_results = {}
    for number, config in enumerate(interaction_configs, 1):
        name = _key(config)
        print(f"[interaction {number}/{len(interaction_configs)}] {name}", flush=True)
        configs_by_name[name] = config
        interaction_results[name] = _run(
            root, output_dir / f"{name}_base.json", config, BASE_COST, args.days,
        )
    winner_name = _select(interaction_results, args.train_folds)
    winner = configs_by_name[winner_name]

    cost_results = {}
    for cost_name, cost in COSTS.items():
        print(f"[cost {cost_name}] {_key(winner)}", flush=True)
        cost_results[cost_name] = _run(
            root, output_dir / f"{_key(winner)}_{cost_name}.json", winner, cost, args.days,
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "research only; selection uses first folds, validation is reported after locking",
        "selection_rule": "max compounded train-fold log return subject to >=4/6 positive folds and <=25% maximum train-fold drawdown",
        "train_folds": args.train_folds,
        "structure_winner": {"name": structure_winner_name, "config": structure_winner},
        "coordinate_winner": {"name": coordinate_winner_name, "config": coordinate_winner},
        "interaction_winner": {"name": winner_name, "config": winner},
        "structure_summary": {name: _summary(result, args.train_folds) for name, result in structural_results.items()},
        "coordinate_summary": {name: _summary(result, args.train_folds) for name, result in coordinate_results.items()},
        "interaction_summary": {name: _summary(result, args.train_folds) for name, result in interaction_results.items()},
        "winner_cost_stress": {name: _summary(result, args.train_folds) for name, result in cost_results.items()},
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({
        "winner": payload["interaction_winner"],
        "cost_stress": payload["winner_cost_stress"],
        "output": str(output),
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
