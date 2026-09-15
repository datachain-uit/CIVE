"""Create auditable manifests for Technical research results."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: Path) -> dict:
    resolved = path.resolve()
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "bytes": stat.st_size,
        "sha256": sha256_file(resolved),
    }


def _git(repo_root: Path, *arguments: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-c", f"safe.directory={repo_root.as_posix()}", "-C", str(repo_root), *arguments],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def build_experiment_manifest(
    *, repo_root: Path, result_path: Path, configuration: dict,
    data_paths: Iterable[Path], source_paths: Iterable[Path],
    execution_semantics: str, event_order: Iterable[str],
) -> dict:
    unique_data = sorted({Path(path).resolve() for path in data_paths}, key=str)
    unique_sources = sorted({Path(path).resolve() for path in source_paths}, key=str)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": _git(repo_root, "rev-parse", "HEAD"),
        "git_status_porcelain": _git(repo_root, "status", "--short"),
        "execution_semantics": execution_semantics,
        "event_order": list(event_order),
        "configuration": configuration,
        "result": _file_record(result_path),
        "sources": [_file_record(path) for path in unique_sources],
        "data": [_file_record(path) for path in unique_data],
    }


def write_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
