"""Run the predeclared FinGPT ChatGLM2 INT4 feasibility gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import traceback
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


def first_headlines(input_path: Path, count: int) -> list[str]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    result: list[str] = []
    for record in payload["records"]:
        for line in record["text"].splitlines():
            if not line.strip():
                continue
            match = HEADLINE_PATTERN.match(line.strip())
            if not match:
                raise ValueError(f"headline line violates contract: {line[:80]}")
            result.append(match.group(1))
            if len(result) == count:
                return result
    raise ValueError(f"corpus contains fewer than {count} headlines")


def parse_label(answer: str) -> str:
    labels = {match.lower() for match in LABEL_PATTERN.findall(answer)}
    if len(labels) != 1:
        raise ValueError(f"expected exactly one sentiment label, got {sorted(labels)}")
    return next(iter(labels))


def prompt(headline: str) -> str:
    return f"Instruction: {INSTRUCTION}\nInput: {headline}\nAnswer: "


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
    parser.add_argument("--quantization", choices=("official-int4", "bnb-nf4"), required=True)
    parser.add_argument("--headline-count", type=int, default=12)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--max-input-tokens", type=int, default=512)
    parser.add_argument("--max-new-tokens", type=int, default=8)
    args = parser.parse_args()

    result = {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": args.experiment_id,
        "stage": "stage0-feasibility",
        "model": {
            "base": args.base_model_id,
            "base_revision": args.base_revision,
            "adapter": "FinGPT/fingpt-mt_chatglm2-6b_lora",
            "adapter_revision": args.adapter_revision,
        },
        "contract_version": CONTRACT_VERSION,
        "contract_hash": CONTRACT_HASH,
        "market_outcomes_consulted": False,
        "trading_backtest_consulted": False,
        "runs": [],
        "passed": False,
        "status": "stage0-running",
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
        headlines = first_headlines(args.input, args.headline_count)
        tokenizer = AutoTokenizer.from_pretrained(
            args.base, trust_remote_code=True, local_files_only=True
        )
        if args.quantization == "bnb-nf4":
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
        else:
            model = AutoModel.from_pretrained(
                args.base, trust_remote_code=True, local_files_only=True
            ).half().cuda().eval()
        model = PeftModel.from_pretrained(
            model, args.adapter, local_files_only=True
        ).eval()
        torch.cuda.reset_peak_memory_stats()

        for run_index in range(args.runs):
            records = []
            for headline in headlines:
                text = prompt(headline)
                inputs = tokenizer(
                    text,
                    return_tensors="pt",
                    truncation=True,
                    max_length=args.max_input_tokens,
                    return_token_type_ids=False,
                )
                inputs = {key: value.cuda() for key, value in inputs.items()}
                with torch.inference_mode():
                    generated = model.generate(
                        **inputs,
                        max_new_tokens=args.max_new_tokens,
                        do_sample=False,
                        eos_token_id=tokenizer.eos_token_id,
                    )
                new_tokens = generated[0, inputs["input_ids"].shape[1]:]
                answer = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
                try:
                    label = parse_label(answer)
                    error = None
                except Exception as exc:
                    label = None
                    error = f"{type(exc).__name__}: {exc}"
                records.append({
                    "headline": headline,
                    "answer": answer,
                    "label": label,
                    "error": error,
                })
            result["runs"].append({"run": run_index + 1, "records": records})
            write_atomic(args.output, result)

        run_labels = [[row["label"] for row in run["records"]] for run in result["runs"]]
        parsed_each = [sum(label is not None for label in labels) for labels in run_labels]
        exact_agreement = sum(
            all(labels[index] == run_labels[0][index] for labels in run_labels[1:])
            for index in range(args.headline_count)
        ) if len(run_labels) > 1 else args.headline_count
        result["runtime"] = {
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
            "peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 1024 / 1024, 2),
            "max_input_tokens": args.max_input_tokens,
            "max_new_tokens": args.max_new_tokens,
            "generation": "greedy",
            "quantization": args.quantization,
        }
        result["checks"] = {
            "parsed_labels_each_run": parsed_each,
            "required_parsed_labels_each_run": args.headline_count,
            "exact_label_agreement": exact_agreement,
            "required_exact_label_agreement": args.headline_count,
        }
        result["passed"] = (
            parsed_each == [args.headline_count] * args.runs
            and exact_agreement == args.headline_count
        )
        result["status"] = (
            "stage0-pass-stage1-authorized"
            if result["passed"]
            else "stage0-fail-stop-before-stage1"
        )
    except Exception as exc:
        result["status"] = "stage0-infeasible-stop-before-stage1"
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
    raise SystemExit(0 if result["passed"] else 2)


if __name__ == "__main__":
    main()
