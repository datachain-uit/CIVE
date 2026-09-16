#!/usr/bin/env python3
"""Reproduce every quantitative result reported in the conference paper.

The runner never writes into frozen evidence. Model-inference outputs whose
weights are not distributed are integrity-checked and semantically audited;
all downstream statistical, technical, and hybrid evaluations are rerun.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from materialize_portable_config import rewrite_paths


ROOT = Path(__file__).resolve().parents[2]
LLM_TOOLS = ROOT / "tools" / "llm"
FROZEN_LLM_TOOLS = ROOT / "frozen_tools" / "llm"
DEFAULT_OUTPUT = ROOT / "runtime" / "reproduction" / "reported_results"
IGNORED_COMPARISON_KEYS = {
    "created_at",
    "evaluated_at",
    "generated_at",
    "output",
    "path",
    "sha256",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_config(source: Path, destination: Path) -> Path:
    payload = rewrite_paths(read_json(source))
    write_json(destination, payload)
    return destination


def run_command(name: str, command: list[str], output_dir: Path) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    log = output_dir / "logs" / f"{name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "$ " + " ".join(command) + "\n\nSTDOUT\n" + completed.stdout
        + "\nSTDERR\n" + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{name} exited with {completed.returncode}; see {log}")


def compare_json(generated_path: Path, frozen_path: Path) -> None:
    differences: list[str] = []

    def compare(left: Any, right: Any, location: str) -> None:
        if len(differences) >= 20:
            return
        if isinstance(left, dict) and isinstance(right, dict):
            left_keys = set(left) - IGNORED_COMPARISON_KEYS
            right_keys = set(right) - IGNORED_COMPARISON_KEYS
            if left_keys != right_keys:
                differences.append(
                    f"{location}: keys differ: generated-only={sorted(left_keys-right_keys)}, "
                    f"frozen-only={sorted(right_keys-left_keys)}"
                )
                return
            for key in sorted(left_keys):
                compare(left[key], right[key], f"{location}.{key}")
            return
        if isinstance(left, list) and isinstance(right, list):
            if len(left) != len(right):
                differences.append(f"{location}: list length {len(left)} != {len(right)}")
                return
            for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
                compare(left_item, right_item, f"{location}[{index}]")
            return
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if not math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=1e-12):
                differences.append(f"{location}: {left!r} != {right!r}")
            return
        if left != right:
            differences.append(f"{location}: {left!r} != {right!r}")

    compare(read_json(generated_path), read_json(frozen_path), "root")
    if differences:
        raise AssertionError("JSON reproduction differs:\n" + "\n".join(differences))


def run_tech_case(label: str, frozen_stem: str, output_dir: Path) -> None:
    manifest_path = ROOT / "results" / f"{frozen_stem}.manifest.json"
    frozen_path = ROOT / "results" / f"{frozen_stem}.json"
    configuration = read_json(manifest_path)["configuration"]
    generated = output_dir / f"{label}.json"
    generated_manifest = output_dir / f"{label}.manifest.json"
    command = [sys.executable, str(ROOT / "executor" / "technical_bybit_lifecycle_execution.py")]
    option_names = {
        "manifest": "--manifest",
        "daily_cache_dir": "--daily-cache-dir",
        "four_h_cache_dir": "--four-h-cache-dir",
        "funding_cache_dir": "--funding-cache-dir",
        "workers": "--workers",
        "top_n": "--top-n",
        "rank_days": "--rank-days",
        "balance": "--balance",
        "gross_leverage": "--gross-leverage",
        "fee_bps": "--fee-bps",
        "slippage_bps": "--slippage-bps",
        "spread_bps": "--spread-bps",
        "impact_bps": "--impact-bps",
        "stop_atr": "--stop-atr",
        "trail_atr": "--trail-atr",
        "fold_days": "--fold-days",
    }
    for key, option in option_names.items():
        value = configuration[key]
        if key.endswith("_dir") or key == "manifest":
            value = ROOT / Path(str(value).replace("\\", "/"))
        command.extend((option, str(value)))
    command.extend(("--output", str(generated), "--experiment-manifest", str(generated_manifest)))
    run_command(label, command, output_dir)
    compare_json(generated, frozen_path)


def run_llm_cases(output_dir: Path) -> None:
    cases = [
        {
            "name": "llm_v17_eth_return",
            "config": "paper/input/results/llm/v17/llm_only_eth_transfer_v17_predeclared.json",
            "panel": "paper/input/results/llm/v17/llm_only_eth_transfer_target_panel_v17.json",
            "script": "evaluate_llm_only_eth_transfer_v17.py",
            "prediction": "llm_v17_predictions.json",
            "result": "llm_v17_result.json",
            "frozen_prediction": "paper/input/results/llm/v17/llm_only_eth_transfer_prediction_panel_v17.json",
            "frozen_result": "paper/input/results/llm/v17/llm_only_eth_transfer_gate_v17.json",
            "panel_option": "--target-panel",
        },
        {
            "name": "llm_v18_btc_return",
            "config": "paper/input/results/llm/v18/llm_only_multicoin_evaluation_v18_predeclared.json",
            "panel": "paper/input/results/llm/v18/llm_only_multicoin_target_panel_v18.json",
            "script": "evaluate_llm_only_multicoin_transfer_v18.py",
            "prediction": "llm_v18_predictions.json",
            "result": "llm_v18_result.json",
            "frozen_prediction": "paper/input/results/llm/v18/llm_only_multicoin_prediction_panel_v18.json",
            "frozen_result": "paper/input/results/llm/v18/llm_only_multicoin_family_gate_v18.json",
            "panel_option": "--target-panel",
            "linked_panel": True,
        },
        {
            "name": "llm_v19_eth_risk",
            "config": "paper/input/results/llm/v19/llm_only_multicoin_risk_evaluation_v19_predeclared.json",
            "panel": "paper/input/results/llm/v19/llm_only_multicoin_risk_panel_v19.json",
            "script": "evaluate_multicoin_risk_transfer_v19.py",
            "prediction": "llm_v19_predictions.json",
            "result": "llm_v19_result.json",
            "frozen_prediction": "paper/input/results/llm/v19/llm_only_multicoin_risk_predictions_v19.json",
            "frozen_result": "paper/input/results/llm/v19/llm_only_multicoin_risk_gate_v19.json",
            "panel_option": "--panel",
        },
        {
            "name": "llm_v20_eth_sol_response",
            "config": "paper/input/results/llm/v20/llm_only_multicoin_short_evaluation_v20_predeclared.json",
            "panel": "paper/input/results/llm/v20/llm_only_multicoin_short_panel_v20.json",
            "script": "evaluate_multicoin_short_transfer_v20.py",
            "prediction": "llm_v20_predictions.json",
            "result": "llm_v20_result.json",
            "frozen_prediction": "paper/input/results/llm/v20/llm_only_multicoin_short_predictions_v20.json",
            "frozen_result": "paper/input/results/llm/v20/llm_only_multicoin_short_gate_v20.json",
            "panel_option": "--panel",
        },
    ]
    for case in cases:
        source_config = ROOT / case["config"]
        config = portable_config(source_config, output_dir / f"{case['name']}_config.json")
        panel = ROOT / case["panel"]
        if case.get("linked_panel"):
            linked = read_json(panel)
            original_hash = sha256(source_config)
            if linked["predeclaration"]["sha256"] != original_hash:
                raise RuntimeError("v18 target panel does not reference its frozen predeclaration")
            linked["predeclaration"]["sha256"] = sha256(config)
            panel = output_dir / "llm_v18_target_portable.json"
            write_json(panel, linked)
        prediction = output_dir / case["prediction"]
        result = output_dir / case["result"]
        command = [
            sys.executable,
            str(LLM_TOOLS / case["script"]),
            "--config",
            str(config),
            case["panel_option"],
            str(panel),
            "--prediction-panel" if case["panel_option"] == "--target-panel" else "--predictions",
            str(prediction),
            "--output",
            str(result),
        ]
        run_command(case["name"], command, output_dir)
        compare_json(prediction, ROOT / case["frozen_prediction"])
        compare_json(result, ROOT / case["frozen_result"])


def run_hybrid_command_cases(output_dir: Path) -> None:
    portable_hyb001 = portable_config(
        ROOT / "paper/input/results/hybrid/tech_llm_conditional_overlay_v1_predeclared.json",
        output_dir / "hyb001_config.json",
    )
    hyb001 = output_dir / "hyb001_result.json"
    run_command(
        "hyb001",
        [sys.executable, str(LLM_TOOLS / "run_tech_llm_conditional_overlay_v1.py"), "evaluate", "--predeclared", str(portable_hyb001), "--output", str(hyb001)],
        output_dir,
    )
    compare_json(hyb001, ROOT / "paper/input/results/hybrid/tech_llm_conditional_overlay_v1_development.json")

    hyb002_source = ROOT / "paper/input/results/hybrid/tech_llm_intratrade_shock_shield_v2_predeclared.json"
    hyb002_payload = read_json(hyb002_source)
    # The pre-evaluation runner recorded by HYB-002 was later replaced and is
    # not distributed. The committed independent replay audit is distributed,
    # so rebind only the runner attestation in the derived runtime copy while
    # retaining and checking every frozen assignment and data input.
    hyb002_payload["inputs"].pop("runner")
    hyb002_payload = rewrite_paths(hyb002_payload)
    audit_runner = LLM_TOOLS / "audit_tech_llm_intratrade_shock_shield_v2_replay.py"
    hyb002_payload["inputs"]["runner"] = {
        "path": str(audit_runner),
        "sha256": sha256(audit_runner),
    }
    portable_hyb002 = output_dir / "hyb002_config.json"
    write_json(portable_hyb002, hyb002_payload)
    hyb002 = output_dir / "hyb002_replay_audit.json"
    run_command(
        "hyb002",
        [
            sys.executable,
            str(audit_runner),
            "--predeclared",
            str(portable_hyb002),
            "--canonical-result",
            str(ROOT / "paper/input/results/hybrid/tech_llm_intratrade_shock_shield_v2_development.json"),
            "--output",
            str(hyb002),
        ],
        output_dir,
    )
    compare_json(hyb002, ROOT / "paper/input/results/hybrid/tech_llm_intratrade_shock_shield_v2_replay_audit.json")

    hyb003 = output_dir / "hyb003_result.json"
    run_command(
        "hyb003",
        [sys.executable, str(LLM_TOOLS / "evaluate_hyb003_stage_d_v3_2.py"), "--output", str(hyb003)],
        output_dir,
    )
    compare_json(hyb003, ROOT / "paper/input/results/hybrid/hyb003_stage_d_remediation_v3_2.json")

    for number in (9, 10):
        stem = "hyb009_model_substitution_v1_1" if number == 9 else "hyb010_risk_budget_reallocation"
        script = "evaluate_hyb009_model_substitution_v1_1.py" if number == 9 else "evaluate_hyb010_risk_budget_reallocation.py"
        config = portable_config(
            ROOT / f"paper/input/results/hybrid/{stem}_predeclared.json",
            output_dir / f"hyb{number:03d}_config.json",
        )
        result = output_dir / f"hyb{number:03d}_result.json"
        run_command(
            f"hyb{number:03d}",
            [sys.executable, str(LLM_TOOLS / script), "--config", str(config), "--output", str(result)],
            output_dir,
        )
        compare_json(result, ROOT / f"paper/input/results/hybrid/{stem}_evaluation.json")


@contextlib.contextmanager
def llm_import_path():
    values = [str(FROZEN_LLM_TOOLS), str(LLM_TOOLS)]
    for value in reversed(values):
        sys.path.insert(0, value)
    try:
        yield
    finally:
        for value in values:
            sys.path.remove(value)


def run_redirected_module(
    module_name: str,
    writer_name: str,
    output_dir: Path,
    portable_predeclaration: str | None = None,
) -> None:
    with llm_import_path():
        frozen_module = FROZEN_LLM_TOOLS / f"{module_name}.py"
        if frozen_module.is_file():
            spec = importlib.util.spec_from_file_location(f"reproduction_{module_name}", frozen_module)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load frozen evaluator: {frozen_module}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        else:
            module = importlib.import_module(module_name)
        original_writer = getattr(module, writer_name)

        def redirected_writer(path: Path, payload: Any) -> None:
            original_writer(output_dir / Path(path).name, payload)

        setattr(module, writer_name, redirected_writer)
        if portable_predeclaration:
            pre_path = (ROOT / portable_predeclaration).resolve()
            portable_payload = read_json(pre_path)
            scripts = portable_payload.get("inputs", {}).pop("scripts", None)
            portable_payload = rewrite_paths(portable_payload)
            if scripts is not None:
                portable_scripts = []
                for item in scripts:
                    name = Path(item["path"]).name
                    candidate = FROZEN_LLM_TOOLS / name
                    if not candidate.is_file():
                        candidate = LLM_TOOLS / name
                    if sha256(candidate) != item["sha256"]:
                        raise ValueError(f"no distributed script matches frozen hash: {name}")
                    portable_scripts.append({**item, "path": str(candidate)})
                portable_payload["inputs"]["scripts"] = portable_scripts
            read_name = "read_json" if hasattr(module, "read_json") else "read"
            original_reader = getattr(module, read_name)

            def redirected_reader(path: Path) -> Any:
                return portable_payload if Path(path).resolve() == pre_path else original_reader(path)

            setattr(module, read_name, redirected_reader)
        module.main()


def run_hybrid_redirected_cases(output_dir: Path) -> None:
    cases = [
        (
            "evaluate_hyb006_rank_pair_reallocation",
            "write_json",
            "paper/input/results/hybrid/hyb006_rank_pair_reallocation_predeclared.json",
            ("hyb006_rank_pair_reallocation_daily_panel.json", "hyb006_rank_pair_reallocation_evaluation.json"),
        ),
        (
            "evaluate_hyb007_historical_risk_attenuation",
            "write",
            None,
            ("hyb007_historical_risk_attenuation_cluster_panel.json", "hyb007_historical_risk_attenuation_evaluation.json"),
        ),
        (
            "evaluate_hyb008_conditional_downside",
            "write",
            "paper/input/results/hybrid/hyb008_conditional_downside_predeclared.json",
            ("hyb008_conditional_downside_predictions.json", "hyb008_conditional_downside_evaluation.json"),
        ),
    ]
    for module_name, writer, predeclaration, outputs in cases:
        run_redirected_module(module_name, writer, output_dir, predeclaration)
        for filename in outputs:
            compare_json(
                output_dir / filename,
                ROOT / "paper/input/results/hybrid" / filename,
            )


def verify_frozen_inference_and_stops() -> dict[str, Any]:
    extraction_path = ROOT / "paper/input/results/llm/v3/llm_event_extractor_v3_9_full_development.json"
    extraction = read_json(extraction_path)
    records = extraction["records"]
    extraction_ok = (
        len(records) == 39_393
        and all(row.get("status") == "success" and row.get("error") is None for row in records)
        and sha256(extraction_path) == "e084343db1b70e31b1c11988c007b4c8b089940720db97bdef05ec3d9484707b"
    )
    if not extraction_ok:
        raise AssertionError("frozen 39,393-record extraction failed integrity/semantic checks")

    screens = {
        ROOT / "paper/input/results/llm/v18/llm_only_multicoin_screen_v18.json": {"XRPUSDT", "SOLUSDT", "BNBUSDT"},
        ROOT / "paper/input/results/llm/v19/llm_only_multicoin_risk_screen_v19.json": {"SOLUSDT", "XRPUSDT", "BNBUSDT"},
        ROOT / "paper/input/results/llm/v20/llm_only_multicoin_short_screen_v20.json": {"XRPUSDT", "BNBUSDT"},
    }
    operational_artifacts = {
        ROOT / "paper/input/results/llm/v21/llm_event_extractor_glm4_9b_v21_stage1_predeclared.json": "811ceeb29d7fe53294b9c8f491cd1dbf1b87c329855275550ba0f35e646ab61a",
        ROOT / "paper/input/results/llm/v21/llm_event_extractor_glm4_9b_v21_stage1_run1.json": "bd788793a96296dd43552314f06ffb045e0dc209b07d31dfff38690fc3475d91",
        ROOT / "paper/input/results/llm/v21/llm_event_extractor_glm4_9b_v21_stage1_gate.json": "f579dd14b335f4fe0919b4650f9022ca40510644a6a4c05cc99ccd21f4638d31",
        ROOT / "configs/llm_glm4_9b_challenger_v1_development.json": "ea440ebb74de4a5db864e7e51c79244876fbf91ea3e23063e84275bf1ff69f25",
        ROOT / "results/llm_daily_reliability_glm4_9b_q3km_run1_v1.json": "bf2ef9c0dd76090ed0ed14b06bf22161c350f68dbd12da9d19dc98411a079b25",
        ROOT / "results/llm_glm4_9b_q3km_challenger_gate_v1.json": "34da04f1e8b2d08d6e2a7afc1ef17bb7a82962d8c0f79bce902a9191beb999d6",
    }
    stop_files = [*screens, *operational_artifacts]
    missing = [str(path.relative_to(ROOT)) for path in stop_files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing reported stop artifacts: {missing}")
    for path, expected_assets in screens.items():
        actual_assets = set(read_json(path)["stopped_assets"])
        if actual_assets != expected_assets:
            raise AssertionError(f"reported stopped assets changed in {path}: {sorted(actual_assets)}")
    for path, expected_hash in operational_artifacts.items():
        if sha256(path) != expected_hash:
            raise AssertionError(f"reported operational artifact hash changed: {path}")
    return {
        "mode": "frozen_model_output_and_stop_artifact_verification",
        "extraction_records": len(records),
        "extraction_sha256": sha256(extraction_path),
        "reported_stop_artifacts": len(stop_files),
        "note": "Full LLM inference requires separately obtained model weights; downstream reported evaluations are replayed by this runner.",
    }


def verify_daily_close_metric() -> dict[str, float]:
    artifact = read_json(ROOT / "results/technical_bybit_lifecycle_1x_candidate_hardened.json")
    value = float(artifact["result"]["starting_balance"])
    peak = value
    maximum_drawdown = 0.0
    for _, daily_return in artifact["daily_returns"]:
        value *= 1.0 + float(daily_return)
        peak = max(peak, value)
        maximum_drawdown = max(maximum_drawdown, 1.0 - value / peak)
    if not math.isclose(value, float(artifact["result"]["final_equity"]), abs_tol=0.01):
        raise AssertionError("daily-close equity path does not reconcile to final equity")
    if len(artifact["daily_returns"]) != 1459 or not math.isclose(maximum_drawdown, 0.0878045, abs_tol=5e-7):
        raise AssertionError("daily-close point count or drawdown differs from the paper")
    return {"daily_points": 1459, "final_equity": value, "daily_close_max_drawdown": maximum_drawdown}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-tech-backtests", action="store_true", help="Development-only shortcut; a complete reproduction must omit this flag.")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir == ROOT or ROOT not in output_dir.parents:
        raise SystemExit("output directory must be a child of the artifact root")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    cases: list[tuple[str, Callable[[], Any], str]] = [
        ("frozen_inference_and_stops", verify_frozen_inference_and_stops, "verified_frozen_model_output"),
        ("tech_daily_close_metric", verify_daily_close_metric, "replayed"),
        ("llm_only_v17_v20", lambda: run_llm_cases(output_dir), "replayed"),
        ("hyb001_003_009_010", lambda: run_hybrid_command_cases(output_dir), "replayed"),
        ("hyb006_008", lambda: run_hybrid_redirected_cases(output_dir), "replayed"),
    ]
    if not args.skip_tech_backtests:
        tech_cases = (
            ("tech_base", "technical_bybit_lifecycle_1x_candidate_hardened"),
            ("tech_stress", "technical_bybit_lifecycle_1x_candidate_hardened_stress"),
            ("tech_harsh", "technical_bybit_lifecycle_1x_candidate_hardened_harsh"),
        )
        for label, stem in tech_cases:
            cases.insert(1, (label, lambda label=label, stem=stem: run_tech_case(label, stem, output_dir), "replayed"))

    report = {"schema_version": 1, "passed": True, "complete": not args.skip_tech_backtests, "cases": []}
    for name, action, mode in cases:
        entry = {"name": name, "mode": mode, "passed": False}
        try:
            details = action()
            entry["passed"] = True
            if details is not None:
                entry["details"] = details
        except Exception as exc:  # keep the full audit report instead of stopping at the first failure
            entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["traceback"] = traceback.format_exc()
            report["passed"] = False
        report["cases"].append(entry)
        print(f"{'PASS' if entry['passed'] else 'FAIL'} {name}")

    report_path = output_dir / "reproduction_report.json"
    write_json(report_path, report)
    print(json.dumps({"passed": report["passed"], "complete": report["complete"], "report": str(report_path)}, indent=2))
    return 0 if report["passed"] and report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
