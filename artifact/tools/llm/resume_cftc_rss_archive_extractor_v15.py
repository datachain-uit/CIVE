"""Resume wrapper preserving the extraction preflight timestamp across thermal restarts."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import run_cftc_rss_archive_extractor_v15 as base


original_preflight = base.preflight


def stable_preflight(output_dir: Path):
    path = output_dir / "extraction_preflight.json"
    if not path.exists():
        return original_preflight(output_dir)
    timestamp = json.loads(path.read_text(encoding="utf-8"))["created_at"]
    original_datetime = base.datetime

    class ExistingTimestamp:
        @staticmethod
        def now(_timezone):
            return datetime.fromisoformat(timestamp)

    base.datetime = ExistingTimestamp
    try:
        return original_preflight(output_dir)
    finally:
        base.datetime = original_datetime


base.preflight = stable_preflight

if __name__ == "__main__":
    base.main()
