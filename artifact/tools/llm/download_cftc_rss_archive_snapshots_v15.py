#!/usr/bin/env python3
"""Checkpointed outcome-blind download of pinned CFTC RSS archive snapshots for v15."""
from __future__ import annotations
import argparse, hashlib, json, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SCREEN=ROOT/'paper/input/references/source_artifacts/cftc_rss_internet_archive_v15/source_screen.json'
PREDECLARED=ROOT/'paper/input/results/llm/v15/cftc_rss_archive_corpus_v15/predeclared.json'
SOURCE_DIR=ROOT/'paper/input/references/source_artifacts/cftc_rss_internet_archive_v15/rss_snapshots'
PROGRESS=ROOT/'paper/input/results/llm/v15/cftc_rss_archive_corpus_v15/download_progress.json'
FEEDS={'general':'https://www.cftc.gov/RSS/RSSGP/rssgp.xml','enforcement':'https://www.cftc.gov/RSS/RSSENF/rssenf.xml'}

def digest(data: bytes)->str: return hashlib.sha256(data).hexdigest()
def atomic_json(path: Path,payload: dict)->None:
    temp=path.with_suffix(path.suffix+'.tmp'); temp.write_text(json.dumps(payload,sort_keys=True,indent=2)+'\n',encoding='utf-8'); temp.replace(path)
def fetch(url: str,timeout: int)->bytes:
    last=None
    for attempt in range(4):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'KLTN-CFTC-RSS-v15-provenance-audit/1.0','Accept':'application/rss+xml, application/xml, text/xml'})
            with urllib.request.urlopen(req,timeout=timeout) as response:
                if response.status!=200: raise RuntimeError(f'HTTP {response.status}')
                return response.read()
        except Exception as exc:
            last=exc; time.sleep(1+attempt)
    raise RuntimeError(str(last))

def main()->None:
    parser=argparse.ArgumentParser(); parser.add_argument('--delay',type=float,default=.25); parser.add_argument('--timeout',type=int,default=45); args=parser.parse_args()
    screen=json.loads(SCREEN.read_text(encoding='utf-8')); pre=json.loads(PREDECLARED.read_text(encoding='utf-8'))
    if screen['decision']!='SOURCE_SCREEN_PASS_FULL_OUTCOME_BLIND_CORPUS_AUDIT_REQUIRED': raise RuntimeError('source screen did not authorize corpus audit')
    if digest(SCREEN.read_bytes())!=pre['source_screen']['sha256']: raise RuntimeError('source screen hash differs from predeclaration')
    if any(pre[key] is not False for key in ('market_data_accessed','outcomes_consulted','model_run','trading_backtest_consulted')): raise RuntimeError('predeclaration is not outcome-blind')
    tasks=[]
    for feed in ('general','enforcement'):
        for row in screen['cdx'][feed]: tasks.append((feed,row))
    tasks.sort(key=lambda item:(item[1]['timestamp'],item[0]))
    completed=[]; errors=[]
    for index,(feed,row) in enumerate(tasks,1):
        folder=SOURCE_DIR/feed; folder.mkdir(parents=True,exist_ok=True); target=folder/f"{row['timestamp']}.xml"
        state='existing'
        try:
            if not target.exists():
                url=f"https://web.archive.org/web/{row['timestamp']}id_/{FEEDS[feed]}"
                body=fetch(url,args.timeout); temp=target.with_suffix('.xml.tmp'); temp.write_bytes(body); temp.replace(target); state='downloaded'; time.sleep(args.delay)
            body=target.read_bytes(); completed.append({'feed':feed,'timestamp':row['timestamp'],'cdx_digest':row['digest'],'cdx_length':row['length'],'file':str(target.relative_to(ROOT)),'sha256':digest(body),'bytes':len(body),'state':state})
        except Exception as exc:
            errors.append({'feed':feed,'timestamp':row['timestamp'],'error':str(exc)})
        payload={'schema_version':'cftc-rss-archive-download-progress-v15','status':'DOWNLOAD_COMPLETE' if index==len(tasks) and not errors else 'DOWNLOAD_IN_PROGRESS','updated_at':datetime.now(timezone.utc).isoformat(),'expected':len(tasks),'processed':index,'success':len(completed),'errors':errors,'market_data_accessed':False,'outcomes_consulted':False,'records':completed}
        atomic_json(PROGRESS,payload)
        if index%10==0 or index==len(tasks): print(f"{index}/{len(tasks)} success={len(completed)} errors={len(errors)}",flush=True)
    if errors: raise SystemExit(2)
if __name__=='__main__': main()