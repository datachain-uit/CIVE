"""Preflight the official FinMem implementation before running a memory agent.

This script does not call an LLM and does not run a backtest. It records whether
the official FinMem repository can be used for a thesis-valid run in the current
machine state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def run_command(args: list[str], cwd: Path) -> dict:
    try:
        completed = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=30)
        return {
            "command": args,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    except Exception as exc:
        return {"command": args, "error": f"{type(exc).__name__}: {exc}"}


def env_key_state(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        return "missing"
    lowered = value.lower()
    if "enter your" in lowered or "your " in lowered or "key here" in lowered:
        return "placeholder"
    return "present"


def read_env_placeholder(repo: Path) -> dict:
    env_path = repo / ".env"
    if not env_path.exists():
        return {"exists": False}
    text = env_path.read_text(encoding="utf-8", errors="replace")
    return {
        "exists": True,
        "sha256": sha256_file(env_path),
        "contains_openai_placeholder": "Enter your OpenAI API Key here" in text,
        "contains_hf_placeholder": "Enter your Hugging Face token here" in text,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    config_path = repo / "config" / "tsla_gpt_config.toml"
    model_inputs = sorted((repo / "data" / "03_model_input").glob("*.pkl"))
    fake_sample = repo / "data-pipeline" / "Fake-Sample-Data.zip"
    run_py = repo / "run.py"

    git_head = run_command(["git", "rev-parse", "HEAD"], repo)
    help_attempt = run_command([str(args.python), str(run_py), "--help"], repo)

    blockers: list[str] = []
    warnings: list[str] = []
    if not model_inputs:
        blockers.append("no FinMem model input .pkl found under data/03_model_input")
    if env_key_state("OPENAI_API_KEY") != "present":
        blockers.append("OPENAI_API_KEY is not present in the process environment")
    env_file = read_env_placeholder(repo)
    if env_file.get("contains_openai_placeholder"):
        blockers.append("repo .env contains the placeholder OpenAI key, not a usable credential")
    if not config_path.exists():
        blockers.append("tsla_gpt_config.toml is missing")
    if not run_py.exists():
        blockers.append("run.py is missing")
    if help_attempt.get("returncode") != 0:
        warnings.append("selected Python environment cannot import/run FinMem dependencies yet")
    if fake_sample.exists():
        warnings.append("toy Fake-Sample-Data.zip exists, but it is not a thesis-valid reproduction dataset")

    payload = {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": "llm-finmem-official-preflight-v1-development",
        "stage": "stage0-feasibility",
        "paper": {
            "id": "H02",
            "title": "FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design",
            "doi": "10.1109/TBDATA.2025.3593370",
            "role": "memory-agent transfer/reproduction preflight; not a crypto execution replication",
        },
        "source": {
            "repo_url": "https://github.com/pipiku915/finmem-llm-stocktrading",
            "local_path": str(repo),
            "git_head": (git_head.get("stdout") or "").strip() or None,
            "git_head_check": git_head,
        },
        "inputs": {
            "config": str(config_path),
            "config_exists": config_path.exists(),
            "model_input_count": len(model_inputs),
            "model_inputs": [str(path) for path in model_inputs],
            "fake_sample_zip": str(fake_sample) if fake_sample.exists() else None,
            "fake_sample_sha256": sha256_file(fake_sample) if fake_sample.exists() else None,
        },
        "credentials": {
            "OPENAI_API_KEY": env_key_state("OPENAI_API_KEY"),
            "HF_TOKEN": env_key_state("HF_TOKEN"),
            "repo_env_file": env_file,
        },
        "dependency_probe": {
            "python": str(args.python),
            "run_py_help_attempt": help_attempt,
        },
        "blockers": blockers,
        "warnings": warnings,
        "market_outcomes_consulted": False,
        "trading_backtest_consulted": False,
        "passed": not blockers,
        "status": (
            "stage0-pass-run-authorized"
            if not blockers
            else "stage0-infeasible-stop-before-finmem-run"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload["passed"] else 2)


if __name__ == "__main__":
    main()
