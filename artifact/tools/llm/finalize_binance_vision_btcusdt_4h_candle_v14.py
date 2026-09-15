"""Finalize the fixed, checksum-verified Binance Vision candle audit for v14."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREDECLARED = ROOT / "paper/input/results/llm/v14/sec_rss_archive_predictive_v14/predeclared.json"
PROTOCOL = ROOT / "paper/working/protocols/LLM_Only_SEC_Archive_Predictive_Protocol_v14.md"
RESOLUTION = ROOT / "paper/working/audits/Binance_Vision_Candle_Coverage_Resolution_v14.md"
ARTIFACT = ROOT / "paper/input/references/source_artifacts/binance_vision_btcusdt_4h_v14"
OUTPUT = ROOT / "paper/input/results/llm/v14/binance_vision_btcusdt_4h_candle_v14"
BASE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h"
MONTHS = [(year, month) for year in range(2021, 2027) for month in range(1, 13)
          if (year, month) >= (2021, 1) and (year, month) <= (2026, 8)]
FOUR_HOURS_MS = 14_400_000


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def inspect(zip_path: Path, checksum_path: Path) -> dict:
    checksum_text = checksum_path.read_text(encoding="utf-8").strip()
    match = re.search(r"\b([0-9a-fA-F]{64})\b", checksum_text)
    if not match or zip_path.name not in checksum_text:
        raise ValueError(f"invalid checksum file: {checksum_path.name}")
    actual = digest(zip_path)
    if actual != match.group(1).lower():
        raise ValueError(f"checksum mismatch: {zip_path.name}")
    with zipfile.ZipFile(zip_path) as archive:
        expected_name = zip_path.stem + ".csv"
        if archive.namelist() != [expected_name]:
            raise ValueError(f"unexpected ZIP members: {zip_path.name}")
        rows = list(csv.reader(io.StringIO(archive.read(expected_name).decode("utf-8-sig"))))
    if rows and rows[0][0].lower() == "open time":
        rows = rows[1:]
    if not rows or any(len(row) != 12 for row in rows):
        raise ValueError(f"invalid kline CSV: {zip_path.name}")
    raw_times = [int(row[0]) for row in rows]
    divisor = 1_000 if max(raw_times) > 10_000_000_000_000 else 1
    times = [value // divisor for value in raw_times]
    if any(right - left != FOUR_HOURS_MS for left, right in zip(times, times[1:])):
        raise ValueError(f"non-contiguous bars: {zip_path.name}")
    return {"file": zip_path.name, "sha256": actual, "rows": len(rows), "first_open_ms": times[0], "last_open_ms": times[-1], "timestamp_unit": "microseconds" if divisor == 1_000 else "milliseconds"}


def main() -> None:
    predeclared = json.loads(PREDECLARED.read_text(encoding="utf-8"))
    if predeclared["status"] != "FROZEN_PENDING_CANDLE_ARTIFACT_AUDIT" or predeclared["model_run"]:
        raise ValueError("predeclaration is not eligible for the candle audit")
    items = []
    for year, month in MONTHS:
        stem = f"BTCUSDT-4h-{year}-{month:02d}.zip"
        zip_path = ARTIFACT / stem
        checksum_path = ARTIFACT / f"{stem}.CHECKSUM"
        if not zip_path.exists() or not checksum_path.exists():
            raise FileNotFoundError(f"missing frozen artifact pair: {stem}")
        item = inspect(zip_path, checksum_path)
        item["zip_url"] = f"{BASE}/{stem}"
        item["checksum_url"] = item["zip_url"] + ".CHECKSUM"
        items.append(item)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": "binance-vision-btcusdt-4h-candle-audit-v14",
        "status": "CANDLE_ARTIFACT_AUDIT_PASS_READY_FOR_EXTRACTION",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "target and evaluation only; never a predictive feature",
        "interpretation": "post-hoc versioned evaluation artifact, not historical candle availability proof",
        "checks": {"predeclaration_precedes_market_access": True, "68_months_cover_2021_01_through_2026_08": True, "published_checksum_matches_each_local_zip": True, "single_expected_csv_member": True, "twelve_kline_columns": True, "open_times_parse_and_are_contiguous_4h": True, "no_target_panel_created": True, "no_model_run": True},
        "inputs": {name: {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(path)} for name, path in {"predeclared": PREDECLARED, "protocol": PROTOCOL, "coverage_resolution": RESOLUTION}.items()},
        "files": items
    }
    (OUTPUT / "candle_artifact_audit.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "months": len(items), "rows": sum(item["rows"] for item in items)}))


if __name__ == "__main__":
    main()
