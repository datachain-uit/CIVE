"""Outcome-free continuous-sizing remediation for HYB-009."""
from __future__ import annotations
import hashlib, json, random
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    prior=ROOT/"paper/input/results/hybrid/hyb009_model_substitution_sample_audit.json"
    old=json.loads(prior.read_text(encoding="utf-8"))
    assignments={}; diagnostics={}
    for i,(name,d) in enumerate(old["diagnostics"].items()):
        keys=[r["key"] for r in d["rows"]]
        weights=[1-0.5*float(r["bearish_percentile"]) for r in d["rows"]]
        shuffled=weights.copy(); random.Random(20260913+i).shuffle(shuffled)
        assignments[name]={"primary":dict(zip(keys,weights)),"shuffled":dict(zip(keys,shuffled)),"constant_075":{k:0.75 for k in keys}}
        diagnostics[name]={"covered":len(keys),"active":sum(w<1 for w in weights),"weight_min":min(weights),"weight_max":max(weights),"weight_mean":sum(weights)/len(weights)}
    checks={
        n+"_coverage_24_and_active_at_least_20":d["covered"]==24 and d["active"]>=20
        for n,d in diagnostics.items()
    }
    payload={"schema_version":1,"experiment_id":"HYB-009-v1.1-continuous-model-substitution","audited_at":datetime.now(timezone.utc).isoformat(),"outcomes_consulted_by_remediation":False,"rationale":"Scale-invariant continuous downside sizing avoids outcome-free threshold sparsity; fixed before PnL access. The effective-sample gate requires all 24 frozen Tech opportunities to be covered and at least 20 to receive a non-unit weight, matching the existing minimum-opportunity gate while allowing a causal percentile of exactly zero to preserve full Tech exposure.","policy":"weight = 1 - 0.5 * causal bearish percentile","status":"PASS" if all(checks.values()) else "FAIL","checks":checks,"diagnostics":diagnostics,"assignments":assignments,"source":{"path":str(prior),"sha256":sha(prior)}}
    out=ROOT/"paper/input/results/hybrid/hyb009_model_substitution_sample_audit_v1_1.json"
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":payload["status"],"diagnostics":diagnostics},indent=2))
if __name__=="__main__": main()
