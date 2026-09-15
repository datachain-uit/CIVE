"""Build a thesis-facing status table for LLM candidates.

The production results directory contains pilots, smoke tests, manifests, and
full ledgers. This script intentionally whitelists the research candidates that
entered the current evidence protocol and summarizes only their decision status.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def fmt_float(value: Any, digits: int = 4) -> str | None:
    if value is None:
        return None
    return f"{float(value):.{digits}f}"


def fmt_bps(value: Any) -> str | None:
    if value is None:
        return None
    return f"{float(value):.2f} bps"


def ci_text(values: list[Any] | None, *, bps: bool = False) -> str | None:
    if not values or len(values) != 2:
        return None
    if bps:
        return f"[{float(values[0]):.2f}, {float(values[1]):.2f}] bps"
    return f"[{float(values[0]):.4f}, {float(values[1]):.4f}]"


def rel(path: Path) -> str:
    return str(path)


def row(
    *,
    candidate: str,
    family: str,
    final_stage: str,
    status: str,
    allowed_backtest: bool,
    stop_reason: str,
    stage0: str = "n/a",
    stage1: str = "n/a",
    full_inference: str = "n/a",
    predictive_gate: str = "n/a",
    key_metrics: str = "",
    artifacts: list[Path] | None = None,
) -> dict[str, Any]:
    artifact_rows = []
    for path in artifacts or []:
        artifact_rows.append({"path": rel(path), "sha256": sha256_file(path)})
    return {
        "candidate": candidate,
        "family": family,
        "stage0": stage0,
        "stage1_reliability": stage1,
        "full_inference": full_inference,
        "predictive_gate": predictive_gate,
        "final_stage": final_stage,
        "status": status,
        "allowed_for_backtest": allowed_backtest,
        "key_metrics": key_metrics,
        "stop_reason": stop_reason,
        "artifacts": artifact_rows,
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    prod = args.production_results
    ktln = args.ktln_llm_results

    finbert_stage1_path = prod / "llm_finbert_operational_gate_v1.json"
    finbert_stage2_path = prod / "llm_finbert_predictive_gate_v1_development.json"
    finbert_stage2 = load(finbert_stage2_path)
    finbert_uncertainty = finbert_stage2["uncertainty"]

    crypto_full_path = ktln / "llm_cryptobert_full_v1_development.json"
    crypto_stage2_path = ktln / "llm_cryptobert_predictive_gate_v1_development.json"
    crypto_full = load(crypto_full_path)
    crypto_stage2 = load(crypto_stage2_path)
    crypto_uncertainty = crypto_stage2["uncertainty"]

    llama_single_path = prod / "llm_bybit_lifecycle_full_v1_development.json"
    llama_consensus_path = prod / "llm_bybit_lifecycle_dual_run_consensus_v1_development.json"
    llama_calibration_path = prod / "llm_outcome_calibration_dual_run_consensus_v1_development.json"
    llama_single = load(llama_single_path)
    llama_consensus = load(llama_consensus_path)
    llama_calibration = load(llama_calibration_path)

    qwen_stage1_path = prod / "llm_qwen25_7b_challenger_gate_v1.json"
    qwen_stage2_path = prod / "llm_qwen25_7b_challenger_stage2_v1.json"
    qwen_stage2 = load(qwen_stage2_path)

    gemma_stage1_path = prod / "llm_gemma3_4b_challenger_gate_v1.json"
    gemma_stage1 = load(gemma_stage1_path)
    gemma_partial = gemma_stage1["stage1_partial_run"]

    fingpt_stage0_path = ktln / "llm_fingpt_chatglm2_6b_bnb_nf4_stage0_v2_development.json"
    fingpt_stage1_path = ktln / "llm_fingpt_chatglm2_6b_bnb_nf4_stage1_reliability_v2_development.json"
    fingpt_stage1 = load(fingpt_stage1_path)
    fingpt_checks = fingpt_stage1["checks"]

    finmem_path = ktln / "llm_finmem_official_preflight_v1_development.json"
    finmem = load(finmem_path)

    rows = [
        row(
            candidate="FinBERT / ProsusAI",
            family="financial sentiment classifier",
            stage1="pass",
            full_inference="pass",
            predictive_gate="fail",
            final_stage="predictive gate",
            status=finbert_stage2["status"],
            allowed_backtest=False,
            key_metrics=(
                f"n={finbert_stage2['observations']}; Pearson={fmt_float(finbert_stage2['pearson_score_forward_return'])}; "
                f"Pearson CI={ci_text(finbert_uncertainty['pearson_score_forward_return_95_ci'])}; "
                f"tercile={fmt_bps(finbert_stage2['top_minus_bottom_tercile_mean_bps'])}; "
                f"tercile CI={ci_text(finbert_uncertainty['top_minus_bottom_tercile_mean_bps_95_ci'], bps=True)}"
            ),
            stop_reason="predictive confidence interval crosses zero",
            artifacts=[finbert_stage1_path, finbert_stage2_path],
        ),
        row(
            candidate="CryptoBERT / ElKulako",
            family="crypto sentiment classifier",
            stage0="pass",
            stage1="pass",
            full_inference="pass",
            predictive_gate="fail",
            final_stage="predictive gate",
            status=crypto_stage2["status"],
            allowed_backtest=False,
            key_metrics=(
                f"full={crypto_full['summary']['success']}/{crypto_full['summary']['information_sets']}; "
                f"n={crypto_stage2['observations']}; Pearson={fmt_float(crypto_stage2['pearson_score_forward_return'])}; "
                f"Pearson CI={ci_text(crypto_uncertainty['pearson_score_forward_return_95_ci'])}; "
                f"tercile={fmt_bps(crypto_stage2['top_minus_bottom_tercile_mean_bps'])}; "
                f"tercile CI={ci_text(crypto_uncertainty['top_minus_bottom_tercile_mean_bps_95_ci'], bps=True)}"
            ),
            stop_reason="predictive confidence interval crosses zero",
            artifacts=[crypto_full_path, crypto_stage2_path],
        ),
        row(
            candidate="Llama 3 dual-run consensus",
            family="local LLM daily action consensus",
            stage1="pass",
            full_inference="pass",
            predictive_gate="fail",
            final_stage="calibration / diagnostic backtest",
            status=llama_calibration["status"],
            allowed_backtest=False,
            key_metrics=(
                f"diagnostic return={llama_consensus['result']['return_pct']:.2f}%; "
                f"MDD={llama_consensus['result']['max_drawdown_pct']:.2f}%; "
                f"long-flat={llama_calibration['overall']['long_minus_flat_mean_bps']:.2f} bps; "
                f"long-flat CI={ci_text(llama_calibration['uncertainty']['long_minus_flat_mean_bps_95_ci'], bps=True)}"
            ),
            stop_reason="calibration confidence interval crosses zero; diagnostic backtest is not freeze evidence",
            artifacts=[llama_consensus_path, llama_calibration_path],
        ),
        row(
            candidate="Llama 3 single run",
            family="local LLM daily action",
            stage1="partial/pass before consensus",
            full_inference="pass",
            predictive_gate="superseded by consensus calibration",
            final_stage="diagnostic backtest",
            status=llama_single.get("protocol", {}).get("research_status", "development-not-frozen"),
            allowed_backtest=False,
            key_metrics=(
                f"diagnostic return={llama_single['result']['return_pct']:.2f}%; "
                f"MDD={llama_single['result']['max_drawdown_pct']:.2f}%; fills={llama_single['result']['fills']}"
            ),
            stop_reason="single stochastic run is superseded by dual-run consensus and calibration gate",
            artifacts=[llama_single_path],
        ),
        row(
            candidate="Qwen 2.5 7B",
            family="local LLM challenger",
            stage1="pass",
            full_inference="pass",
            predictive_gate="fail",
            final_stage="stage2 calibration",
            status=qwen_stage2["status"],
            allowed_backtest=False,
            key_metrics=(
                f"full={qwen_stage2['checks']['full_records']['observed']}; "
                f"schema errors={qwen_stage2['checks']['schema_errors']['observed']}; "
                f"Pearson CI lower={qwen_stage2['checks']['pearson_ci_lower_bound']['observed']:.4f}; "
                f"long-flat CI lower={qwen_stage2['checks']['long_minus_flat_ci_lower_bound']['observed']:.2f} bps"
            ),
            stop_reason="stage2 predictive lower bounds are negative",
            artifacts=[qwen_stage1_path, qwen_stage2_path],
        ),
        row(
            candidate="Gemma 3 4B",
            family="local LLM challenger",
            stage1="fail-fast",
            final_stage="stage1 reliability",
            status=gemma_stage1["status"],
            allowed_backtest=False,
            key_metrics=(
                f"observed={gemma_partial['observed_information_sets']}/{gemma_partial['expected_information_sets']}; "
                f"schema success={gemma_partial['schema_success']}; errors={gemma_partial['schema_errors']}; "
                f"max possible success={gemma_partial['maximum_possible_schema_success_if_completed']}"
            ),
            stop_reason="cannot reach required 108/108 schema success after early parse errors",
            artifacts=[gemma_stage1_path],
        ),
        row(
            candidate="FinGPT ChatGLM2 6B LoRA bnb-nf4",
            family="financial instruction LLM",
            stage0="pass",
            stage1="fail",
            final_stage="stage1 reliability",
            status=fingpt_stage1["status"],
            allowed_backtest=False,
            key_metrics=(
                f"information sets={fingpt_checks['information_sets']['observed']}; "
                f"schema success each run={fingpt_checks['schema_success_each_run']['observed']}; "
                f"headline matches each run={fingpt_checks['headline_count_matches_each_run']['observed']}"
            ),
            stop_reason="operational reliability gate failed before full inference",
            artifacts=[fingpt_stage0_path, fingpt_stage1_path],
        ),
        row(
            candidate="FinMem official implementation",
            family="memory agent framework",
            stage0="infeasible",
            final_stage="stage0 preflight",
            status=finmem["status"],
            allowed_backtest=False,
            key_metrics=(
                f"repo={finmem['source']['git_head']}; model input .pkl count={finmem['inputs']['model_input_count']}; "
                f"OPENAI_API_KEY={finmem['credentials']['OPENAI_API_KEY']}"
            ),
            stop_reason="; ".join(finmem["blockers"]),
            artifacts=[finmem_path],
        ),
    ]

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": "llm-candidate-status-summary-v1-development",
        "scope": "research candidates only; excludes smoke tests, raw ledgers not tied to current gates, and manifests",
        "selection_rule": "manual whitelist of LLM candidates discussed in current protocol",
        "summary": {
            "candidate_count": len(rows),
            "allowed_for_backtest_count": sum(1 for item in rows if item["allowed_for_backtest"]),
            "all_candidates_stopped_before_new_backtest": all(not item["allowed_for_backtest"] for item in rows),
        },
        "candidates": rows,
    }


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    headers = [
        "Candidate",
        "Family",
        "Stage0",
        "Stage1",
        "Full",
        "Predictive",
        "Allowed backtest",
        "Status",
        "Key metrics",
        "Stop reason",
    ]
    lines = [
        "# LLM Candidate Status Summary",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        f"Scope: {payload['scope']}",
        "",
        f"Allowed for new backtest: **{payload['summary']['allowed_for_backtest_count']} / {payload['summary']['candidate_count']}**",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for item in payload["candidates"]:
        values = [
            item["candidate"],
            item["family"],
            item["stage0"],
            item["stage1_reliability"],
            item["full_inference"],
            item["predictive_gate"],
            "yes" if item["allowed_for_backtest"] else "no",
            item["status"],
            item["key_metrics"],
            item["stop_reason"],
        ]
        escaped = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(escaped) + " |")
    lines.append("")
    lines.append("## Artifact Sources")
    lines.append("")
    for item in payload["candidates"]:
        lines.append(f"### {item['candidate']}")
        for artifact in item["artifacts"]:
            lines.append(f"- `{artifact['path']}` (`sha256={artifact['sha256']}`)")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_csv(payload: dict[str, Any], path: Path) -> None:
    fieldnames = [
        "candidate",
        "family",
        "stage0",
        "stage1_reliability",
        "full_inference",
        "predictive_gate",
        "final_stage",
        "status",
        "allowed_for_backtest",
        "key_metrics",
        "stop_reason",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in payload["candidates"]:
            writer.writerow({name: item[name] for name in fieldnames})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-results", type=Path, default=Path(__file__).resolve().parents[2] / "results")
    parser.add_argument("--ktln-llm-results", type=Path, default=Path(__file__).resolve().parents[2] / "paper/input/results/llm")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()

    payload = build(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.output_md)
    write_csv(payload, args.output_csv)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
