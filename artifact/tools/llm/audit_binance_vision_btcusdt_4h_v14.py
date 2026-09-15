"""Download and verify the predeclared Binance Vision target artifact for v14.

This program deliberately creates no target panel and no model input. It only pins
the published ZIP/CHECKSUM pairs and verifies the fixed 4-hour kline structure.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREDECLARED = ROOT / "paper/input/results/llm/v14/sec_rss_archive_predictive_v14/predeclared.json"
PROTOCOL = ROOT / "paper/working/protocols/LLM_Only_SEC_Archive_Predictive_Protocol_v14.md"
OUTPUT = ROOT / "paper/input/results/llm/v14/binance_vision_btcusdt_4h_candle_v14"
ARTIFACT = ROOT / "paper/input/references/source_artifacts/binance_vision_btcusdt_4h_v14"
BASE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h"
MONTHS = [(year, month) for year in range(2021, 2027) for month in range(1, 13)
          if (year, month) >= (2021, 1) and (year, month) <= (2026, 9)]
EXPECTED_COLUMNS = 12
FOUR_HOURS_MS = 4 * 60 * 60 * 1000


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "KLTN-v14-reproducibility-audit/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP {response.status} for {url}")
        return response.read()


def expected_checksum(raw: bytes, zip_name: str) -> str:
    text = raw.decode("utf-8").strip()
    match = re.search(r"\b([a-fA-F0-9]{64})\b", text)
    if not match or zip_name not in text:
        raise ValueError(f"malformed checksum for {zip_name}: {text!r}")
    return match.group(1).lower()


def parse_rows(zip_bytes: bytes, zip_name: str) -> tuple[int, int, int, int]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = archive.namelist()
        expected_csv = zip_name.removesuffix(".zip") + ".csv"
        if names != [expected_csv]:
            raise ValueError(f"unexpected ZIP members for {zip_name}: {names}")
        decoded = archive.read(expected_csv).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(decoded)))
    if not rows:
        raise ValueError(f"empty CSV for {zip_name}")
    if not all(len(row) == EXPECTED_COLUMNS for row in rows):
        raise ValueError(f"unexpected column count for {zip_name}")
    if rows[0][0].lower() == "open time":
        rows = rows[1:]
    if not rows:
        raise ValueError(f"CSV lacks data rows for {zip_name}")
    times = [int(row[0]) for row in rows]
    unit = 1_000 if max(times) > 10_000_000_000_000 else 1
    times_ms = [value // unit for value in times]
    if any((right - left) != FOUR_HOURS_MS for left, right in zip(times_ms, times_ms[1:])):
        raise ValueError(f"non-contiguous 4h open times for {zip_name}")
    return len(rows), times_ms[0], times_ms[-1], unit


def main() -> None:
    predeclared = json.loads(PREDECLARED.read_text(encoding="utf-8"))
    if predeclared["status"] != "FROZEN_PENDING_CANDLE_ARTIFACT_AUDIT":
        raise ValueError("v14 candle audit requires the frozen predeclaration")
    if predeclared["market_data_accessed"] or predeclared["model_run"]:
        raise ValueError("predeclaration must precede target access and model execution")

    ARTIFACT.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    files = []
    for year, month in MONTHS:
        stem = f"BTCUSDT-4h-{year}-{month:02d}"
        zip_name = f"{stem}.zip"
        zip_url = f"{BASE}/{zip_name}"
        checksum_url = f"{zip_url}.CHECKSUM"
        checksum_raw = read_url(checksum_url)
        zip_raw = read_url(zip_url)
        expected = expected_checksum(checksum_raw, zip_name)
        actual = sha256_bytes(zip_raw)
        if actual != expected:
            raise ValueError(f"checksum mismatch for {zip_name}: {actual} != {expected}")
        rows, first_ms, last_ms, unit = parse_rows(zip_raw, zip_name)
        zip_path = ARTIFACT / zip_name
        checksum_path = ARTIFACT / f"{zip_name}.CHECKSUM"
        zip_path.write_bytes(zip_raw)
        checksum_path.write_bytes(checksum_raw)
        files.append({
            "month": f"{year}-{month:02d}", "zip_url": zip_url, "checksum_url": checksum_url,
            "zip": str(zip_path.relative_to(ROOT)).replace("\\", "/"),
            "checksum": str(checksum_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": actual, "rows": rows, "first_open_ms": first_ms, "last_open_ms": last_ms,
            "timestamp_unit": "microseconds" if unit == 1_000 else "milliseconds"
        })

    result = {
        "schema_version": "binance-vision-btcusdt-4h-candle-audit-v14",
        "status": "CANDLE_ARTIFACT_AUDIT_PASS_READY_FOR_EXTRACTION",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "target and evaluation only; never a predictive feature",
        "interpretation": "post-hoc versioned evaluation artifact, not historical candle availability proof",
        "source": {"publisher": "Binance Vision", "asset": "BTCUSDT spot", "interval": "4h"},
        "checks": {
            "predeclaration_precedes_market_access": True,
            "published_checksum_matches_each_local_zip": True,
            "single_expected_csv_member": True,
            "twelve_kline_columns": True,
            "open_times_parse_and_are_contiguous_4h": True,
            "months_cover_2021_01_through_2026_09": True,
            "no_target_panel_created": True,
            "no_model_run": True
        },
        "inputs": {
            "predeclared": {"path": str(PREDECLARED.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256_file(PREDECLARED)},
            "protocol": {"path": str(PROTOCOL.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256_file(PROTOCOL)}
        },
        "files": files
    }
    (OUTPUT / "candle_artifact_audit.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "months": len(files), "rows": sum(item["rows"] for item in files)}))


if __name__ == "__main__":
    main()
