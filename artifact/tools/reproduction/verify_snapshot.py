"""Verify repository files against the migrated auto-trading snapshot manifest."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "reproduction" / "auto_trading_snapshot_manifest.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(manifest_path: Path) -> dict[str, object]:
    failures: list[str] = []
    checked = 0
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            relative = row["path"]
            path = ROOT / Path(relative)
            if not path.is_file():
                failures.append(f"missing: {relative}")
                continue
            if path.stat().st_size != int(row["bytes"]):
                failures.append(f"size mismatch: {relative}")
                continue
            if sha256(path) != row["sha256"].lower():
                failures.append(f"hash mismatch: {relative}")
                continue
            checked += 1
    return {
        "manifest": str(manifest_path),
        "verified": checked,
        "passed": not failures,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    result = verify(args.manifest.resolve())
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
