#!/usr/bin/env python3
"""Checkpointed outcome-blind download of pinned ECB RSS archive snapshots for v16."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCREEN = ROOT / "paper/input/references/source_artifacts/ecb_rss_internet_archive_v16/source_screen.json"
PREDECLARED = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_corpus_v16/predeclared.json"
SOURCE_DIR = ROOT / "paper/input/references/source_artifacts/ecb_rss_internet_archive_v16/rss_snapshots"
PROGRESS = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_corpus_v16/download_progress.json"
FEED = "https://www.ecb.europa.eu/rss/press.html"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def fetch(url: str, timeout: int) -> bytes:
    last = None
    for attempt in range(5):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "KLTN-ECB-RSS-v16-provenance-audit/1.0",
                    "Accept": "application/rss+xml, application/xml, text/xml",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                return response.read()
        except Exception as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(str(last))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    screen = json.loads(SCREEN.read_text(encoding="utf-8"))
    predeclared = json.loads(PREDECLARED.read_text(encoding="utf-8"))
    if screen["decision"] != "SOURCE_SCREEN_PASS_TITLE_ONLY_FULL_OUTCOME_BLIND_CORPUS_AUDIT_REQUIRED":
        raise RuntimeError("source screen did not authorize corpus audit")
    if digest(SCREEN.read_bytes()) != predeclared["source_screen"]["sha256"]:
        raise RuntimeError("source screen hash differs from predeclaration")
    if any(predeclared[key] is not False for key in (
        "market_data_accessed", "outcomes_consulted", "model_run", "trading_backtest_consulted"
    )):
        raise RuntimeError("predeclaration is not outcome-blind")
    rows = screen["archive"]["rows"]
    if len(rows) != predeclared["source_screen"]["expected_snapshots"]:
        raise RuntimeError("snapshot count differs from predeclaration")
    completed = []
    errors = []
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    for index, row in enumerate(rows, 1):
        timestamp = row["timestamp"]
        target = SOURCE_DIR / f"{timestamp}.xml"
        state = "existing"
        try:
            if not target.exists():
                replay = f"https://web.archive.org/web/{timestamp}id_/{FEED}"
                body = fetch(replay, args.timeout)
                temporary = target.with_suffix(".xml.tmp")
                temporary.write_bytes(body)
                temporary.replace(target)
                state = "downloaded"
                time.sleep(args.delay)
            body = target.read_bytes()
            completed.append({
                "timestamp": timestamp,
                "cdx_digest": row["digest"],
                "cdx_length": row["length"],
                "file": str(target.relative_to(ROOT)).replace("\\", "/"),
                "sha256": digest(body),
                "bytes": len(body),
                "state": state,
            })
        except Exception as exc:
            errors.append({"timestamp": timestamp, "error": f"{type(exc).__name__}: {exc}"})
        payload = {
            "schema_version": "ecb-rss-archive-download-progress-v16",
            "status": "DOWNLOAD_COMPLETE" if index == len(rows) and not errors else "DOWNLOAD_IN_PROGRESS",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "expected": len(rows),
            "processed": index,
            "success": len(completed),
            "errors": errors,
            "market_data_accessed": False,
            "outcomes_consulted": False,
            "records": completed,
        }
        atomic_json(PROGRESS, payload)
        if index % 25 == 0 or index == len(rows):
            print(f"{index}/{len(rows)} success={len(completed)} errors={len(errors)}", flush=True)
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
