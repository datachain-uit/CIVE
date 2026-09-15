#!/usr/bin/env python3
"""Freeze outcome-free Binance Vision BTCUSDT 4h monthly archive availability for 2017."""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "paper/input/references/source_artifacts/binance_vision_btcusdt_4h_v16/source_screen.json"
BASE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h"
DOC = "https://github.com/binance/binance-public-data/blob/master/README.md"


def head(url: str) -> dict:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "KLTN-v16-target-coverage-screen/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return {"status": response.status, "content_length": int(response.headers.get("Content-Length", 0))}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "content_length": 0}


def main() -> None:
    months = []
    for month in range(1, 13):
        name = f"BTCUSDT-4h-2017-{month:02d}.zip"
        zip_url = f"{BASE}/{name}"
        checksum_url = zip_url + ".CHECKSUM"
        months.append({
            "month": f"2017-{month:02d}",
            "zip_url": zip_url,
            "zip_head": head(zip_url),
            "checksum_url": checksum_url,
            "checksum_head": head(checksum_url),
        })
    available = [item["month"] for item in months if item["zip_head"]["status"] == 200 and item["checksum_head"]["status"] == 200]
    first = available[0] if available else None
    checks = {
        "january_through_july_absent": all(item["zip_head"]["status"] == 404 for item in months[:7]),
        "august_zip_and_checksum_available": months[7]["zip_head"]["status"] == 200 and months[7]["checksum_head"]["status"] == 200,
        "august_is_first_available_2017_month": first == "2017-08",
        "no_market_values_downloaded": True,
        "no_outcomes_or_predictions_consulted": True,
    }
    payload = {
        "schema_version": "binance-vision-btcusdt-4h-source-screen-v16",
        "screened_at": datetime.now(timezone.utc).isoformat(),
        "status": "SOURCE_START_SCREEN_PASS" if all(checks.values()) else "SOURCE_START_SCREEN_FAIL",
        "source": {"publisher": "Binance Vision", "symbol": "BTCUSDT", "market": "spot", "interval": "4h", "documentation": DOC},
        "first_available_month": first,
        "months": months,
        "checks": checks,
        "selection_uses_outcomes": False,
        "market_values_downloaded": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "first_available_month": first, "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}))
    if payload["status"] != "SOURCE_START_SCREEN_PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
