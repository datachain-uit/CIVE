"""Build a hashable, outcome-blind Federal Register crypto corpus from official raw-text endpoints."""
from __future__ import annotations
import hashlib,json,re,time,urllib.request
from datetime import datetime,timezone,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
REF=ROOT/"paper/input/references/source_artifacts/federal_register_crypto_v12_5"
OUT=ROOT/"paper/input/results/llm/v12_5/federal_register_crypto_corpus_v12_5"
MARK=re.compile(r"(?i)all rights reserved|copyright.{0,80}(?:third.party|permission|reprodu)")
def sha(b): return hashlib.sha256(b).hexdigest()
def get(url):
 r=urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"KLTN-v12.5-corpus/1.0"}),timeout=45)
 return r.read()
def main():
 if (OUT/"manifest.json").exists(): raise SystemExit("Manifest exists; preserve evidence and version reruns.")
 raw=OUT/"raw"; raw.mkdir(parents=True,exist_ok=True); docs=[]
 for y in range(2020,2026):
  docs+=json.loads((REF/f"query_{y}.json").read_text(encoding="utf-8"))["results"]
 admitted=[]; excluded=[]
 for i,d in enumerate(sorted(docs,key=lambda x:(x["publication_date"],x["document_number"]))):
  n=d["document_number"]; day=d["publication_date"].replace("-","/")
  url=f"https://www.federalregister.gov/documents/full_text/text/{day}/{n}.txt"
  try: b=get(url)
  except Exception as e: excluded.append({"document_number":n,"reason":"fetch_error","error":str(e)}); continue
  p=raw/f"{n}.txt"; p.write_bytes(b); text=b.decode("utf-8",errors="replace").strip()
  reasons=[]
  if len(text)<400: reasons.append("text_too_short")
  if MARK.search(text): reasons.append("rights_marker")
  rec={"id":n,"publication_date":d["publication_date"],"available_at_utc":(datetime.fromisoformat(d["publication_date"]).replace(tzinfo=timezone.utc)+timedelta(days=1)).isoformat(),"title":d["title"],"type":d["type"],"agencies":[a["name"] for a in d["agencies"]],"source_url":url,"source_sha256":sha(b),"text":text,"text_sha256":sha(text.encode()),"admission_reasons":reasons}
  (excluded if reasons else admitted).append(rec)
  if i%20==0: print(json.dumps({"processed":i+1,"admitted":len(admitted),"excluded":len(excluded)}))
  time.sleep(.08)
 admitted.sort(key=lambda x:(x["available_at_utc"],x["id"])); excluded.sort(key=lambda x:x["id"])
 (OUT/"corpus.json").write_text(json.dumps(admitted,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 (OUT/"excluded.json").write_text(json.dumps(excluded,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 files={p.name:sha(p.read_bytes()) for p in raw.glob("*.txt")}
 m={"status":"OUTCOME_BLIND_TEXT_CORPUS_NEEDS_REVIEWER_FREEZE","documents_queried":len(docs),"admitted_documents":len(admitted),"excluded_documents":len(excluded),"raw_files":files,"market_data_accessed":False,"model_run":False,"next_gate":["verify package hashes","freeze corpus contract","sample manual rights review before any model"]}
 (OUT/"manifest.json").write_text(json.dumps(m,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({k:m[k] for k in ("status","documents_queried","admitted_documents","excluded_documents")}))
if __name__=="__main__": main()
