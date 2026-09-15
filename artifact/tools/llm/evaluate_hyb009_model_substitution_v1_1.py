"""Evaluate frozen HYB-009 continuous model-substitution assignments."""
from __future__ import annotations
import argparse, itertools, json
from datetime import datetime, timezone
from pathlib import Path
from run_tech_llm_conditional_overlay_v1 import read_json, sha256, summarize, key, iso

def signflip_p(rows):
    groups={}
    for r in rows:
        dt=datetime.fromtimestamp(r["entry_time"]/1000,timezone.utc); q=f"{dt.year}-Q{(dt.month-1)//3+1}"
        groups.setdefault(q,[]).append(r["paired_net_difference"])
    sums=[sum(v) for v in groups.values()]; observed=sum(sums)/sum(len(v) for v in groups.values())
    values=[sum(s*x for s,x in zip(signs,sums))/sum(len(v) for v in groups.values()) for signs in itertools.product((-1,1),repeat=len(sums))]
    return (1+sum(v>=observed for v in values))/(1+len(values)) if observed>0 else 1.0
def holm(items):
    ordered=sorted(items,key=lambda x:x[1]); out={}; run=0; m=len(items)
    for i,(n,p) in enumerate(ordered): run=max(run,min(1,(m-i)*p)); out[n]=run
    return out
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--config",type=Path,required=True); ap.add_argument("--output",type=Path,required=True); a=ap.parse_args()
    c=read_json(a.config)
    for x in c["sources"].values():
        if sha256(Path(x["path"]))!=x["sha256"]: raise ValueError("hash mismatch "+x["path"])
    audit=read_json(Path(c["sources"]["audit"]["path"])); tech=read_json(Path(c["sources"]["tech"]["path"]))
    required=set(next(iter(audit["assignments"].values()))["primary"]); base=[]; cumulative=0
    for t in sorted(tech["closed_trades"],key=lambda x:(int(x["entry_time"]),x["symbol"])):
        entry=int(t["entry_time"]); eq=float(tech["result"]["starting_balance"])+cumulative
        if f"{entry}::{t['symbol']}" in required:
            cost=float(t["execution_cost"])+float(t["fees"])+float(t["funding_paid"])
            base.append({"symbol":t["symbol"],"entry_time":entry,"entry_time_iso":iso(entry),"exit_time":int(t["exit_time"]),"exit_time_iso":iso(int(t["exit_time"])),"exit_reason":t["reason"],"tech_entry_equity":eq,"tech_gross_return":float(t["gross_price_pnl"])/eq,"tech_cost_return":cost/eq,"tech_net_return":float(t["net_pnl"])/eq})
        cumulative+=float(t["net_pnl"])
    results={}; pvals=[]
    for name,arms in audit["assignments"].items():
        results[name]={k:summarize(name+"_"+k,v,base,c["folds"]) for k,v in arms.items()}
        p=signflip_p(results[name]["primary"]["paired_rows"]); results[name]["primary"]["one_sided_signflip_p"]=p; pvals.append((name,p))
    adjusted=holm(pvals)
    decisions={}
    for n,x in results.items():
        p=x["primary"]; p["holm_adjusted_p"]=adjusted[n]
        decisions[n]={"economic_increment":p["paired_net_difference_ci95"][0]>0 and p["mean_paired_gross_difference"]>0 and p["positive_folds"]>=2 and adjusted[n]<0.05 and p["mean_paired_net_difference"]>max(x["shuffled"]["mean_paired_net_difference"],x["constant_075"]["mean_paired_net_difference"])}
    out={"schema_version":1,"experiment_id":c["experiment_id"],"evaluated_at":datetime.now(timezone.utc).isoformat(),"scope":"post-outcome exploratory development; not validation/holdout/live","status":"COMPLETE","decisions":decisions,"results":results,"predeclaration":{"path":str(a.config),"sha256":sha256(a.config)}}
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"COMPLETE","decisions":decisions,"summary":{n:{k:v for k,v in x["primary"].items() if k not in ("paired_rows","folds")} for n,x in results.items()}},indent=2))
if __name__=="__main__": main()
