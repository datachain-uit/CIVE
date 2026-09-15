"""Build and validate immutable research freeze artifacts."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from technical_experiment_manifest import sha256_file, write_manifest

def canonical_hash(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()

def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("UTC timestamp must include timezone")
    return parsed.astimezone(timezone.utc)

def validate_holdout(holdout: dict, development_end_ms: int) -> None:
    start, end = parse_utc(holdout["start_utc"]), parse_utc(holdout["end_utc_exclusive"])
    development_end = datetime.fromtimestamp(development_end_ms / 1000, timezone.utc)
    if start <= development_end:
        raise ValueError("sealed holdout overlaps inspected development data")
    if (start - development_end).days < int(holdout["embargo_days"]):
        raise ValueError("sealed holdout violates declared embargo")
    if (end - start).days < int(holdout["minimum_calendar_days"]):
        raise ValueError("sealed holdout is shorter than declared minimum")
    if holdout["open_policy"]["allow_interim_performance_read"]:
        raise ValueError("sealed protocol cannot allow interim performance reads")

def build_freeze(root: Path) -> dict:
    config_paths = [root / "configs" / name for name in (
        "technical_control_v1.json", "controlled_experiment_v1.json", "sealed_forward_holdout_v1.json"
    )]
    configs = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in config_paths}
    universe = json.loads((root / "results" / "bybit_lifecycle_universe.json").read_text(encoding="utf-8"))
    validate_holdout(configs["sealed_forward_holdout_v1"], int(universe["protocol"]["end_ms"]))
    evidence_paths = [root / "results" / name for name in (
        "technical_bybit_lifecycle_1x_candidate_hardened.json",
        "technical_bybit_lifecycle_1x_candidate_hardened.manifest.json",
        "technical_lifecycle_robustness_report_v2.json",
        "technical_lifecycle_concentration_regime_v2.json",
        "technical_selection_inference_v2.json",
    )]
    source_paths = [root / "executor" / name for name in (
        "technical_bybit_lifecycle_execution.py", "technical_execution_semantics.py",
        "controlled_arm_contract.py", "freeze_experiment.py",
    )]
    return {
        "schema_version": 1, "freeze_id": "tech-control-v1-freeze",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "Tech frozen; three-arm collection blocked until LLM and Hybrid freezes exist",
        "configuration_hashes": {p.name: canonical_hash(p) for p in config_paths},
        "configuration_files": {p.name: sha256_file(p) for p in config_paths},
        "evidence_files": {str(p.resolve()): sha256_file(p) for p in evidence_paths},
        "source_files": {str(p.resolve()): sha256_file(p) for p in source_paths},
        "holdout": configs["sealed_forward_holdout_v1"],
        "unresolved_requirements": ["llm-pipeline-v1 freeze", "hybrid-overlay-v1 freeze"],
    }

def verify_freeze(payload: dict) -> None:
    root = Path(__file__).resolve().parents[1]
    for group in ("configuration_files", "evidence_files", "source_files"):
        for name, expected in payload[group].items():
            path = root / "configs" / name if group == "configuration_files" else Path(name)
            if not path.is_file() or sha256_file(path) != expected:
                raise ValueError(f"freeze integrity violation in {group}: {path}")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("results/tech_control_v1_freeze.json"))
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / args.output
    if args.verify:
        payload = json.loads(output.read_text(encoding="utf-8"))
        verify_freeze(payload)
    else:
        payload = build_freeze(root)
        write_manifest(output, payload)
    print(json.dumps(payload, indent=2))

if __name__ == "__main__":
    main()
