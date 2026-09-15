"""Build leakage-safe raw outcome targets for the event/risk LLM v3 protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


FOUR_HOURS_MS = 4 * 60 * 60 * 1000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class BarSeries:
    def __init__(self, rows: list[list[float]]) -> None:
        self.by_time = {int(row[0]): row for row in rows}

    def row_at(self, timestamp_ms: int) -> list[float] | None:
        return self.by_time.get(timestamp_ms)

    def rows_between(self, start_ms: int, end_ms: int) -> list[list[float]] | None:
        rows = [self.by_time.get(ts) for ts in range(start_ms, end_ms, FOUR_HOURS_MS)]
        return None if not rows or any(row is None for row in rows) else rows


def raw_targets(series: BarSeries, cutoff_ms: int, delay_hours: int,
                horizons: tuple[int, ...]) -> dict[str, float] | None:
    entry_ms = cutoff_ms + delay_hours * 60 * 60 * 1000
    entry_row = series.row_at(entry_ms)
    if entry_row is None:
        return None
    entry = float(entry_row[1])
    result: dict[str, float] = {}
    for hours in horizons:
        exit_ms = entry_ms + hours * 60 * 60 * 1000
        exit_row = series.row_at(exit_ms)
        path = series.rows_between(entry_ms, exit_ms)
        if exit_row is None or path is None:
            return None
        highs = [float(row[2]) for row in path]
        lows = [float(row[3]) for row in path]
        closes = [float(row[4]) for row in path]
        log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        prefix = f"h{hours}"
        result[f"{prefix}_return"] = float(exit_row[1]) / entry - 1.0
        result[f"{prefix}_max_favorable_excursion"] = max(highs) / entry - 1.0
        result[f"{prefix}_max_adverse_excursion"] = min(lows) / entry - 1.0
        result[f"{prefix}_realized_volatility"] = math.sqrt(sum(value * value for value in log_returns))
    return result


def build(information_sets_path: Path, btc_bars_path: Path, output_path: Path,
          delay_hours: int = 4, horizons: tuple[int, ...] = (4, 12, 24, 72)) -> dict:
    if any(hours <= 0 or hours % 4 for hours in horizons):
        raise ValueError("all horizons must be positive multiples of four hours")
    source = json.loads(information_sets_path.read_text(encoding="utf-8"))
    series = BarSeries(json.loads(btc_bars_path.read_text(encoding="utf-8")))
    records = []
    missing = 0
    for item in source["records"]:
        cutoff = datetime.fromisoformat(item["available_at"]).astimezone(timezone.utc)
        cutoff_ms = int(cutoff.timestamp() * 1000)
        targets = raw_targets(series, cutoff_ms, delay_hours, horizons)
        if targets is None:
            missing += 1
            continue
        record = {
            "information_date": item["information_date"],
            "available_at": item["available_at"],
            "source_snapshot_hash": item["source_snapshot_hash"],
            "entry_at": datetime.fromtimestamp(
                (cutoff_ms + delay_hours * 60 * 60 * 1000) / 1000, timezone.utc
            ).isoformat(),
            "targets": targets,
        }
        record["record_hash"] = canonical_hash(record)
        records.append(record)

    payload = {
        "schema_version": 1,
        "experiment_id": "llm-event-risk-v3-target-panel-development",
        "status": "development-target-audit-no-model-selection",
        "policy": {
            "information_cutoff": "available_at from causal daily information set",
            "execution_delay_hours": delay_hours,
            "horizons_hours": list(horizons),
            "target_family": ["return", "realized_volatility", "max_favorable_excursion", "max_adverse_excursion"],
            "classification_thresholds": "not defined here; derive inside each training fold only",
            "target_selection": "prohibited until protocol predeclaration and walk-forward evaluation",
        },
        "sources": {
            "information_sets": {"path": str(information_sets_path), "sha256": sha256(information_sets_path)},
            "btc_bars": {"path": str(btc_bars_path), "sha256": sha256(btc_bars_path)},
        },
        "summary": {
            "source_records": len(source["records"]),
            "complete_records": len(records),
            "missing_records": missing,
            "coverage_start": records[0]["information_date"] if records else None,
            "coverage_end": records[-1]["information_date"] if records else None,
        },
        "records": records,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--information-sets", type=Path, required=True)
    parser.add_argument("--btc-bars", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--delay-hours", type=int, default=4)
    parser.add_argument("--horizons", type=int, nargs="+", default=[4, 12, 24, 72])
    args = parser.parse_args()
    payload = build(
        args.information_sets, args.btc_bars, args.output,
        args.delay_hours, tuple(sorted(set(args.horizons))),
    )
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
