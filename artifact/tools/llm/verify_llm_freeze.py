"""Verify the sealed manifest and every copied artifact in an LLM evidence freeze."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(directory: Path) -> dict:
    manifest_path = directory / "manifest.json"
    seal_path = directory / "MANIFEST.SHA256"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_manifest_hash = seal_path.read_text(encoding="ascii").split()[0]
    failures = []
    if sha256(manifest_path) != expected_manifest_hash:
        failures.append("manifest seal mismatch")
    total_size = 0
    for item in manifest["artifacts"]:
        path = directory / item["snapshot_path"]
        if not path.is_file():
            failures.append(f"missing: {item['snapshot_path']}")
            continue
        total_size += path.stat().st_size
        if path.stat().st_size != item["size_bytes"]:
            failures.append(f"size mismatch: {item['snapshot_path']}")
        if sha256(path) != item["sha256"]:
            failures.append(f"hash mismatch: {item['snapshot_path']}")
    expected = manifest["summary"]
    if total_size != expected["total_size_bytes"]:
        failures.append("total size mismatch")
    result = {
        "freeze_id": manifest["freeze_id"],
        "artifact_count": len(manifest["artifacts"]),
        "verified_artifact_count": len(manifest["artifacts"]) - len([
            value for value in failures if value.startswith(("missing:", "size mismatch:", "hash mismatch:"))
        ]),
        "passed": not failures,
        "failures": failures,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = verify(args.directory)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
