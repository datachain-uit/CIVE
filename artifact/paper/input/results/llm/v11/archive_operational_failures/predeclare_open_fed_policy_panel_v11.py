"""Freeze v11 target join before reading target values."""
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def item(path): return {"path": path, "sha256": digest(path)}


def main():
    extraction = Path("paper/input/results/llm/v11/open_fed_policy_extraction_v11.json")
    bars = Path(r"D:\projects\auto-trading\results\bybit_lifecycle_4h\BTCUSDT_1660348800000_1786492800000.json")
    output = Path("paper/input/results/llm/v11/open_fed_policy_panel_v11_predeclared.json")
    payload = {
        "schema_version": "open-fed-policy-panel-predeclaration-v11", "predeclared_at": datetime.now(timezone.utc).isoformat(),
        "status": "FROZEN_BEFORE_V11_TARGET_VALUES_ACCESSED", "prior_v3_v8_outcomes_consulted": True, "v11_target_values_consulted": False,
        "sources": {"events": item("paper/input/results/llm/v11/conditional_fed_policy_events_v11/events.json"), "extraction": {"path": str(extraction), "sha256": digest(extraction)}, "btc_4h": {"path": str(bars), "sha256": digest(bars)}},
        "code": {"builder": item("tools/llm/build_open_fed_policy_panel_v11.py"), "tests": item("tools/llm/test_build_open_fed_policy_panel_v11.py")},
        "protocol": item("paper/working/protocols/LLM_Only_Open_Fed_Policy_Protocol_v11.md"),
        "target": {"asset": "BTCUSDT", "horizon_hours": 4, "rule": "strictly next UTC 4h open to following 4h open"},
        "predictive_feature_policy": "LLM output only; market data target-only",
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8"); print(json.dumps({"output": str(output), "sha256": digest(output)}, indent=2))


if __name__ == "__main__": main()
