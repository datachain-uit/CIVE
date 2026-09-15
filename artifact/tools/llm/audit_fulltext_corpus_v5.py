import argparse
import csv
import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


SPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")


def normalize_text(value: str) -> str:
    return SPACE_RE.sub(" ", html.unescape(value or "")).strip()


def canonical_url(value: str) -> str:
    value = normalize_text(value)
    if not value:
        return ""
    parts = urlsplit(value)
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower() or "https", host, path, "", ""))


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def floor_4h(timestamp: datetime) -> str:
    return timestamp.replace(hour=(timestamp.hour // 4) * 4, minute=0, second=0, microsecond=0).isoformat()


def percentile(values: list[int], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def audit(input_path: Path) -> dict:
    csv.field_size_limit(2**31 - 1)
    rows = 0
    valid_timestamps = 0
    urls: set[str] = set()
    ids: set[str] = set()
    bodies: set[str] = set()
    titles: set[str] = set()
    sources = Counter()
    years = Counter()
    buckets = Counter()
    bucket_sources: dict[str, set[str]] = defaultdict(set)
    word_counts: list[int] = []
    body_thresholds = Counter()
    earliest = None
    latest = None

    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"id", "published_on", "title", "body", "url", "source"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")
        for row in reader:
            rows += 1
            title = normalize_text(row.get("title", ""))
            body = normalize_text(row.get("body", ""))
            url = canonical_url(row.get("url", ""))
            source = normalize_text(row.get("source", "")).lower() or "unknown"
            identity = url or normalize_text(row.get("guid", "")) or normalize_text(row.get("id", ""))
            ids.add(identity)
            if url:
                urls.add(url)
            if title:
                titles.add(hashlib.sha256(title.lower().encode("utf-8")).hexdigest())
            if body:
                bodies.add(hashlib.sha256(body.lower().encode("utf-8")).hexdigest())
            count = len(WORD_RE.findall(body))
            word_counts.append(count)
            for threshold in (20, 50, 100, 200, 500):
                if count >= threshold:
                    body_thresholds[str(threshold)] += 1
            sources[source] += 1
            try:
                timestamp = parse_timestamp(row.get("published_on", ""))
            except (TypeError, ValueError):
                continue
            valid_timestamps += 1
            earliest = timestamp if earliest is None or timestamp < earliest else earliest
            latest = timestamp if latest is None or timestamp > latest else latest
            years[str(timestamp.year)] += 1
            bucket = floor_4h(timestamp)
            buckets[bucket] += 1
            bucket_sources[bucket].add(source)

    multi_source_buckets = sum(1 for value in bucket_sources.values() if len(value) >= 2)
    return {
        "schema_version": "llm-fulltext-corpus-audit-v5",
        "input": {
            "path": str(input_path.resolve()),
            "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
            "bytes": input_path.stat().st_size,
        },
        "counts": {
            "rows": rows,
            "valid_timestamps": valid_timestamps,
            "unique_article_identities": len(ids),
            "unique_canonical_urls": len(urls),
            "unique_normalized_titles": len(titles),
            "unique_normalized_bodies": len(bodies),
            "sources": len(sources),
            "four_hour_buckets": len(buckets),
            "multi_source_four_hour_buckets": multi_source_buckets,
        },
        "coverage": {
            "earliest_utc": earliest.isoformat() if earliest else None,
            "latest_utc": latest.isoformat() if latest else None,
            "rows_by_year": dict(sorted(years.items())),
        },
        "body_word_counts": {
            "p10": percentile(word_counts, 0.10),
            "p25": percentile(word_counts, 0.25),
            "median": percentile(word_counts, 0.50),
            "p75": percentile(word_counts, 0.75),
            "p90": percentile(word_counts, 0.90),
            "at_least": dict(body_thresholds),
        },
        "four_hour_bucket_size": {
            "median": percentile(list(buckets.values()), 0.50),
            "p90": percentile(list(buckets.values()), 0.90),
            "max": max(buckets.values(), default=0),
        },
        "top_sources": sources.most_common(25),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
