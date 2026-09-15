"""Build ETH 24h targets and strictly causal ETH market features after v17 predeclaration."""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from eth_transfer_v17_common import sha256, write_json


FOUR_HOURS_MS = 14_400_000


def build(info_path: Path, bars_path: Path, funding_path: Path, predeclared_path: Path, output_path: Path) -> dict:
    config = json.loads(predeclared_path.read_text(encoding="utf-8"))
    if config["stage"] != "PREDECLARED_BEFORE_TARGET_BUILD":
        raise ValueError("invalid predeclaration stage")
    expected = config["sources"]
    for key, path in (("information_sets", info_path), ("eth_bars", bars_path), ("eth_funding", funding_path)):
        if sha256(path) != expected[key]["sha256"]:
            raise ValueError(f"{key} hash mismatch")
    info = json.loads(info_path.read_text(encoding="utf-8"))["records"]
    bars = json.loads(bars_path.read_text(encoding="utf-8"))
    by_time = {int(row[0]): row for row in bars}
    funding = {int(k): float(v) for k, v in json.loads(funding_path.read_text(encoding="utf-8")).items()}
    records = []
    for item in info:
        cutoff = datetime.fromisoformat(item["available_at"]).astimezone(timezone.utc)
        cutoff_ms = int(cutoff.timestamp() * 1000)
        entry_ms = cutoff_ms + FOUR_HOURS_MS
        exit_ms = entry_ms + 6 * FOUR_HOURS_MS
        history_times = [cutoff_ms - i * FOUR_HOURS_MS for i in range(1, 181)]
        if entry_ms not in by_time or exit_ms not in by_time or any(t not in by_time for t in history_times):
            continue
        ordered = [by_time[t] for t in reversed(history_times)]
        closes = np.asarray([float(row[4]) for row in ordered])
        log_returns = np.diff(np.log(closes))
        daily_quote = np.asarray([sum(float(ordered[j + k][6]) for k in range(6)) for j in range(0, 180, 6)])
        recent_volume = daily_quote[-1]
        volume_scale = float(np.std(daily_quote[:-1])) or 1.0
        features = {
            "tech_eth_return_24h": float(closes[-1] / closes[-7] - 1.0),
            "tech_eth_return_72h": float(closes[-1] / closes[-19] - 1.0),
            "tech_eth_return_168h": float(closes[-1] / closes[-43] - 1.0),
            "tech_eth_realized_vol_7d": float(math.sqrt(np.sum(log_returns[-42:] ** 2))),
            "tech_eth_volume_zscore_30d": float((recent_volume - np.mean(daily_quote[:-1])) / volume_scale),
            "tech_eth_funding_latest": float(next((funding[t] for t in sorted(funding, reverse=True) if t <= cutoff_ms), 0.0)),
            "tech_eth_funding_24h": float(sum(v for t, v in funding.items() if cutoff_ms - 86_400_000 < t <= cutoff_ms)),
            "tech_eth_funding_72h": float(sum(v for t, v in funding.items() if cutoff_ms - 259_200_000 < t <= cutoff_ms)),
            "tech_cross_asset_mean_return_24h": float(item["features"]["cross_asset_mean_return_24h"]),
            "tech_cross_asset_breadth_24h": float(item["features"]["cross_asset_breadth_24h"]),
            "tech_cross_asset_dispersion_24h": float(item["features"]["cross_asset_dispersion_24h"]),
        }
        funding_24h = sum(v for t, v in funding.items() if entry_ms < t <= exit_ms)
        records.append({
            "information_date": item["information_date"], "available_at": item["available_at"],
            "entry_at": datetime.fromtimestamp(entry_ms / 1000, timezone.utc).isoformat(),
            "exit_at": datetime.fromtimestamp(exit_ms / 1000, timezone.utc).isoformat(),
            "target_h24_return": float(by_time[exit_ms][1]) / float(by_time[entry_ms][1]) - 1.0,
            "funding_rate_sum_h24": float(funding_24h), "tech_features": features,
        })
    payload = {
        "schema_version": 1, "experiment_id": "LLM-072/HYB-004-ETH-shared-panel-v17",
        "status": "DEVELOPMENT_TARGET_PANEL", "outcomes_consulted": True,
        "target_contract": config["target_contract"], "records": records,
        "summary": {"records": len(records), "start": records[0]["information_date"], "end": records[-1]["information_date"]},
        "inputs": {key: {"path": value["path"], "sha256": value["sha256"]} for key, value in expected.items()},
        "predeclaration": {"path": str(predeclared_path), "sha256": sha256(predeclared_path)},
    }
    write_json(output_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--information-sets", type=Path, required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--predeclared", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args.information_sets, args.bars, args.funding, args.predeclared, args.output)
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()

