#!/usr/bin/env python3
"""Create immutable pre-inference metadata, then invoke the v12.5.11 executor."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXECUTOR = Path(__file__).with_name("run_federal_register_llm_dry_run_v12_5_11.py")
OUT = ROOT / "paper" / "input" / "results" / "llm" / "v12_5" / "federal_register_llm_dry_run_v12_5_11"
MODEL = "ministral-3:8b"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if os.environ.get("KLTN_ALLOW_DRY_RUN") != "YES":
        raise SystemExit("set KLTN_ALLOW_DRY_RUN=YES after reviewing this frozen runner")
    OUT.mkdir(parents=True, exist_ok=True)
    preflight = OUT / "pre_inference_execution_metadata.json"
    if preflight.exists():
        raise SystemExit("pre-inference metadata already exists; do not overwrite a frozen run")
    modelfile = subprocess.run(["ollama", "show", MODEL, "--modelfile"], check=True, capture_output=True, text=True, timeout=30).stdout
    version = subprocess.run(["ollama", "--version"], check=True, capture_output=True, text=True, timeout=20).stdout.strip()
    value = {
        "status": "FROZEN_BEFORE_INFERENCE",
        "at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model": MODEL,
        "model_modelfile_sha256": hashlib.sha256(modelfile.encode("utf-8")).hexdigest(),
        "ollama_version": version,
        "executor_v12_5_11_sha256": digest(EXECUTOR),
        "launcher_v12_5_12_sha256": digest(Path(__file__)),
        "corpus_declared_sha256": "a0ab4923badb52665b9deaae077e578b42e9ef1490b88422079183bbed8fab53",
        "market_data_read_by_launcher": False,
        "target_materialized_by_launcher": False
    }
    preflight.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return subprocess.run([sys.executable, str(EXECUTOR)], env=os.environ.copy()).returncode


if __name__ == "__main__":
    raise SystemExit(main())
