"""Audit a locally materialized, pinned Bitcoin-news snapshot without outcomes or models."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v12_1"
CLONE = ROOT / "runtime/external/bitcoin_news_mouadja02_v12_1"
OUT = ROOT / "paper/input/results/llm" / VERSION
SOURCE_AUDIT = OUT / "bitcoin_news_source_audit_v12_1.json"
REQUIRED_COLUMNS = [
    "DATETIME", "HEADLINE", "SUMMARY", "SOURCE", "URL",
    "CATEGORIES", "TAGS", "API_SOURCE", "FILE_NAME", "CREATED_AT",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True, encoding="utf-8").strip()


def lfs_objects(clone: Path) -> dict[str, str]:
    lines = command("git", "-C", str(clone), "lfs", "ls-files", "-l").splitlines()
    objects = {}
    for line in lines:
        parts = line.split()
        if len(parts) >= 3:
            objects[parts[-1]] = parts[0]
    return objects


def audit_tsv(path: Path) -> dict:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=chr(9))
        if reader.fieldnames != REQUIRED_COLUMNS:
            raise ValueError(f"Unexpected TSV schema: {reader.fieldnames}")
        rows = list(reader)
    if not rows:
        raise ValueError("TSV contains no records")
    values = {name: [row[name] for row in rows] for name in REQUIRED_COLUMNS}
    datetime_values = values["DATETIME"]
    created_values = values["CREATED_AT"]
    return {
        "row_count": len(rows),
        "columns": reader.fieldnames,
        "datetime_min_lexical": min(datetime_values),
        "datetime_max_lexical": max(datetime_values),
        "datetime_has_explicit_timezone": any(value.endswith("Z") or "+" in value[10:] for value in datetime_values),
        "created_at_has_explicit_timezone": any(value.endswith("Z") or "+" in value[10:] for value in created_values),
        "null_or_empty_counts": {name: sum(not value.strip() for value in values[name]) for name in REQUIRED_COLUMNS},
        "duplicate_url_count": len(rows) - len(set(values["URL"])),
        "api_source_counts": dict(sorted(Counter(values["API_SOURCE"]).items())),
    }


def main() -> None:
    output = OUT / "bitcoin_news_snapshot_schema_audit_v12_1.json"
    if output.exists():
        raise SystemExit("Audit output exists; preserve evidence and version a rerun.")
    source = json.loads(SOURCE_AUDIT.read_text(encoding="utf-8"))
    expected_revision = source["candidate"]["revision"]
    expected_parquet_sha = source["candidate"]["parquet_lfs"]["sha256"]
    if not CLONE.is_dir():
        raise SystemExit(f"Missing pinned local clone: {CLONE}")
    actual_revision = command("git", "-C", str(CLONE), "rev-parse", "HEAD")
    if actual_revision != expected_revision:
        raise ValueError(f"Revision mismatch: {actual_revision} != {expected_revision}")
    parquet = CLONE / "bitcoin-news.parquet"
    tsv = CLONE / "bitcoin-news.tsv"
    lfs = lfs_objects(CLONE)
    parquet_sha = sha256_file(parquet)
    tsv_sha = sha256_file(tsv)
    if parquet_sha != expected_parquet_sha:
        raise ValueError("Parquet SHA-256 differs from source-audit LFS pointer")
    if lfs.get(parquet.name) != parquet_sha or lfs.get(tsv.name) != tsv_sha:
        raise ValueError("Git LFS object ID differs from local file SHA-256")
    tsv_audit = audit_tsv(tsv)
    report = {
        "status": "VERSIONED_SNAPSHOT_AUDITED_NOT_ADMITTED_PENDING_TERMS_AND_PIT_GATE",
        "scope": "pinned snapshot identity and outcome-blind TSV schema only",
        "source_audit": str(SOURCE_AUDIT.relative_to(ROOT)),
        "revision": actual_revision,
        "snapshot": {
            "parquet": {"bytes": parquet.stat().st_size, "sha256": parquet_sha, "lfs_oid_verified": True},
            "tsv": {"bytes": tsv.stat().st_size, "sha256": tsv_sha, "lfs_oid_verified": True},
        },
        "tsv_schema_audit": tsv_audit,
        "admission": {
            "outcome_blind": True,
            "market_data_accessed": False,
            "model_run": False,
            "eligible_for_model_input": False,
            "blocking_reasons": [
                "DATETIME and CREATED_AT lack explicit timezone in the audited TSV.",
                "Dataset timestamp fields do not independently certify historical point-in-time availability.",
                "README requires review of original publishers' terms before text is admitted.",
            ],
        },
        "next_gate": [
            "Document source-term assessment for The Guardian, Finnhub and AlphaVantage-derived text.",
            "Define conservative timezone policy or exclude records with ambiguous timestamps.",
            "Freeze an outcome-blind corpus contract before any market-data join.",
        ],
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "rows": tsv_audit["row_count"],
        "datetime_timezone": tsv_audit["datetime_has_explicit_timezone"],
        "duplicate_urls": tsv_audit["duplicate_url_count"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
