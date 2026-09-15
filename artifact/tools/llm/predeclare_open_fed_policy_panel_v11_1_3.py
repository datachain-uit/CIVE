"""Freeze the successfully extracted v11.1.3 target join."""
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def item(path): return {"path":path,"sha256":digest(path)}
def main():
    panel=Path("paper/input/results/llm/v11/open_fed_policy_panel_v11.json")
    payload={"schema_version":"open-fed-policy-panel-predeclaration-v11.1.3","predeclared_at":datetime.now(timezone.utc).isoformat(),"status":"FROZEN_AFTER_OUTCOME_BLIND_EXTRACTION_BEFORE_METRICS","sources":{"events":item("paper/input/results/llm/v11/conditional_fed_policy_events_v11/events.json"),"extraction":item("paper/input/results/llm/v11/open_fed_policy_extraction_v11_1_3.json"),"btc_4h":item("results/bybit_lifecycle_4h/BTCUSDT_1660348800000_1786492800000.json")},"code":{"builder":item("tools/llm/build_open_fed_policy_panel_v11.py"),"tests":item("tools/llm/test_build_open_fed_policy_panel_v11.py")},"target":{"asset":"BTCUSDT","horizon_hours":4,"rule":"strictly next UTC 4h open to following 4h open"},"predictive_feature_policy":"LLM output only; market data target-only","target_values_consulted_for_design":False}
    out=Path("paper/input/results/llm/v11/open_fed_policy_panel_v11_1_3_predeclared.json");out.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8");print(json.dumps({"output":str(out),"sha256":digest(out)},indent=2))
if __name__=="__main__":main()
