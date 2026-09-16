#!/usr/bin/env python3
"""Create a portable copy of a frozen config without modifying frozen evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
from typing import Any


ARTIFACT_ROOT = Path(__file__).resolve().parents[2]
LEGACY_ROOTS = (
    PureWindowsPath("D:/UIT/KLTN"),
    PureWindowsPath("D:/projects/auto-trading"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_path(value: str) -> Path:
    windows_value = PureWindowsPath(value)
    if windows_value.is_absolute():
        for legacy_root in LEGACY_ROOTS:
            try:
                relative = windows_value.relative_to(legacy_root)
            except ValueError:
                continue
            return (ARTIFACT_ROOT / Path(*relative.parts)).resolve()

        raise ValueError(f"unsupported absolute path in frozen config: {value}")

    candidate = Path(value)
    if not candidate.is_absolute():
        return (ARTIFACT_ROOT / Path(value.replace("\\", "/"))).resolve()

    raise ValueError(f"unsupported absolute path in frozen config: {value}")


def rewrite_paths(value: Any) -> Any:
    if isinstance(value, list):
        return [rewrite_paths(item) for item in value]
    if not isinstance(value, dict):
        return value

    rewritten = {key: rewrite_paths(item) for key, item in value.items()}
    if isinstance(value.get("path"), str):
        resolved = portable_path(value["path"])
        if not resolved.is_file():
            raise FileNotFoundError(f"mapped artifact does not exist: {resolved}")
        rewritten["path"] = str(resolved)
        expected = value.get("sha256")
        if isinstance(expected, str):
            actual = sha256(resolved)
            if actual != expected:
                raise ValueError(
                    f"SHA-256 mismatch after path mapping: {resolved}\n"
                    f"expected {expected}\nactual   {actual}"
                )
    return rewritten


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Map legacy absolute paths in a frozen JSON config to this artifact clone."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    rewritten = rewrite_paths(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rewritten, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "PORTABLE_CONFIG_CREATED",
                "source": str(args.input),
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
