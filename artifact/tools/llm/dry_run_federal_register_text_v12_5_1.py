"""Validate official Federal Register text renditions for a ten-document dry run."""
import hashlib,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
REF=ROOT/"paper/input/references/source_artifacts/federal_register_crypto_v12_5"
OUT=ROOT/"paper/input/results/llm/v12_5/federal_register_crypto_text_dry_run_v12_5_1.json"
def fetch(url):
 r=urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"KLTN-v12.5-dry-run/1.0"}),timeout=45)
 return r.read(),r.headers.get_content_type()
def main():
 if OUT.exists(): raise SystemExit("Dry-run exists; preserve evidence.")
 docs=[]
 for y in range(2020,2026): docs+=json.loads((REF/f"query_{y}.json").read_text(encoding="utf-8"))["results"]
 rows=[]
 for d in sorted(docs,key=lambda x:(x["publication_date"],x["document_number"]))[:10]:
  n=d["document_number"]; meta,meta_type=fetch(f"https://www.federalregister.gov/api/v1/documents/{n}.json")
  detail=json.loads(meta); url=detail.get("raw_text_url")
  row={"id":n,"publication_date":d["publication_date"],"metadata_sha256":hashlib.sha256(meta).hexdigest(),"raw_text_url":url,"result":"QUARANTINE"}
  if not url: row["reason"]="raw_text_url_missing"
  else:
   try:
    text,ctype=fetch(url); row.update({"content_type":ctype,"bytes":len(text),"text_sha256":hashlib.sha256(text).hexdigest()})
    if ctype!="text/plain": row["reason"]="non_plain_content_type"
    elif len(text)<400: row["reason"]="text_too_short"
    else: row["result"]="PASS_RENDITION"
   except Exception as e: row["reason"]="text_fetch_error"; row["error"]=str(e)
  rows.append(row)
 report={"status":"DRY_RUN_RENDITION_GATE","documents":rows,"pass_count":sum(x["result"]=="PASS_RENDITION" for x in rows),"market_data_accessed":False,"model_run":False}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"status":report["status"],"pass_count":report["pass_count"],"total":len(rows)}))
if __name__=="__main__": main()
