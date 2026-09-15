"""Freeze HYB-009 v1.1 sources and evaluator before PnL evaluation."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def item(p): return {"path":str(p),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
def main():
    audit=ROOT/"paper/input/results/hybrid/hyb009_model_substitution_sample_audit_v1_1.json"
    evaluator=ROOT/"tools/llm/evaluate_hyb009_model_substitution_v1_1.py"
    tech=ROOT/"results/technical_bybit_lifecycle_1x_candidate_hardened.json"
    old=json.loads((ROOT/"paper/input/results/hybrid/tech_llm_conditional_overlay_v1_predeclared.json").read_text(encoding="utf-8"))
    payload={"schema_version":1,"experiment_id":"HYB-009-v1.1-continuous-model-substitution","frozen_at":datetime.now(timezone.utc).isoformat(),"research_role":"post-outcome exploratory development","sources":{"audit":item(audit),"tech":item(tech),"evaluator":item(evaluator)},"folds":old["evaluation"]["folds"],"primary_estimand":"paired net return difference versus frozen Tech-Control","family_gate":"CI lower >0, gross mean >0, >=2/3 folds, Holm sign-flip p<0.05, and exceeds shuffled plus constant-0.75 placebos","prohibited":["retuning after PnL evaluation","claiming validation, holdout or live evidence"]}
    out=ROOT/"paper/input/results/hybrid/hyb009_model_substitution_v1_1_predeclared.json"; out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps({"output":str(out),"evaluator_sha256":payload["sources"]["evaluator"]["sha256"]},indent=2))
if __name__=="__main__": main()
