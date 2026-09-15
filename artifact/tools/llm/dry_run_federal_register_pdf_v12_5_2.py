"""Dry-run official GovInfo PDF rendition and local text extraction."""
import hashlib,io,json,urllib.request
from pathlib import Path
import pdfplumber
ROOT=Path(__file__).resolve().parents[2]
REF=ROOT/"paper/input/references/source_artifacts/federal_register_crypto_v12_5"
OUT=ROOT/"paper/input/results/llm/v12_5/federal_register_crypto_pdf_dry_run_v12_5_2.json"
def fetch(url): return urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"KLTN-v12.5-pdf-dry-run/1.0"}),timeout=45).read()
def main():
 if OUT.exists(): raise SystemExit("Dry-run exists; preserve evidence.")
 docs=[]
 for y in range(2020,2026): docs+=json.loads((REF/f"query_{y}.json").read_text(encoding="utf-8"))["results"]
 rows=[]
 for d in sorted(docs,key=lambda x:(x["publication_date"],x["document_number"]))[:10]:
  row={"id":d["document_number"],"publication_date":d["publication_date"],"pdf_url":d.get("pdf_url"),"result":"QUARANTINE"}
  try:
   b=fetch(row["pdf_url"]); pdf=pdfplumber.open(io.BytesIO(b)); text="\n".join(p.extract_text() or "" for p in pdf.pages)
   row.update({"pdf_bytes":len(b),"pdf_sha256":hashlib.sha256(b).hexdigest(),"pages":len(pdf.pages),"text_chars":len(text),"text_sha256":hashlib.sha256(text.encode()).hexdigest()})
   if not b.startswith(b"%PDF"): row["reason"]="not_pdf"
   elif len(text)<400: row["reason"]="text_too_short"
   else: row["result"]="PASS_PDF_RENDITION"
  except Exception as e: row.update({"reason":"pdf_fetch_or_extract_error","error":str(e)})
  rows.append(row)
 report={"status":"DRY_RUN_PDF_RENDITION_GATE","documents":rows,"pass_count":sum(x["result"]=="PASS_PDF_RENDITION" for x in rows),"market_data_accessed":False,"model_run":False}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"status":report["status"],"pass_count":report["pass_count"],"total":len(rows)}))
if __name__=="__main__": main()
