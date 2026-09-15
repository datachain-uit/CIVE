#!/usr/bin/env python3
"""Check or synchronize files shared by artifact/ and the ignored cowork/ tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ARTIFACT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = ARTIFACT_ROOT.parent
DEFAULT_COWORK_ROOT = WORKSPACE_ROOT / "cowork"
PATH_LIST = ARTIFACT_ROOT / "reproduction" / "cowork_mirror_paths.txt"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_entries() -> list[str]:
    entries = []
    for raw in PATH_LIST.read_text(encoding="utf-8").splitlines():
        value = raw.strip()
        if value and not value.startswith("#"):
            entries.append(value)
    return entries


def is_transient(relative: Path) -> bool:
    name = relative.name
    return (
        "__pycache__" in relative.parts
        or relative.suffix in {".pyc", ".pyo"}
        or name.startswith("~$")
        or name.endswith(".inspect.ndjson")
    )


def source_files(entry: str):
    source = ARTIFACT_ROOT / entry
    if not source.exists():
        raise FileNotFoundError(f"Missing artifact source: {source}")
    if source.is_file():
        relative = Path(entry)
        if not is_transient(relative):
            yield source, relative
        return
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(ARTIFACT_ROOT)
        if path.is_file() and not is_transient(relative):
            yield path, relative


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Report missing or different cowork copies.")
    mode.add_argument("--sync", action="store_true", help="Copy missing or different artifact files to cowork.")
    parser.add_argument("--cowork-root", type=Path, default=DEFAULT_COWORK_ROOT)
    args = parser.parse_args()

    cowork_root = args.cowork_root.resolve()
    workspace_root = WORKSPACE_ROOT.resolve()
    if cowork_root != workspace_root / "cowork":
        try:
            cowork_root.relative_to(workspace_root)
        except ValueError as exc:
            raise SystemExit(f"Refusing destination outside workspace: {cowork_root}") from exc

    checked = copied = missing = different = 0
    details = []
    for entry in load_entries():
        for source, relative in source_files(entry):
            destination = cowork_root / relative
            checked += 1
            if not destination.exists():
                missing += 1
                state = "missing"
            elif destination.stat().st_size != source.stat().st_size or sha256(destination) != sha256(source):
                different += 1
                state = "different"
            else:
                continue

            if args.sync:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                copied += 1
            elif len(details) < 100:
                details.append({"path": relative.as_posix(), "state": state})

    report = {
        "artifact_root": str(ARTIFACT_ROOT),
        "cowork_root": str(cowork_root),
        "checked": checked,
        "missing": missing,
        "different": different,
        "copied": copied,
        "in_sync": missing == 0 and different == 0,
        "details": details,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if args.sync or report["in_sync"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
