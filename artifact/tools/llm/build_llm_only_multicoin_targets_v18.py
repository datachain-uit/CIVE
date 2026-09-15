"""Build 24h price targets for v18 assets after outcome-free screening."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from eth_transfer_v17_common import sha256, write_json

FOUR_HOURS_MS = 14_400_000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config["stage"] != "PREDECLARED_BEFORE_TARGET_BUILD":
        raise ValueError("invalid v18 evaluation predeclaration")
    info_path = Path(config["sources"]["information_sets"]["path"])
    if sha256(info_path) != config["sources"]["information_sets"]["sha256"]:
        raise ValueError("information-set hash mismatch")
    info = json.loads(info_path.read_text(encoding="utf-8"))["records"]
    assets = {}
    for symbol in config["eligible_assets"]:
        bars_spec = config["sources"]["bars"][symbol]
        bars_path = Path(bars_spec["path"])
        if sha256(bars_path) != bars_spec["sha256"]:
            raise ValueError(f"bar hash mismatch: {symbol}")
        bars = json.loads(bars_path.read_text(encoding="utf-8"))
        by_time = {int(row[0]): row for row in bars}
        records = []
        for item in info:
            cutoff = datetime.fromisoformat(item["available_at"]).astimezone(timezone.utc)
            cutoff_ms = int(cutoff.timestamp() * 1000)
            entry_ms = cutoff_ms + FOUR_HOURS_MS
            exit_ms = entry_ms + 6 * FOUR_HOURS_MS
            if entry_ms not in by_time or exit_ms not in by_time:
                continue
            records.append({
                "information_date": item["information_date"],
                "available_at": item["available_at"],
                "entry_at": datetime.fromtimestamp(entry_ms / 1000, timezone.utc).isoformat(),
                "exit_at": datetime.fromtimestamp(exit_ms / 1000, timezone.utc).isoformat(),
                "target_h24_return": float(by_time[exit_ms][1]) / float(by_time[entry_ms][1]) - 1.0,
            })
        assets[symbol] = {
            "experiment_id": config["assets"][symbol]["experiment_id"],
            "records": records,
            "summary": {
                "records": len(records),
                "start": records[0]["information_date"] if records else None,
                "end": records[-1]["information_date"] if records else None,
            },
        }
    payload = {
        "schema_version": 1,
        "family_id": config["family_id"],
        "status": "DEVELOPMENT_TARGET_PANEL",
        "outcomes_consulted": True,
        "target_contract": config["target_contract"],
        "assets": assets,
        "predeclaration": {"path": str(args.config), "sha256": sha256(args.config)},
    }
    write_json(args.output, payload)
    print(json.dumps({symbol: value["summary"] for symbol, value in assets.items()}, indent=2))


if __name__ == "__main__":
    main()
