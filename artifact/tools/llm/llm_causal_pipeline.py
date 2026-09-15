"""Causal, auditable news corpus and LLM assessment primitives."""
from __future__ import annotations

import hashlib
import json
import re
import time as time_module
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from statistics import median

UTC = timezone.utc

def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()

def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()

def parse_source_time(value: str) -> tuple[datetime, bool]:
    raw = str(value).strip()
    date_only = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw))
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC), date_only

def causal_availability(value: str) -> tuple[datetime, datetime, str]:
    published, date_only = parse_source_time(value)
    if date_only:
        available = datetime.combine(published.date() + timedelta(days=1), time.min, UTC)
        precision = "date-only-next-day"
    else:
        available, precision = published, "source-timestamp"
    return published, available, precision

@dataclass(frozen=True)
class NewsSnapshot:
    content_hash: str
    text: str
    published_at: str
    available_at: str
    timestamp_precision: str
    source_dataset: str
    source_row: int

def migrate_legacy_corpus(rows: list[dict], source_dataset: str) -> tuple[list[dict], dict]:
    migrated: list[NewsSnapshot] = []
    seen: set[str] = set()
    rejected = 0
    for index, row in enumerate(rows):
        text_value, date_value = normalize_text(str(row.get("text", ""))), row.get("date")
        if not text_value or not date_value:
            rejected += 1
            continue
        digest = content_hash(text_value)
        if digest in seen:
            continue
        published, available, precision = causal_availability(str(date_value))
        migrated.append(NewsSnapshot(
            digest, text_value, published.isoformat(), available.isoformat(), precision,
            source_dataset, index,
        ))
        seen.add(digest)
    records = [asdict(item) for item in sorted(migrated, key=lambda item: (item.available_at, item.content_hash))]
    dates = {record["published_at"][:10] for record in records}
    audit = {
        "input_rows": len(rows), "unique_records": len(records),
        "duplicates_removed": len(rows) - rejected - len(records), "rejected": rejected,
        "unique_publication_dates": len(dates),
        "coverage_start": min((r["published_at"] for r in records), default=None),
        "coverage_end": max((r["published_at"] for r in records), default=None),
        "adequate_for_four_year_backtest": False,
    }
    return records, audit

def parse_model_response(raw: str) -> dict:
    payload = json.loads(raw)
    if set(payload) != {"score", "confidence", "reason_code"}:
        raise ValueError("model response must contain exactly score, confidence and reason_code")
    score, confidence = float(payload["score"]), float(payload["confidence"])
    if not -1 <= score <= 1 or not 0 <= confidence <= 1:
        raise ValueError("model response values outside declared ranges")
    if not str(payload["reason_code"]).strip():
        raise ValueError("reason_code is required")
    return {"score": score, "confidence": confidence, "reason_code": str(payload["reason_code"])}

def aggregate_window(scored: list[dict], cutoff: datetime, hours: int = 24, minimum: int = 3) -> dict:
    cutoff = cutoff.astimezone(UTC)
    start = cutoff - timedelta(hours=hours)
    eligible = [
        row for row in scored
        if row.get("status") == "success" and start < datetime.fromisoformat(row["available_at"]) <= cutoff
    ]
    if len(eligible) < minimum:
        return {"status": "insufficient-data", "score": None, "successful_articles": len(eligible)}
    return {
        "status": "success", "score": float(median(float(row["score"]) for row in eligible)),
        "successful_articles": len(eligible),
        "source_snapshot_hash": hashlib.sha256(
            "".join(sorted(row["content_hash"] for row in eligible)).encode()
        ).hexdigest(),
    }

def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time_module.sleep(0.1 * (attempt + 1))
