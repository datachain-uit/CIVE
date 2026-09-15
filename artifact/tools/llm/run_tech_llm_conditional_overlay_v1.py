"""Freeze and evaluate the Tech+LLM conditional entry overlay v1.

Policy construction uses only frozen Tech entry timestamps, LLM event fields,
and source metadata. Evaluation is a separate subcommand that may read PnL.
The result is exploratory because project researchers have seen the underlying
development outcomes before this protocol was written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCHEMA = "tech-llm-conditional-overlay-v1"
SEED = 20_260_909
DRAWS = 10_000
DOWNSIZE = 0.68
VETO = 0.76


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).isoformat()


def info_date(timestamp: int, delay_days: int = 0) -> str:
    moment = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
    return (moment.date() - timedelta(days=1 + delay_days)).isoformat()


def key(row: dict[str, Any]) -> str:
    return f"{row['entry_time']}::{row['symbol']}"


def strength(record: dict[str, Any], direction: str) -> float:
    if record.get("direction") != direction:
        return 0.0
    relevance = {"direct": 1.0, "indirect": 0.5, "none": 0.0}.get(
        str(record.get("btc_relevance")), 0.0
    )
    return (
        relevance
        * float(record.get("severity", 0.0))
        * float(record.get("confidence", 0.0))
        * (0.5 + 0.5 * float(record.get("reported_surprise", 0.0)))
    )


def daily_features(events_path: Path, inputs_path: Path) -> dict[str, dict[str, Any]]:
    events = read_json(events_path)["records"]
    inputs = read_json(inputs_path)["records"]
    inputs_by_id = {row["headline_id"]: row for row in inputs}
    if len(inputs_by_id) != len(inputs):
        raise ValueError("duplicate headline_id in frozen inputs")
    output: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "adverse": 0.0, "beneficial": 0.0, "headlines": 0,
        "bitcoin_headlines": 0, "latest_available_at": None,
    })
    seen = set()
    for event in events:
        headline_id = event["headline_id"]
        source = inputs_by_id.get(headline_id)
        if source is None or source["information_date"] != event["information_date"]:
            raise ValueError(f"event/input mismatch: {headline_id}")
        if event.get("status") != "success" or event.get("error") is not None:
            raise ValueError(f"non-success event in completed v3.9 output: {headline_id}")
        seen.add(headline_id)
        row = output[event["information_date"]]
        row["adverse"] = max(row["adverse"], strength(event, "negative"))
        row["beneficial"] = max(row["beneficial"], strength(event, "positive"))
        row["headlines"] += 1
        row["bitcoin_headlines"] += int(source.get("coin_type") == "Bitcoin")
        available = str(source["available_at"])
        if row["latest_available_at"] is None or available > row["latest_available_at"]:
            row["latest_available_at"] = available
    if len(seen) != len(inputs_by_id):
        raise ValueError(f"coverage mismatch: {len(seen)} != {len(inputs_by_id)}")
    return dict(output)


def weight(score: float) -> float:
    if score >= VETO:
        return 0.0
    if score >= DOWNSIZE:
        return 0.5
    return 1.0


def frozen_opportunities(tech: dict[str, Any], start: int, end: int) -> list[dict[str, Any]]:
    rows = [
        {
            "symbol": str(trade["symbol"]),
            "entry_time": int(trade["entry_time"]),
            "exit_time": int(trade["exit_time"]),
            "exit_reason": str(trade["reason"]),
        }
        for trade in tech["closed_trades"]
        if start <= int(trade["entry_time"]) <= end
    ]
    return sorted(rows, key=lambda row: (row["entry_time"], row["symbol"]))


def assignments(opportunities: list[dict[str, Any]], features: dict[str, dict[str, Any]]) -> tuple[dict[str, dict[str, float]], list[dict[str, Any]]]:
    audit = []
    for opportunity in opportunities:
        current_date = info_date(opportunity["entry_time"])
        delayed_date = info_date(opportunity["entry_time"], 1)
        current = features.get(current_date)
        delayed = features.get(delayed_date)
        if current is None:
            raise ValueError(f"missing information date: {current_date}")
        available = datetime.fromisoformat(current["latest_available_at"]).astimezone(timezone.utc)
        entry = datetime.fromtimestamp(opportunity["entry_time"] / 1000, tz=timezone.utc)
        if available > entry:
            raise ValueError(f"look-ahead availability: {key(opportunity)}")
        audit.append({
            **opportunity,
            "entry_time_iso": iso(opportunity["entry_time"]),
            "information_date": current_date,
            "latest_available_at": available.isoformat(),
            "adverse_score": float(current["adverse"]),
            "beneficial_score": float(current["beneficial"]),
            "headline_count": int(current["headlines"]),
            "bitcoin_headline_count": int(current["bitcoin_headlines"]),
            "delayed_information_date": delayed_date,
            "delayed_adverse_score": float(delayed["adverse"]) if delayed else 0.0,
            "primary_weight": weight(float(current["adverse"])),
        })
    primary = {key(row): row["primary_weight"] for row in audit}
    n_veto = sum(value == 0.0 for value in primary.values())
    n_downsize = sum(value == 0.5 for value in primary.values())
    metadata_rank = sorted(audit, key=lambda row: (
        -row["bitcoin_headline_count"], -row["headline_count"],
        row["entry_time"], row["symbol"],
    ))
    positive_rank = sorted(audit, key=lambda row: (
        -row["beneficial_score"], row["entry_time"], row["symbol"],
    ))
    metadata = {key(row): 1.0 for row in audit}
    opposite = {key(row): 1.0 for row in audit}
    for rank, output in ((metadata_rank, metadata), (positive_rank, opposite)):
        for row in rank[:n_veto]:
            output[key(row)] = 0.0
        for row in rank[n_veto:n_veto + n_downsize]:
            output[key(row)] = 0.5
    ordered_keys = [key(row) for row in audit]
    shuffled_values = [primary[item] for item in ordered_keys]
    random.Random(SEED).shuffle(shuffled_values)
    return {
        "tech_only": {item: 1.0 for item in ordered_keys},
        "tech_llm": primary,
        "metadata_only": metadata,
        "shuffled_timestamp": dict(zip(ordered_keys, shuffled_values, strict=True)),
        "delayed_24h": {key(row): weight(row["delayed_adverse_score"]) for row in audit},
        "opposite_polarity": opposite,
    }, audit


def freeze(args: argparse.Namespace) -> None:
    tech = read_json(args.tech_result)
    features = daily_features(args.events, args.inputs)
    start = int(datetime.fromisoformat(args.start).timestamp() * 1000)
    end = int(datetime.fromisoformat(args.end).timestamp() * 1000)
    opportunities = frozen_opportunities(tech, start, end)
    policies, audit = assignments(opportunities, features)
    primary = policies["tech_llm"]
    sample = {
        "total_opportunities": len(opportunities),
        "policy_active": sum(value < 1.0 for value in primary.values()),
        "veto": sum(value == 0.0 for value in primary.values()),
        "downsize": sum(value == 0.5 for value in primary.values()),
    }
    runner = Path(__file__).resolve()
    payload = {
        "schema_version": SCHEMA,
        "experiment_id": "HYB-001",
        "status": "frozen-exploratory-policy-before-evaluation",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "research_role": "exploratory development; not validation or sealed holdout",
        "researcher_outcomes_previously_seen": True,
        "policy_selection_used_trade_pnl": False,
        "architecture": {
            "technical_signal": "frozen long-only Tech-Control entry",
            "llm_authority": "confirm/downsize/veto entry only",
            "weight_domain": [0.0, 0.5, 1.0],
            "weight_locked_until_tech_exit": True,
            "new_trade_or_direction_reversal_allowed": False,
            "missing_or_error_fallback_weight": 1.0,
        },
        "feature_contract": {
            "source": "frozen event-risk v3.9 full extraction",
            "adverse_event_score": "relevance_weight * severity * confidence * (0.5 + 0.5 * reported_surprise), negative events only",
            "relevance_weights": {"direct": 1.0, "indirect": 0.5, "none": 0.0},
            "daily_aggregation": "maximum adverse event score",
            "polarity": "negative is adverse because frozen Tech-Control is long-only",
        },
        "policy": {
            "confirm": "score < 0.68",
            "downsize": "0.68 <= score < 0.76",
            "veto": "score >= 0.76",
            "selection_basis": "feature-only density audit at frozen Tech entries; no PnL used",
        },
        "evaluation": {
            "start": args.start, "end": args.end,
            "unit": "frozen Tech-Control trade-entry opportunity",
            "primary_estimand": "mean paired net return difference",
            "resampling_unit": "calendar-quarter cluster",
            "bootstrap_draws": DRAWS, "confidence_level": 0.95,
            "bootstrap_seed": SEED,
            "minimum_total_opportunities": 20,
            "minimum_policy_active_opportunities": 6,
            "folds": [
                ["2022-09-13T00:00:00+00:00", "2023-09-01T00:00:00+00:00"],
                ["2023-09-01T00:00:00+00:00", "2024-09-01T00:00:00+00:00"],
                ["2024-09-01T00:00:00+00:00", "2025-08-29T00:00:00+00:00"],
            ],
            "pass_gate": [
                "sample minima pass",
                "paired cluster-bootstrap CI95 lower bound for net difference > 0",
                "mean paired gross difference > 0",
                "paired net difference > 0 in at least 2/3 folds",
                "primary mean net difference exceeds every placebo",
            ],
            "secondary_path_metric": "closed-trade compounded return and closed-trade drawdown",
        },
        "placebos": {
            "metadata_only": "same action density ranked by Bitcoin count then headline count",
            "shuffled_timestamp": "primary weights permuted once across opportunities",
            "delayed_24h": "adverse score from one information day earlier",
            "opposite_polarity": "same action density assigned to largest beneficial scores",
        },
        "effective_sample_audit": sample,
        "inputs": {
            "tech_result": {"path": str(args.tech_result.resolve()), "sha256": sha256(args.tech_result)},
            "events": {"path": str(args.events.resolve()), "sha256": sha256(args.events)},
            "inputs": {"path": str(args.inputs.resolve()), "sha256": sha256(args.inputs)},
            "runner": {"path": str(runner), "sha256": sha256(runner)},
        },
        "assignments": policies,
        "feature_audit": audit,
        "prohibited": [
            "changing policy, assignments, folds, bootstrap, gate, or placebos after evaluation",
            "calling this development result validation, sealed holdout, or live evidence",
            "letting LLM create a trade, reverse direction, or alter Tech exit semantics",
        ],
    }
    write_json(args.output, payload)
    print(json.dumps({"status": payload["status"], "sample": sample, "output": str(args.output)}, indent=2))


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def quarter(timestamp: int) -> str:
    moment = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
    return f"{moment.year}-Q{(moment.month - 1) // 3 + 1}"


def bootstrap_ci(rows: list[dict[str, Any]], field: str) -> list[float]:
    clusters: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        clusters[quarter(row["entry_time"])].append(float(row[field]))
    keys = sorted(clusters)
    rng = random.Random(SEED)
    estimates = []
    for _ in range(DRAWS):
        sample = []
        for _ in keys:
            sample.extend(clusters[rng.choice(keys)])
        estimates.append(statistics.fmean(sample))
    return [percentile(estimates, 0.025), percentile(estimates, 0.975)]


def summarize(name: str, weights: dict[str, float], base: list[dict[str, Any]], folds: list[list[str]]) -> dict[str, Any]:
    rows, net_equity, gross_equity, peak, drawdown = [], 1.0, 1.0, 1.0, 0.0
    for trade in base:
        policy_weight = float(weights[key(trade)])
        net_hybrid = policy_weight * trade["tech_net_return"]
        gross_hybrid = policy_weight * trade["tech_gross_return"]
        row = {
            **trade, "weight": policy_weight,
            "hybrid_net_return": net_hybrid,
            "hybrid_gross_return": gross_hybrid,
            "paired_net_difference": net_hybrid - trade["tech_net_return"],
            "paired_gross_difference": gross_hybrid - trade["tech_gross_return"],
        }
        rows.append(row)
        net_equity *= 1 + net_hybrid
        gross_equity *= 1 + gross_hybrid
        peak = max(peak, net_equity)
        drawdown = max(drawdown, 1 - net_equity / peak)
    fold_rows = []
    for start, end in folds:
        start_ms = int(datetime.fromisoformat(start).timestamp() * 1000)
        end_ms = int(datetime.fromisoformat(end).timestamp() * 1000)
        values = [row["paired_net_difference"] for row in rows if start_ms <= row["entry_time"] < end_ms]
        fold_rows.append({
            "start": start, "end": end, "n": len(values),
            "mean_paired_net_difference": statistics.fmean(values) if values else None,
        })
    net_d = [row["paired_net_difference"] for row in rows]
    gross_d = [row["paired_gross_difference"] for row in rows]
    return {
        "name": name, "n": len(rows),
        "active": sum(row["weight"] < 1.0 for row in rows),
        "veto": sum(row["weight"] == 0.0 for row in rows),
        "downsize": sum(row["weight"] == 0.5 for row in rows),
        "mean_paired_net_difference": statistics.fmean(net_d),
        "paired_net_difference_ci95": bootstrap_ci(rows, "paired_net_difference"),
        "mean_paired_gross_difference": statistics.fmean(gross_d),
        "compounded_net_return": net_equity - 1,
        "compounded_gross_return": gross_equity - 1,
        "closed_trade_max_drawdown": drawdown,
        "folds": fold_rows,
        "positive_folds": sum(
            row["mean_paired_net_difference"] is not None
            and row["mean_paired_net_difference"] > 0 for row in fold_rows
        ),
        "losing_tech_trades_vetoed": sum(row["weight"] == 0.0 and row["tech_net_return"] < 0 for row in rows),
        "winning_tech_trades_vetoed": sum(row["weight"] == 0.0 and row["tech_net_return"] > 0 for row in rows),
        "paired_rows": rows,
    }


def evaluate(args: argparse.Namespace) -> None:
    frozen = read_json(args.predeclared)
    if frozen.get("status") != "frozen-exploratory-policy-before-evaluation":
        raise ValueError("invalid pre-evaluation freeze status")
    for item in frozen["inputs"].values():
        path = Path(item["path"])
        if sha256(path) != item["sha256"]:
            raise ValueError(f"frozen input hash mismatch: {path}")
    tech = read_json(Path(frozen["inputs"]["tech_result"]["path"]))
    required = set(frozen["assignments"]["tech_only"])
    cumulative_pnl, previous_exit, base = 0.0, None, []
    trades = sorted(tech["closed_trades"], key=lambda row: (int(row["entry_time"]), row["symbol"]))
    for trade in trades:
        entry_time = int(trade["entry_time"])
        entry_equity = float(tech["result"]["starting_balance"]) + cumulative_pnl
        if f"{entry_time}::{trade['symbol']}" in required:
            if previous_exit is not None and entry_time < previous_exit:
                raise ValueError("overlapping trades violate top-1 replay")
            cost = float(trade["execution_cost"]) + float(trade["fees"]) + float(trade["funding_paid"])
            base.append({
                "symbol": str(trade["symbol"]), "entry_time": entry_time,
                "entry_time_iso": iso(entry_time), "exit_time": int(trade["exit_time"]),
                "exit_time_iso": iso(int(trade["exit_time"])), "exit_reason": str(trade["reason"]),
                "tech_entry_equity": entry_equity,
                "tech_gross_return": float(trade["gross_price_pnl"]) / entry_equity,
                "tech_cost_return": cost / entry_equity,
                "tech_net_return": float(trade["net_pnl"]) / entry_equity,
            })
            previous_exit = int(trade["exit_time"])
        cumulative_pnl += float(trade["net_pnl"])
    if {key(row) for row in base} != required:
        raise ValueError("assignments do not match frozen Tech opportunities")
    folds = frozen["evaluation"]["folds"]
    results = {name: summarize(name, weights, base, folds) for name, weights in frozen["assignments"].items()}
    primary = results["tech_llm"]
    placebo_names = ["metadata_only", "shuffled_timestamp", "delayed_24h", "opposite_polarity"]
    checks = {
        "minimum_total_opportunities": primary["n"] >= frozen["evaluation"]["minimum_total_opportunities"],
        "minimum_policy_active_opportunities": primary["active"] >= frozen["evaluation"]["minimum_policy_active_opportunities"],
        "paired_net_ci_lower_positive": primary["paired_net_difference_ci95"][0] > 0,
        "paired_gross_mean_positive": primary["mean_paired_gross_difference"] > 0,
        "positive_at_least_two_of_three_folds": primary["positive_folds"] >= 2,
        "primary_exceeds_every_placebo": all(
            primary["mean_paired_net_difference"] > results[name]["mean_paired_net_difference"]
            for name in placebo_names
        ),
    }
    sample_ok = checks["minimum_total_opportunities"] and checks["minimum_policy_active_opportunities"]
    status = "exploratory-development-pass" if all(checks.values()) else (
        "exploratory-development-fail" if sample_ok else "exploratory-development-insufficient-sample"
    )
    payload = {
        "schema_version": SCHEMA, "experiment_id": "HYB-001", "status": status,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "exploratory development; not validation, sealed holdout, or live evidence",
        "predeclared": {"path": str(args.predeclared.resolve()), "sha256": sha256(args.predeclared)},
        "checks": checks, "results": results,
        "limitations": [
            "Only 24 frozen Tech opportunities occur in the LLM coverage window.",
            "Outcomes were already known to the project before this policy was frozen.",
            "Compounded return and drawdown use closed-trade resolution, not intrabar resolution.",
        ],
    }
    write_json(args.output, payload)
    compact = {name: {k: v for k, v in result.items() if k not in {"paired_rows", "folds"}} for name, result in results.items()}
    print(json.dumps({"status": status, "checks": checks, "results": compact, "output": str(args.output)}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze_parser = commands.add_parser("freeze")
    freeze_parser.add_argument("--tech-result", type=Path, required=True)
    freeze_parser.add_argument("--events", type=Path, required=True)
    freeze_parser.add_argument("--inputs", type=Path, required=True)
    freeze_parser.add_argument("--start", default="2022-09-13T00:00:00+00:00")
    freeze_parser.add_argument("--end", default="2025-08-28T00:00:00+00:00")
    freeze_parser.add_argument("--output", type=Path, required=True)
    freeze_parser.set_defaults(function=freeze)
    evaluate_parser = commands.add_parser("evaluate")
    evaluate_parser.add_argument("--predeclared", type=Path, required=True)
    evaluate_parser.add_argument("--output", type=Path, required=True)
    evaluate_parser.set_defaults(function=evaluate)
    args = parser.parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
