"""Build a point-in-time, outcome-free LLM news corpus from CryptoVision v2."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from llm_causal_pipeline import causal_availability, content_hash, normalize_text

SOURCE_ID = "cryptovision-v2"
SOURCE_DOI = "10.17632/3c3xtxtfb6.2"
SOURCE_URL = "https://data.mendeley.com/datasets/3c3xtxtfb6/2"
LICENSE = "CC BY 4.0"
ALLOWED_DOMAINS = {
    "blockworks.co", "coindesk.com", "cointelegraph.com", "cryptonews.com",
    "cryptopanic.com", "decrypt.co",
}
REQUIRED_COLUMNS = {"URL", "Title", "Date Time", "Coin Type"}
LEAKAGE_COLUMNS = {
    "sentiment_label", "sentiment_score", "Open", "High", "Low", "Close",
    "Volume", "Movement_OpenClose_%", "Movement_HighLow_%", "Market_Move",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_domain(url: str) -> str:
    return urlparse(url.strip()).netloc.lower().removeprefix("www.")


def build(source: Path, output: Path, manifest_path: Path) -> dict:
    seen_text: set[str] = set()
    seen_urls: set[str] = set()
    domains: Counter[str] = Counter()
    coins: Counter[str] = Counter()
    rejection: Counter[str] = Counter()
    timestamps: list[datetime] = []
    input_rows = 0

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        csv_entries = [item for item in archive.infolist() if item.filename.lower().endswith(".csv")]
        if len(csv_entries) != 1:
            raise ValueError(f"expected exactly one CSV, found {len(csv_entries)}")
        entry = csv_entries[0]
        with archive.open(entry) as raw, gzip.open(output, "wt", encoding="utf-8", newline="\n") as target:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            columns = set(reader.fieldnames or [])
            missing = REQUIRED_COLUMNS - columns
            if missing:
                raise ValueError(f"missing required columns: {sorted(missing)}")
            present_leakage = sorted(LEAKAGE_COLUMNS & columns)
            for source_row, row in enumerate(reader, start=2):
                input_rows += 1
                text = normalize_text(row.get("Title") or "")
                url = (row.get("URL") or "").strip()
                domain = canonical_domain(url)
                if not text:
                    rejection["missing_title"] += 1
                    continue
                if not url or domain not in ALLOWED_DOMAINS:
                    rejection["missing_or_disallowed_url"] += 1
                    continue
                try:
                    published, available, precision = causal_availability(row.get("Date Time") or "")
                except (TypeError, ValueError):
                    rejection["invalid_timestamp"] += 1
                    continue
                digest = content_hash(text)
                normalized_url = url.rstrip("/")
                if digest in seen_text:
                    rejection["duplicate_title"] += 1
                    continue
                if normalized_url in seen_urls:
                    rejection["duplicate_url"] += 1
                    continue
                record = {
                    "content_hash": digest,
                    "text": text,
                    "published_at": published.isoformat(),
                    "available_at": available.isoformat(),
                    "timestamp_precision": precision,
                    "url": url,
                    "source_domain": domain,
                    "coin_type": normalize_text(row.get("Coin Type") or "unknown"),
                    "source_dataset": SOURCE_ID,
                    "source_row": source_row,
                }
                target.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                seen_text.add(digest)
                seen_urls.add(normalized_url)
                domains[domain] += 1
                coins[record["coin_type"]] += 1
                timestamps.append(published)

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_status": "development-not-frozen",
        "source": {
            "dataset": SOURCE_ID,
            "doi": SOURCE_DOI,
            "landing_page": SOURCE_URL,
            "version": 2,
            "license": LICENSE,
            "snapshot_file": str(source),
            "snapshot_bytes": source.stat().st_size,
            "snapshot_sha256": sha256_file(source),
            "archive_member": entry.filename,
        },
        "input_rows": input_rows,
        "accepted_records": len(seen_text),
        "rejected_records": sum(rejection.values()),
        "rejection_reasons": dict(sorted(rejection.items())),
        "coverage_start": min(timestamps).isoformat() if timestamps else None,
        "coverage_end": max(timestamps).isoformat() if timestamps else None,
        "unique_utc_dates": len({item.date() for item in timestamps}),
        "source_domains": dict(sorted(domains.items())),
        "coin_types": dict(coins.most_common()),
        "timestamp_policy": "exact source timestamp converted to UTC; availability equals publication",
        "deduplication": "first occurrence by normalized-title SHA-256, then normalized URL",
        "allow_list": sorted(ALLOWED_DOMAINS),
        "columns_imported": ["URL", "Title", "Date Time", "Coin Type"],
        "columns_explicitly_excluded_as_leakage": present_leakage,
        "corpus_file": str(output),
        "corpus_bytes": output.stat().st_size,
        "corpus_sha256": sha256_file(output),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = build(args.source, args.output, args.manifest)
    print(json.dumps({key: manifest[key] for key in (
        "input_rows", "accepted_records", "rejected_records", "coverage_start", "coverage_end"
    )}, indent=2))


if __name__ == "__main__":
    main()
