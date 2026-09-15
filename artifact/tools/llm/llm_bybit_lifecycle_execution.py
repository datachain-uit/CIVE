"""Run LLM-only targets through the frozen Bybit lifecycle execution engine."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import technical_bybit_lifecycle_execution as lifecycle_engine
from llm_lifecycle_adapter import build_targets
from technical_bybit_lifecycle_universe import _atomic_json
from technical_execution_semantics import EVENT_ORDER, EXECUTION_SEMANTICS
from technical_experiment_manifest import build_experiment_manifest, write_manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM-only BTC long/flat on the common lifecycle engine",
        add_help=False,
    )
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--lifecycle-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiment-manifest", type=Path)
    parser.add_argument("--long-threshold", type=float, default=0.30)
    parser.add_argument("--minimum-confidence", type=float, default=0.70)
    parser.add_argument("--decision-delay-hours", type=int, default=4)
    args, engine_args = parser.parse_known_args()

    scored = json.loads(args.scores.read_text(encoding="utf-8"))
    lifecycle = json.loads(args.lifecycle_manifest.read_text(encoding="utf-8"))
    adapter = build_targets(
        scored, lifecycle, args.long_threshold, args.minimum_confidence,
        args.decision_delay_hours,
    )
    target_schedule = {
        int(timestamp): set(symbols) for timestamp, symbols in adapter["targets"].items()
    }

    def injected_targets(_manifest, _daily, _top_n, _rank_days, _excluded_symbols=None):
        return target_schedule

    lifecycle_engine._targets = injected_targets
    manifest_path = args.experiment_manifest or args.output.with_suffix(".manifest.json")
    original_argv = sys.argv
    sys.argv = [str(Path(lifecycle_engine.__file__))] + engine_args + [
        "--manifest", str(args.lifecycle_manifest),
        "--output", str(args.output),
        "--experiment-manifest", str(manifest_path),
        "--top-n", "1",
        "--rank-days", "1",
    ]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            lifecycle_engine.main()
    finally:
        sys.argv = original_argv

    engine_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = json.loads(args.output.read_text(encoding="utf-8"))
    result["protocol"].pop("top_n", None)
    result["protocol"].pop("rank_days", None)
    result["protocol"].update({
        "strategy": adapter["strategy"],
        "signal_source": "causal completed-day LLM information sets",
        "signal_instrument": "BTCUSDT",
        "long_threshold": args.long_threshold,
        "minimum_confidence": args.minimum_confidence,
        "decision_delay_hours": args.decision_delay_hours,
        "missing_or_error": "explicit flat target",
        "technical_entry_filter": False,
        "score_model": adapter.get("model"),
        "score_model_digest": adapter.get("model_digest"),
        "prompt_version": adapter.get("prompt_version"),
        "adapter_summary": adapter["summary"],
        "research_status": "development-not-frozen",
    })
    _atomic_json(args.output, result)

    data_paths = [Path(item["path"]) for item in engine_manifest.get("data", [])]
    data_paths.extend([args.scores.resolve(), args.lifecycle_manifest.resolve()])
    data_paths = list(dict.fromkeys(path for path in data_paths if path.exists()))
    source_paths = [Path(item["path"]) for item in engine_manifest.get("sources", [])]
    source_paths.extend([Path(__file__), Path(build_targets.__code__.co_filename)])
    source_paths = list(dict.fromkeys(path.resolve() for path in source_paths if path.exists()))
    configuration = {
        "scores": str(args.scores),
        "lifecycle_manifest": str(args.lifecycle_manifest),
        "long_threshold": args.long_threshold,
        "minimum_confidence": args.minimum_confidence,
        "decision_delay_hours": args.decision_delay_hours,
        "engine_arguments": engine_args,
    }
    write_manifest(manifest_path, build_experiment_manifest(
        repo_root=Path(__file__).resolve().parents[2],
        result_path=args.output,
        configuration=configuration,
        data_paths=data_paths,
        source_paths=source_paths,
        execution_semantics=EXECUTION_SEMANTICS,
        event_order=EVENT_ORDER,
    ))
    print(json.dumps({
        "result": result["result"],
        "adapter_summary": adapter["summary"],
        "output": str(args.output),
        "experiment_manifest": str(manifest_path),
    }, indent=2))


if __name__ == "__main__":
    main()
