"""Create an immutable, checksum-addressed snapshot of the completed LLM v1/v2 branch."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


LOCAL_SOURCES = (
    Path("paper/input/results/llm"),
    Path("paper/input/results/snapshots/llm"),
)

RUNTIME_SOURCES = (
    Path("runtime/ministral3_8b_challenger/configs"),
    Path("runtime/ministral3_8b_challenger/results"),
    Path("runtime/nemotron3_nano4b_challenger/configs"),
    Path("runtime/nemotron3_nano4b_challenger/results"),
    Path("runtime/llama31_8b_challenger/configs"),
    Path("runtime/llama31_8b_challenger/results"),
)

EXTERNAL_PATTERNS = (
    "llm_*challenger_gate*.json",
    "llm_*challenger_stage2*.json",
    "llm_*operational_gate*.json",
    "llm_*predictive_gate*.json",
    "llm_outcome_calibration*.json",
    "llm_bybit_lifecycle_full_v1_development.json",
    "llm_bybit_lifecycle_dual_run_consensus_v1_development.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_files(root: Path, source: Path) -> list[tuple[Path, str]]:
    if not source.exists():
        return []
    return [
        (path, path.relative_to(root).as_posix())
        for path in sorted(source.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".json", ".csv"}
    ]


def build_snapshot(workspace: Path, external_results: Path, destination: Path) -> dict:
    if destination.exists():
        raise FileExistsError(f"freeze destination already exists: {destination}")

    selected: list[tuple[Path, str, str]] = []
    for source in LOCAL_SOURCES:
        for path, relative in collect_files(workspace, workspace / source):
            selected.append((path, f"workspace/{relative}", "workspace"))
    for source in RUNTIME_SOURCES:
        for path, relative in collect_files(workspace, workspace / source):
            selected.append((path, f"workspace/{relative}", "runtime"))

    external_seen: set[Path] = set()
    for pattern in EXTERNAL_PATTERNS:
        for path in sorted(external_results.glob(pattern)):
            resolved = path.resolve()
            if resolved not in external_seen:
                external_seen.add(resolved)
                selected.append((path, f"external/{path.name}", "external-production"))

    if not selected:
        raise ValueError("no evidence files selected")

    artifacts = []
    for source, relative, origin in selected:
        target = destination / "artifacts" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_hash = sha256(source)
        copied_hash = sha256(target)
        if source_hash != copied_hash:
            raise IOError(f"copy verification failed: {source}")
        artifacts.append({
            "snapshot_path": target.relative_to(destination).as_posix(),
            "source_path": str(source.resolve()),
            "origin": origin,
            "size_bytes": target.stat().st_size,
            "sha256": copied_hash,
        })

    manifest = {
        "schema_version": 1,
        "freeze_id": "llm-direct-direction-v1-v2-negative-evidence",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": (
            "Completed development evidence for direct sentiment/direction LLM candidates, "
            "including the multi-source causal-memory v2.1 transfer test"
        ),
        "research_status": "frozen-negative-development-evidence",
        "trading_authorization": False,
        "sealed_holdout_status": "not-run",
        "supersession_policy": (
            "Future event/risk or overlay experiments are a new protocol and must not mutate "
            "or reinterpret these artifacts as successful predictive evidence"
        ),
        "summary": {
            "artifact_count": len(artifacts),
            "total_size_bytes": sum(item["size_bytes"] for item in artifacts),
        },
        "artifacts": artifacts,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (destination / "MANIFEST.SHA256").write_text(
        f"{sha256(manifest_path)}  manifest.json\n", encoding="ascii"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument(
        "--external-results", type=Path,
        default=Path(__file__).resolve().parents[2] / "results",
    )
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    payload = build_snapshot(
        args.workspace.resolve(), args.external_results.resolve(), args.destination.resolve()
    )
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
