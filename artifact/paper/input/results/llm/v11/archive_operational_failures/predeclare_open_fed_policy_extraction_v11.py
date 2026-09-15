"""Freeze v11 model extraction before target construction."""
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

MODEL_DIGEST = "1922accd5827ebe6829e536369195db25eaf664528dc66206d646ea3bb386b71"


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def item(path): return {"path": path, "sha256": digest(path)}


def main():
    output = Path("paper/input/results/llm/v11/open_fed_policy_extraction_v11_predeclared.json")
    payload = {
        "schema_version": "open-fed-policy-extraction-predeclaration-v11", "predeclared_at": datetime.now(timezone.utc).isoformat(),
        "status": "FROZEN_BEFORE_MARKET_TARGET_ACCESS", "development_only": True, "strict_point_in_time": False,
        "sources": {"events": item("paper/input/results/llm/v11/conditional_fed_policy_events_v11/events.json")},
        "model": {"name": "ministral-3:8b", "digest": MODEL_DIGEST},
        "contract": {"prompt": item("tools/llm/prompts/open_fed_policy_v11.txt"), "schema": item("tools/llm/schemas/open_fed_policy_v11.json"), "producer": item("tools/llm/score_open_fed_policy_v11.py"), "tests": item("tools/llm/test_score_open_fed_policy_v11.py"), "protocol": item("paper/working/protocols/LLM_Only_Open_Fed_Policy_Protocol_v11.md"), "batch_size": 1, "workers": 1, "temperature": 0, "seed": 20260905, "think": False},
        "outcomes_consulted_for_v11_extraction": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "sha256": digest(output)}, indent=2))


if __name__ == "__main__": main()
