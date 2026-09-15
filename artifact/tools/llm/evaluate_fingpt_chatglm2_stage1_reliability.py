"""Run the FinGPT ChatGLM2 Stage1 operational reliability gate.

This is intentionally stored in the KLTN workspace so the result artifact can be
used by the thesis evidence ledger without mutating the production repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


CONTRACT_VERSION = "fingpt-benchmark-headline-label-mean-v1"
CONTRACT_TEXT = (
    "Treat every nonempty line in a daily information set as one metadata-prefixed headline. "
    "Remove the leading metadata bracket. For each title, use the official FinGPT Benchmark "
    "prompt: Instruction: What is the sentiment of this news? Please choose an answer from "
    "{negative/neutral/positive}. Input: <headline>. Answer:. Generate greedily with at most 8 "
    "new tokens and parse exactly one label from negative, neutral or positive. Daily score "
    "equals (positive count minus negative count) divided by parsed headline count. Any "
    "unparseable or multiple-label answer makes the information set an explicit error. Market "
    "outcomes are not used."
)
CONTRACT_HASH = hashlib.sha256(CONTRACT_TEXT.encode()).hexdigest()
HEADLINE_PATTERN = re.compile(r"^-\s*\[[^\]]+\]\s*(.+?)\s*$")
LABEL_PATTERN = re.compile(r"\b(negative|neutral|positive)\b", re.IGNORECASE)
INSTRUCTION = (
    "What is the sentiment of this news? Please choose an answer from "
    "{negative/neutral/positive}."
)


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def stratified_sample(records: list[dict], per_year: int) -> list[dict]:
    if per_year <= 0:
        return records
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[record["information_date"][:4]].append(record)
    selected: list[dict] = []
    for year in sorted(groups):
        group = groups[year]
        if len(group) <= per_year:
            selected.extend(group)
            continue
        indices = (
            [round(index * (len(group) - 1) / (per_year - 1)) for index in range(per_year)]
            if per_year > 1
            else [len(group) // 2]
        )
        selected.extend(group[index] for index in indices)
    return selected


def parse_headlines(text: str) -> list[str]:
    headlines: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = HEADLINE_PATTERN.match(line.strip())
        if not match:
            raise ValueError(f"daily information-set line violates contract: {line[:80]}")
        headlines.append(match.group(1))
    if not headlines:
        raise ValueError("daily information set contains no headlines")
    return headlines


def parse_label(answer: str) -> str:
    labels = {match.lower() for match in LABEL_PATTERN.findall(answer)}
    if len(labels) != 1:
        raise ValueError(f"expected exactly one sentiment label, got {sorted(labels)}")
    return next(iter(labels))


def prompt(headline: str) -> str:
    return f"Instruction: {INSTRUCTION}\nInput: {headline}\nAnswer: "


def score_labels(labels: list[str]) -> float:
    if not labels:
        raise ValueError("cannot score an empty label set")
    return (labels.count("positive") - labels.count("negative")) / len(labels)


def classify_daily(headlines: list[str], torch, tokenizer, model, max_input_tokens: int, max_new_tokens: int) -> dict:
    rows: list[dict] = []
    labels: list[str] = []
    for headline in headlines:
        inputs = tokenizer(
            prompt(headline),
            return_tensors="pt",
            truncation=True,
            max_length=max_input_tokens,
            return_token_type_ids=False,
        )
        inputs = {key: value.cuda() for key, value in inputs.items()}
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                eos_token_id=tokenizer.eos_token_id,
            )
        new_tokens = generated[0, inputs["input_ids"].shape[1]:]
        answer = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        label = parse_label(answer)
        labels.append(label)
        rows.append({"headline": headline, "answer": answer, "label": label})
    return {
        "parsed_headlines": len(headlines),
        "score": score_labels(labels),
        "label_counts": {label: labels.count(label) for label in ("negative", "neutral", "positive")},
        "records": rows,
    }


def completed_keys(payload: dict) -> set[tuple[int, str]]:
    keys: set[tuple[int, str]] = set()
    for run in payload.get("runs", []):
        run_index = int(run["run"])
        for record in run.get("records", []):
            keys.add((run_index, record["content_hash"]))
    return keys


def ensure_run(payload: dict, run_index: int) -> dict:
    for run in payload["runs"]:
        if int(run["run"]) == run_index:
            return run
    run = {"run": run_index, "records": []}
    payload["runs"].append(run)
    payload["runs"].sort(key=lambda item: int(item["run"]))
    return run


def finalize(payload: dict, required_sets: int, run_count: int) -> None:
    run_records = {int(run["run"]): run.get("records", []) for run in payload.get("runs", [])}
    success_each = [
        sum(record.get("status") == "success" for record in run_records.get(index, []))
        for index in range(1, run_count + 1)
    ]
    count_matches_each = [
        sum(record.get("headline_count_matches") is True for record in run_records.get(index, []))
        for index in range(1, run_count + 1)
    ]
    exact_score_agreement = 0
    mean_abs_diff = None
    max_abs_diff = None
    if run_count >= 2 and all(len(run_records.get(index, [])) == required_sets for index in range(1, run_count + 1)):
        left = {record["content_hash"]: record for record in run_records[1]}
        right = {record["content_hash"]: record for record in run_records[2]}
        diffs = []
        for content_hash, left_record in left.items():
            right_record = right.get(content_hash)
            if not right_record:
                continue
            if left_record.get("score") == right_record.get("score"):
                exact_score_agreement += 1
            if left_record.get("score") is not None and right_record.get("score") is not None:
                diffs.append(abs(float(left_record["score"]) - float(right_record["score"])))
        if diffs:
            mean_abs_diff = sum(diffs) / len(diffs)
            max_abs_diff = max(diffs)
    payload["checks"] = {
        "information_sets": {"observed": required_sets, "required": required_sets, "passed": True},
        "schema_success_each_run": {"observed": success_each, "required": required_sets},
        "headline_count_matches_each_run": {"observed": count_matches_each, "required": required_sets},
        "exact_score_agreement": {"observed": exact_score_agreement, "required_min": required_sets},
        "mean_absolute_score_difference": {"observed": mean_abs_diff, "required_max": 0.0},
        "max_absolute_score_difference": {"observed": max_abs_diff, "required_max": 0.0},
    }
    passed = (
        success_each == [required_sets] * run_count
        and count_matches_each == [required_sets] * run_count
        and exact_score_agreement == required_sets
        and mean_abs_diff == 0.0
        and max_abs_diff == 0.0
    )
    payload["passed"] = passed
    payload["status"] = (
        "stage1-pass-full-calibration-authorized"
        if passed
        else "stage1-fail-stop-before-full-inference"
    )
    payload["evaluated_at"] = datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--base-revision", required=True)
    parser.add_argument("--adapter-revision", required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--base-model-id", required=True)
    parser.add_argument("--sample-per-year", type=int, default=12)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--max-input-tokens", type=int, default=512)
    parser.add_argument("--max-new-tokens", type=int, default=8)
    parser.add_argument("--power-plan-observed", default=None)
    args = parser.parse_args()

    input_payload = json.loads(args.input.read_text(encoding="utf-8"))
    selected = stratified_sample(input_payload["records"], args.sample_per_year)
    if args.output.exists():
        result = json.loads(args.output.read_text(encoding="utf-8"))
        if result.get("contract_hash") != CONTRACT_HASH:
            raise ValueError("checkpoint contract hash does not match")
    else:
        result = {
            "schema_version": 1,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "experiment_id": args.experiment_id,
            "stage": "stage1-operational-reliability",
            "model": {
                "base": args.base_model_id,
                "base_revision": args.base_revision,
                "adapter": "FinGPT/fingpt-mt_chatglm2-6b_lora",
                "adapter_revision": args.adapter_revision,
            },
            "input": {
                "artifact": str(args.input),
                "sha256": sha256_file(args.input),
                "selected_information_sets": len(selected),
                "sample_per_year": args.sample_per_year,
            },
            "contract_version": CONTRACT_VERSION,
            "contract_hash": CONTRACT_HASH,
            "market_outcomes_consulted": False,
            "trading_backtest_consulted": False,
            "runtime": {
                "device": "cuda:0",
                "workers": 1,
                "generation": "greedy",
                "quantization": "bnb-nf4",
                "max_input_tokens": args.max_input_tokens,
                "max_new_tokens": args.max_new_tokens,
                "power_plan_observed": args.power_plan_observed,
            },
            "runs": [],
            "passed": False,
            "status": "stage1-running",
            "error": None,
        }
        write_atomic(args.output, result)

    model = None
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModel, AutoTokenizer, BitsAndBytesConfig

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available")
        tokenizer = AutoTokenizer.from_pretrained(
            args.base, trust_remote_code=True, local_files_only=True
        )
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        model = AutoModel.from_pretrained(
            args.base,
            trust_remote_code=True,
            local_files_only=True,
            device_map={"": 0},
            low_cpu_mem_usage=True,
            quantization_config=quantization_config,
            torch_dtype=torch.float16,
        ).eval()
        model = PeftModel.from_pretrained(
            model, args.adapter, local_files_only=True
        ).eval()
        result["runtime"].update({
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
        })
        torch.cuda.reset_peak_memory_stats()

        done = completed_keys(result)
        for run_index in range(1, args.runs + 1):
            run = ensure_run(result, run_index)
            for source in selected:
                key = (run_index, source["content_hash"])
                if key in done:
                    continue
                base = {
                    "content_hash": source["content_hash"],
                    "information_date": source["information_date"],
                    "available_at": source["available_at"],
                    "source_snapshot_hash": source["source_snapshot_hash"],
                    "selected_article_count": source["selected_article_count"],
                }
                try:
                    headlines = parse_headlines(source["text"])
                    if len(headlines) != int(source["selected_article_count"]):
                        raise ValueError(
                            f"parsed {len(headlines)} headlines but expected {source['selected_article_count']}"
                        )
                    scored = classify_daily(
                        headlines, torch, tokenizer, model, args.max_input_tokens, args.max_new_tokens
                    )
                    record = {
                        **base,
                        "status": "success",
                        "headline_count_matches": True,
                        **scored,
                        "error": None,
                    }
                except Exception as exc:
                    record = {
                        **base,
                        "status": "error",
                        "parsed_headlines": None,
                        "headline_count_matches": False,
                        "score": None,
                        "label_counts": None,
                        "records": [],
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                run["records"].append(record)
                result["runtime"]["peak_allocated_mib"] = round(
                    torch.cuda.max_memory_allocated() / 1024 / 1024, 2
                )
                finalize(result, len(selected), args.runs)
                if result["status"].startswith("stage1-pass"):
                    result["status"] = "stage1-running"
                    result["passed"] = False
                write_atomic(args.output, result)
                print(
                    f"run={run_index} {len(run['records'])}/{len(selected)} "
                    f"{source['information_date']} {record['status']}",
                    flush=True,
                )
        finalize(result, len(selected), args.runs)
    except Exception as exc:
        result["status"] = "stage1-infeasible-stop-before-full-inference"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
    finally:
        if model is not None:
            del model
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        result["evaluated_at"] = datetime.now(timezone.utc).isoformat()
        write_atomic(args.output, result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.get("passed") else 2)


if __name__ == "__main__":
    main()
