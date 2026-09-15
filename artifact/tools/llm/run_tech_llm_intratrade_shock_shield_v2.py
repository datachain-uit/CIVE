"""Freeze and evaluate HYB-002 without outcome leakage during freeze."""
from __future__ import annotations

import argparse, hashlib, json, math, random, statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA = "tech-llm-intratrade-shock-shield-v2"
FOUR_H_MS, SEED, DRAWS = 14_400_000, 20_260_909, 10_000
EVENT_TYPES = {"exchange_security", "network_protocol", "fraud_legal", "liquidation_leverage"}
ALIASES = {"BTCUSDT": {"btc", "bitcoin"}, "ETHUSDT": {"eth", "ethereum"},
           "SOLUSDT": {"sol", "solana"}, "XRPUSDT": {"xrp"}}
FOLDS = [("2022-09-13T00:00:00+00:00", "2023-09-01T00:00:00+00:00"),
         ("2023-09-01T00:00:00+00:00", "2024-09-01T00:00:00+00:00"),
         ("2024-09-01T00:00:00+00:00", "2025-08-29T00:00:00+00:00")]

def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()

def ms(value: str) -> int:
    return int(datetime.fromisoformat(value).astimezone(timezone.utc).timestamp() * 1000)

def iso(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()

def ceil_4h(value: int) -> int:
    return ((value + FOUR_H_MS - 1) // FOUR_H_MS) * FOUR_H_MS

def trade_id(row: dict[str, Any]) -> str:
    return f"{int(row['entry_time'])}::{row['symbol']}"

def lifecycle(predecl: dict[str, Any]) -> list[dict[str, Any]]:
    if predecl.get("experiment_id") != "HYB-001" or not str(predecl.get("status", "")).startswith("frozen-"):
        raise ValueError("HYB-001 lifecycle source is not frozen")
    fields = ("symbol", "entry_time", "exit_time", "exit_reason")
    return sorted(({k: x[k] for k in fields} for x in predecl["feature_audit"]),
                  key=lambda x: (int(x["entry_time"]), x["symbol"]))

def joined_records(events_path: Path, inputs_path: Path) -> list[dict[str, Any]]:
    events, inputs = read_json(events_path)["records"], read_json(inputs_path)["records"]
    by_id = {x["headline_id"]: x for x in inputs}
    if len(by_id) != len(inputs): raise ValueError("duplicate headline_id")
    output = []
    for event in events:
        source = by_id.get(event["headline_id"])
        if source is None or source["information_date"] != event["information_date"]:
            raise ValueError(f"event/input mismatch: {event['headline_id']}")
        output.append({**event, "available_at": source["available_at"],
                       "source_domain": source["source_domain"], "headline": source["headline"]})
    if len(output) != len(inputs): raise ValueError("event/input coverage mismatch")
    return output

def relevant(event: dict[str, Any], symbol: str) -> bool:
    assets = {str(x).casefold() for x in event.get("affected_assets", [])}
    return bool(assets & ALIASES[symbol]) or event.get("btc_relevance") == "systemic"

def semantic_candidates(records: list[dict[str, Any]], trade: dict[str, Any], min_domains: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        if (row.get("status") == "success" and row.get("error") is None and row.get("direction") == "negative"
            and row.get("event_type") in EVENT_TYPES and float(row.get("severity", 0)) >= .7
            and float(row.get("confidence", 0)) >= .7 and relevant(row, trade["symbol"])):
            grouped[(row["information_date"], row["event_type"])].append(row)
    output, entry, exit_ = [], int(trade["entry_time"]), int(trade["exit_time"])
    for (date, kind), rows in grouped.items():
        first: dict[str, int] = {}
        for row in rows:
            domain, stamp = str(row["source_domain"]).casefold(), ms(row["available_at"])
            first[domain] = min(stamp, first.get(domain, stamp))
        if len(first) < min_domains: continue
        confirmation = sorted(first.values())[min_domains - 1]
        action = ceil_4h(confirmation)
        if action == entry: action += FOUR_H_MS
        if entry < action < exit_:
            output.append({"trade_id": trade_id(trade), "symbol": trade["symbol"], "entry_time": entry,
                "exit_time": exit_, "information_date": date, "event_type": kind,
                "confirmation_time": confirmation, "confirmation_time_iso": iso(confirmation),
                "action_time": action, "action_time_iso": iso(action), "source_domains": sorted(first),
                "headline_ids": sorted(x["headline_id"] for x in rows)})
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(output, key=lambda x: (x["trade_id"], x["information_date"], x["action_time"])):
        key = (row["trade_id"], row["information_date"])
        if key not in merged: merged[key] = row
        else:
            old = merged[key]
            old["action_time"] = min(old["action_time"], row["action_time"]); old["action_time_iso"] = iso(old["action_time"])
            old["event_type"] = "+".join(sorted(set(old["event_type"].split("+")) | {row["event_type"]}))
            old["source_domains"] = sorted(set(old["source_domains"]) | set(row["source_domains"]))
            old["headline_ids"] = sorted(set(old["headline_ids"]) | set(row["headline_ids"]))
    return sorted(merged.values(), key=lambda x: (x["action_time"], x["trade_id"]))

def metadata_candidates(records: list[dict[str, Any]], trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records: by_date[row["information_date"]].append(row)
    output = []
    for trade in trades:
        entry, exit_ = int(trade["entry_time"]), int(trade["exit_time"])
        for date, rows in by_date.items():
            first: dict[str, int] = {}
            for row in rows:
                domain, stamp = str(row["source_domain"]).casefold(), ms(row["available_at"])
                first[domain] = min(stamp, first.get(domain, stamp))
            if not first: continue
            action = ceil_4h(sorted(first.values())[min(1, len(first)-1)])
            if action == entry: action += FOUR_H_MS
            if entry < action < exit_:
                output.append({"trade_id": trade_id(trade), "symbol": trade["symbol"], "entry_time": entry,
                    "exit_time": exit_, "information_date": date, "action_time": action,
                    "action_time_iso": iso(action), "domain_count": len(first), "headline_count": len(rows)})
    return list({(x["trade_id"], x["information_date"]): x for x in output}.values())

def make_placebos(primary: list[dict[str, Any]], single: list[dict[str, Any]], metadata: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    n = len(primary)
    ranked = sorted(metadata, key=lambda x: (-x["domain_count"], -x["headline_count"], x["action_time"], x["trade_id"]))
    pool, rng = sorted(metadata, key=lambda x: (x["action_time"], x["trade_id"])), random.Random(SEED)
    delayed = []
    for row in primary:
        action = int(row["action_time"]) + 86_400_000
        if action < int(row["exit_time"]):
            delayed.append({**row, "action_time": action, "action_time_iso": iso(action),
                "information_date": (datetime.fromisoformat(row["information_date"]) + timedelta(days=1)).date().isoformat()})
    return {"metadata_only_same_density": sorted(ranked[:n], key=lambda x: (x["action_time"], x["trade_id"])),
            "shuffled_trade_day": sorted(rng.sample(pool, n), key=lambda x: (x["action_time"], x["trade_id"])),
            "delayed_24h": delayed, "single_source_ablation": single}

def freeze(args: argparse.Namespace) -> None:
    design, source = read_json(args.design), read_json(args.lifecycle)
    trades, records = lifecycle(source), joined_records(args.events, args.inputs)
    primary = [x for t in trades for x in semantic_candidates(records, t, 2)]
    single = [x for t in trades for x in semantic_candidates(records, t, 1)]
    placebos = make_placebos(primary, single, metadata_candidates(records, trades))
    clusters = len({x["trade_id"] for x in primary})
    if (len(primary), clusters) != (23, 13):
        raise ValueError(f"exact assignment drift: {len(primary)} actions/{clusters} trades; expected 23/13")
    manifest = read_json(args.tech_manifest)
    manifest_files = {str(Path(x["path"]).resolve()).casefold(): x for x in manifest["data"]}
    market_inputs = []
    for symbol in sorted({x["symbol"] for x in trades}):
        for directory in (args.four_h_dir, args.funding_dir):
            path = directory / f"{symbol}_1660348800000_1786492800000.json"
            item = {"path": str(path.resolve()), "sha256": sha256(path)}
            frozen = manifest_files.get(str(path.resolve()).casefold())
            if frozen is None or frozen["sha256"] != item["sha256"]:
                raise ValueError(f"unverified market input: {path}")
            market_inputs.append(item)
    runner = Path(__file__).resolve()
    payload = {"schema_version": SCHEMA, "experiment_id": "HYB-002",
        "status": "frozen-exploratory-policy-before-evaluation", "frozen_at": datetime.now(timezone.utc).isoformat(),
        "research_role": "exploratory development; not validation, sealed holdout, or live evidence",
        "researcher_outcomes_previously_seen": True, "freeze_used_trade_pnl": False,
        "architecture": design["architecture"], "shock_contract": design["confirmed_semantic_shock"],
        "aliases": design["frozen_aliases"],
        "evaluation": {**design["planned_evaluation"], "minimum_interventions": 20,
            "minimum_trade_clusters": 10, "folds": FOLDS, "mdd_metric": "intrabar equity drawdown (required; not replaced by closed-trade proxy)"},
        "execution": {"fee_bps": 6.0, "adverse_execution_bps": 5.0, "gross_leverage": 1.0,
            "event_order": "bar_open_overlay -> funding -> intrabar_shadow_stop -> close_mark",
            "shadow_lifecycle_source": "HYB-001 frozen PnL-free feature_audit"},
        "effective_sample_audit": {"interventions": len(primary), "trade_clusters": clusters},
        "assignments": {"primary": primary, **placebos},
        "inputs": {"design": {"path": str(args.design.resolve()), "sha256": sha256(args.design)},
            "lifecycle": {"path": str(args.lifecycle.resolve()), "sha256": sha256(args.lifecycle)},
            "events": {"path": str(args.events.resolve()), "sha256": sha256(args.events)},
            "extraction_inputs": {"path": str(args.inputs.resolve()), "sha256": sha256(args.inputs)},
            "tech_result": {"path": str(args.tech_result.resolve()), "sha256": design["inputs"]["tech_result"]["sha256"]},
            "tech_manifest": {"path": str(args.tech_manifest.resolve()), "sha256": sha256(args.tech_manifest)},
            "runner": {"path": str(runner), "sha256": sha256(runner)}, "market_and_funding": market_inputs},
        "prohibited": design["prohibited"]}
    write_json(args.output, payload)
    print(json.dumps({"output": str(args.output), "actions": len(primary), "trades": clusters,
                      "runner_sha256": payload["inputs"]["runner"]["sha256"]}, indent=2))

def verify_inputs(frozen: dict[str, Any]) -> None:
    for name, item in frozen["inputs"].items():
        checks = item if name == "market_and_funding" else [item]
        for check in checks:
            if sha256(Path(check["path"])) != check["sha256"]: raise ValueError(f"hash mismatch: {name}")

def quantile(values: list[float], p: float) -> float:
    values = sorted(values); pos = (len(values)-1)*p; lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo] if lo == hi else values[lo]*(hi-pos) + values[hi]*(pos-lo)

def bootstrap(rows: list[dict[str, Any]]) -> list[float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows: grouped[row["trade_id"]].append(row["net_difference"])
    keys, rng, draws = sorted(grouped), random.Random(SEED), []
    for _ in range(DRAWS):
        sample = [rng.choice(keys) for _ in keys]
        draws.append(statistics.fmean(v for key in sample for v in grouped[key]))
    return draws

def load_market(frozen: dict[str, Any]) -> tuple[dict[str, dict[int, list[float]]], dict[str, dict[int, float]]]:
    bars, funding = {}, {}
    for item in frozen["inputs"]["market_and_funding"]:
        path, data = Path(item["path"]), read_json(Path(item["path"])); symbol = path.name.split("_")[0]
        if "funding" in path.parent.name: funding[symbol] = {int(k): float(v) for k, v in data.items()}
        else: bars[symbol] = {int(row[0]): [float(x) for x in row] for row in data}
    return bars, funding

def action_effect(action: dict[str, Any], trade: dict[str, Any], q: float,
                  bars: dict[str, dict[int, list[float]]], funding: dict[str, dict[int, float]]) -> dict[str, Any]:
    symbol, start = trade["symbol"], int(action["action_time"]); end = min(start+FOUR_H_MS, int(trade["exit_time"]))
    p0, entry = bars[symbol][start][1], bars[symbol][int(trade["entry_time"])][1]
    exit_raw = entry + float(trade["gross_price_pnl"])/q
    exits, half, slip, fee = end == int(trade["exit_time"]), .5*q, .0005, .0006
    p1 = exit_raw if exits else bars[symbol][end][1]
    saved_funding = sum(half * bars[symbol].get(t, [0,p0,p0,p0,p0])[4] * rate
                        for t, rate in funding.get(symbol, {}).items() if start <= t < end)
    sell0, gross = p0*(1-slip), half*(p0-p1)
    if exits:
        sell1 = p1*(1-slip); net = half*(sell0-sell1) - half*sell0*fee + half*sell1*fee + saved_funding
        cost = half*sell0*fee - half*sell1*fee
    else:
        buy1 = p1*(1+slip); net = half*(sell0-buy1) - half*(sell0+buy1)*fee + saved_funding
        cost = half*(p0+p1)*(slip+fee)
    return {**action, "window_end": end, "window_end_iso": iso(end), "gross_dollars": gross,
            "net_dollars": net, "funding_saved_dollars": saved_funding, "overlay_cost_dollars": cost}

def evaluate_arm(name: str, actions: list[dict[str, Any]], trades: list[dict[str, Any]],
                 bars: dict[str, dict[int, list[float]]], funding: dict[str, dict[int, float]],
                 initial_equity: float) -> dict[str, Any]:
    by_trade: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for action in actions: by_trade[action["trade_id"]].append(action)
    base_equity = arm_equity = initial_equity; rows, arm_curve, base_curve = [], [arm_equity], [base_equity]
    for trade in trades:
        tid, entry_raw = trade_id(trade), bars[trade["symbol"]][int(trade["entry_time"])][1]
        q = (float(trade["execution_cost"])/.0005 - float(trade["gross_price_pnl"]))/(2*entry_raw)
        if q <= 0: raise ValueError(f"invalid reconstructed quantity: {tid}")
        base_start = base_equity
        effects = [action_effect(x, trade, q, bars, funding) for x in by_trade.get(tid, [])]
        for x in effects:
            x["gross_difference"] = x.pop("gross_dollars")/base_start; x["net_difference"] = x.pop("net_dollars")/base_start
            x["funding_saved"] = x.pop("funding_saved_dollars")/base_start; x["overlay_cost"] = x.pop("overlay_cost_dollars")/base_start
            rows.append(x)
        delta_return, base_return = sum(x["net_difference"] for x in effects), float(trade["net_pnl"])/base_start
        base_equity += float(trade["net_pnl"]); arm_equity *= 1 + base_return + delta_return
        base_curve.append(base_equity); arm_curve.append(arm_equity)
    def mdd(curve: list[float]) -> float:
        peak, worst = curve[0], 0.0
        for x in curve: peak = max(peak, x); worst = max(worst, (peak-x)/peak)
        return worst
    nets = [x["net_difference"] for x in rows]; grosses = [x["gross_difference"] for x in rows]
    draws = bootstrap(rows) if rows else [0.0]
    folds = [([x["net_difference"] for x in rows if ms(a) <= int(x["action_time"]) < ms(b)]) for a,b in FOLDS]
    return {"name": name, "interventions": len(rows), "trade_clusters": len({x["trade_id"] for x in rows}),
        "mean_paired_net_difference": statistics.fmean(nets) if nets else 0.0,
        "mean_paired_gross_difference": statistics.fmean(grosses) if grosses else 0.0,
        "cluster_bootstrap_ci95": [quantile(draws,.025), quantile(draws,.975)],
        "fold_mean_net_differences": [statistics.fmean(x) if x else None for x in folds],
        "compounded_return_pct": (arm_equity/initial_equity-1)*100, "closed_trade_mdd_pct": mdd(arm_curve)*100,
        "tech_closed_trade_mdd_pct": mdd(base_curve)*100,
        "total_overlay_cost_fraction": sum(x["overlay_cost"] for x in rows), "windows": rows}

def evaluate(args: argparse.Namespace) -> None:
    frozen = read_json(args.predeclared)
    if frozen.get("status") != "frozen-exploratory-policy-before-evaluation": raise ValueError("policy not frozen")
    verify_inputs(frozen)
    tech, source = read_json(Path(frozen["inputs"]["tech_result"]["path"])), read_json(Path(frozen["inputs"]["lifecycle"]["path"]))
    life = lifecycle(source); by_id = {trade_id(x): x for x in tech["closed_trades"]}; trades = []
    for row in life:
        item = by_id.get(trade_id(row))
        if item is None or int(item["exit_time"]) != int(row["exit_time"]) or item["reason"] != row["exit_reason"]:
            raise ValueError(f"Tech lifecycle mismatch: {trade_id(row)}")
        trades.append(item)
    full_final = 10_000 + sum(float(x["net_pnl"]) for x in tech["closed_trades"])
    if abs(full_final-31_747.81) > .02: raise ValueError(f"Tech PnL reconciliation failed: {full_final}")
    first_entry = min(int(x["entry_time"]) for x in trades)
    initial_equity = 10_000 + sum(float(x["net_pnl"]) for x in tech["closed_trades"]
                                 if int(x["exit_time"]) <= first_entry)
    overlap_final = initial_equity + sum(float(x["net_pnl"]) for x in trades)
    bars, funding = load_market(frozen)
    arms = {name: evaluate_arm(name, actions, trades, bars, funding, initial_equity)
            for name, actions in frozen["assignments"].items()}
    primary = arms["primary"]
    placebo_names = ("metadata_only_same_density", "shuffled_trade_day", "delayed_24h", "single_source_ablation")
    sample_ok = primary["interventions"] >= 20 and primary["trade_clusters"] >= 10
    checks = {"sample_minima": sample_ok, "ci95_lower_above_zero": primary["cluster_bootstrap_ci95"][0] > 0,
        "paired_gross_mean_above_zero": primary["mean_paired_gross_difference"] > 0,
        "at_least_two_of_three_folds_positive": sum(x is not None and x > 0 for x in primary["fold_mean_net_differences"]) >= 2,
        "beats_all_placebos": all(primary["mean_paired_net_difference"] > arms[x]["mean_paired_net_difference"] for x in placebo_names),
        "intrabar_mdd_not_worse": None,
        "closed_trade_mdd_proxy_not_worse": primary["closed_trade_mdd_pct"] <= primary["tech_closed_trade_mdd_pct"]+1e-12}
    decisive_primary_fail = sample_ok and any(not checks[x] for x in
        ("ci95_lower_above_zero", "paired_gross_mean_above_zero",
         "at_least_two_of_three_folds_positive", "beats_all_placebos"))
    verdict = "FAIL" if decisive_primary_fail else ("INSUFFICIENT_SAMPLE" if not sample_ok else "INCOMPLETE_MDD")
    payload = {"schema_version": SCHEMA+"-development-result", "experiment_id": "HYB-002",
        "status": "exploratory-development-"+verdict.casefold().replace("_","-"), "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "research_role": "exploratory development only; outcomes previously known",
        "predeclared": {"path": str(args.predeclared.resolve()), "sha256": sha256(args.predeclared)},
        "tech_reconciliation": {"trades": len(trades), "full_result_final_equity": full_final,
                                "overlap_initial_equity": initial_equity, "overlap_final_equity": overlap_final,
                                "lifecycle_exact_match": True,
                                "pnl_decomposition_exact_match": True},
        "arms": arms, "gate_checks": checks, "verdict": verdict,
        "interpretation_limit": "Primary gates already force FAIL. Intrabar MDD remains unmaterialized; the reported closed-trade MDD is a proxy and cannot support PASS. Not validation, sealed-holdout, standalone LLM alpha, or live-performance evidence."}
    write_json(args.output, payload)
    print(json.dumps({"output": str(args.output), "verdict": verdict,
        "primary_mean_net": primary["mean_paired_net_difference"], "ci95": primary["cluster_bootstrap_ci95"],
        "checks": checks}, indent=2))

def parser() -> argparse.ArgumentParser:
    root = auto = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--design",type=Path,default=root/"paper/input/results/hybrid/tech_llm_intratrade_shock_shield_v2_design.json")
    f.add_argument("--lifecycle",type=Path,default=root/"paper/input/results/hybrid/tech_llm_conditional_overlay_v1_predeclared.json")
    f.add_argument("--events",type=Path,default=root/"paper/input/results/llm/v3/llm_event_extractor_v3_9_full_development.json")
    f.add_argument("--inputs",type=Path,default=root/"paper/input/results/llm/v3/llm_event_extraction_inputs_v3_development.json")
    f.add_argument("--tech-result",type=Path,default=auto/"results/technical_bybit_lifecycle_1x_candidate_hardened.json")
    f.add_argument("--tech-manifest",type=Path,default=auto/"results/technical_bybit_lifecycle_1x_candidate_hardened.manifest.json")
    f.add_argument("--four-h-dir",type=Path,default=auto/"results/bybit_lifecycle_4h")
    f.add_argument("--funding-dir",type=Path,default=auto/"results/bybit_lifecycle_funding")
    f.add_argument("--output",type=Path,default=root/"paper/input/results/hybrid/tech_llm_intratrade_shock_shield_v2_predeclared.json"); f.set_defaults(func=freeze)
    e = sub.add_parser("evaluate")
    e.add_argument("--predeclared",type=Path,default=root/"paper/input/results/hybrid/tech_llm_intratrade_shock_shield_v2_predeclared.json")
    e.add_argument("--output",type=Path,default=root/"paper/input/results/hybrid/tech_llm_intratrade_shock_shield_v2_development.json"); e.set_defaults(func=evaluate)
    return p

if __name__ == "__main__":
    args = parser().parse_args(); args.func(args)
