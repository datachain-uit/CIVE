#!/usr/bin/env python3
"""Build and verify the outcome-blind CFTC RSS Internet Archive corpus v15."""
from __future__ import annotations
import argparse, hashlib, html, json, re, urllib.parse, xml.etree.ElementTree as ET
from html.parser import HTMLParser
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SCREEN=ROOT/'paper/input/references/source_artifacts/cftc_rss_internet_archive_v15/source_screen.json'
PRE=ROOT/'paper/input/results/llm/v15/cftc_rss_archive_corpus_v15/predeclared.json'
AMEND=ROOT/'paper/input/results/llm/v15/cftc_rss_archive_corpus_v15/implementation_amendment.json'
PROGRESS=ROOT/'paper/input/results/llm/v15/cftc_rss_archive_corpus_v15/download_progress.json'
SNAPSHOTS=ROOT/'paper/input/references/source_artifacts/cftc_rss_internet_archive_v15/rss_snapshots'
OUT=ROOT/'paper/input/results/llm/v15/cftc_rss_archive_corpus_v15'

def sha(data: bytes)->str:return hashlib.sha256(data).hexdigest()
def canonical_json(value)->bytes:return (json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode()
def write(path: Path,value)->None:path.write_bytes(canonical_json(value))
def capture_time(value: str)->datetime:return datetime.strptime(value,'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
def pub_time(value: str)->datetime:
    parsed=parsedate_to_datetime(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:raise ValueError('pubDate lacks explicit offset')
    return parsed

class PlainText(HTMLParser):
    def __init__(self)->None:super().__init__(convert_charrefs=True);self.parts=[]
    def handle_data(self,data: str)->None:self.parts.append(data)
    def handle_starttag(self,tag: str,attrs)->None:
        if tag.lower() in {'br','p','div','li'}:self.parts.append(' ')
    def handle_endtag(self,tag: str)->None:
        if tag.lower() in {'p','div','li'}:self.parts.append(' ')

def clean(value: str|None)->str:return ' '.join(html.unescape(value or '').split())
def plain_text(value: str|None)->str:
    parser=PlainText();parser.feed(value or '');parser.close();return clean(' '.join(parser.parts))
def child(item: ET.Element,name: str)->str:
    node=item.find(name);raw=node.text if node is not None else None
    return plain_text(raw) if name=='description' else clean(raw)
def canonical_link(value: str)->str:
    parsed=urllib.parse.urlsplit(value.strip())
    host=(parsed.hostname or '').lower()
    if host not in {'cftc.gov','www.cftc.gov'}:raise ValueError('non-CFTC host')
    path=re.sub('/+','/',parsed.path).rstrip('/')
    if not re.fullmatch(r'/PressRoom/PressReleases/[^/]+',path,re.I):raise ValueError('non-release link')
    return 'https://www.cftc.gov'+path

def build()->dict:
    screen=json.loads(SCREEN.read_text(encoding='utf-8'));pre=json.loads(PRE.read_text(encoding='utf-8'));amend=json.loads(AMEND.read_text(encoding='utf-8'));progress=json.loads(PROGRESS.read_text(encoding='utf-8'))
    if sha(SCREEN.read_bytes())!=pre['source_screen']['sha256']:raise RuntimeError('source screen hash mismatch')
    if any(amend[k] for k in ('outcomes_consulted','market_data_accessed','model_run','backtest_consulted')):raise RuntimeError('implementation amendment is not outcome-blind')
    if progress['status']!='DOWNLOAD_COMPLETE' or progress['success']!=progress['expected'] or progress['errors']:raise RuntimeError('raw snapshot download is incomplete')
    rows=[]
    for feed in ('general','enforcement'):
        for row in screen['cdx'][feed]:rows.append((row['timestamp'],feed,row))
    rows.sort()
    progress_by_key={(r['feed'],r['timestamp']):r for r in progress['records']}
    admitted={};excluded=[];snapshot_audit=[]
    for timestamp,feed,row in rows:
        path=SNAPSHOTS/feed/f'{timestamp}.xml';body=path.read_bytes();recorded=progress_by_key[(feed,timestamp)]
        if sha(body)!=recorded['sha256']:raise RuntimeError(f'raw snapshot hash mismatch: {feed} {timestamp}')
        info={'feed':feed,'archive_capture':timestamp,'archive_capture_at':capture_time(timestamp).isoformat(),'cdx_digest':row['digest'],'cdx_length':int(row['length']),'file':str(path.relative_to(ROOT)),'sha256':sha(body),'bytes':len(body)}
        try:root=ET.fromstring(body)
        except ET.ParseError as exc:
            excluded.append({'feed':feed,'archive_capture':timestamp,'reason':f'xml_parse_error:{exc}'});snapshot_audit.append({**info,'parse_ok':False,'items_seen':0,'items_admitted':0});continue
        items=root.findall('./channel/item');added=0
        for item in items:
            title,description,link,raw_pub=(child(item,x) for x in ('title','description','link','pubDate'))
            if not all((title,description,link,raw_pub)):
                excluded.append({'feed':feed,'archive_capture':timestamp,'link':link,'reason':'missing_required_field'});continue
            try:canonical=canonical_link(link);published=pub_time(raw_pub)
            except (TypeError,ValueError) as exc:
                excluded.append({'feed':feed,'archive_capture':timestamp,'link':link,'reason':str(exc)});continue
            available=capture_time(timestamp)
            if published.astimezone(timezone.utc)>available:
                excluded.append({'feed':feed,'archive_capture':timestamp,'link':canonical,'reason':'pubdate_after_archive_capture'});continue
            if canonical in admitted:continue
            text=f'TITLE: {title}\nDESCRIPTION: {description}'
            admitted[canonical]={'record_id':sha(canonical_json({'canonical_link':canonical,'archive_capture':timestamp,'text':text})),'feed':feed,'canonical_link':canonical,'text':text,'title':title,'description':description,'publisher_pubdate':published.isoformat(),'archive_capture_at':available.isoformat(),'archive_capture':timestamp,'archive_digest':row['digest'],'archive_length':int(row['length']),'snapshot_sha256':sha(body)};added+=1
        snapshot_audit.append({**info,'parse_ok':True,'items_seen':len(items),'items_admitted':added})
    records=sorted(admitted.values(),key=lambda r:(r['archive_capture_at'],r['canonical_link']))
    corpus={'schema_version':1,'corpus_id':'cftc-rss-internet-archive-v15','information_time':'archive_capture_at','selection_uses_outcomes':False,'market_data_accessed':False,'model_run':False,'records':records}
    exclusions={'schema_version':1,'corpus_id':'cftc-rss-internet-archive-v15','selection_uses_outcomes':False,'records':excluded}
    write(OUT/'corpus.json',corpus);write(OUT/'excluded.json',exclusions)
    manifest={'schema_version':1,'status':'OUTCOME_BLIND_CORPUS_CLOSED_PENDING_SCHEMA_AUDIT','corpus_id':corpus['corpus_id'],'selection_uses_outcomes':False,'market_data_accessed':False,'model_run':False,'trading_backtest_consulted':False,'information_time':'archive_capture_at','snapshot_count':len(snapshot_audit),'admitted_records':len(records),'excluded_records':len(excluded),'information_sets':len({r['archive_capture_at'] for r in records}),'feed_counts':dict(sorted(Counter(r['feed'] for r in records).items())),'files':{'source_screen.json':sha(SCREEN.read_bytes()),'predeclared.json':sha(PRE.read_bytes()),'implementation_amendment.json':sha(AMEND.read_bytes()),'download_progress.json':sha(PROGRESS.read_bytes()),'build_cftc_rss_archive_corpus_v15.py':sha(Path(__file__).read_bytes()),'corpus.json':sha((OUT/'corpus.json').read_bytes()),'excluded.json':sha((OUT/'excluded.json').read_bytes())},'snapshots':snapshot_audit}
    write(OUT/'manifest.json',manifest);return manifest

def verify()->dict:
    manifest=json.loads((OUT/'manifest.json').read_text());corpus=json.loads((OUT/'corpus.json').read_text());seen_links=set();seen_ids=set();previous=None
    if manifest['status']!='OUTCOME_BLIND_CORPUS_CLOSED_PENDING_SCHEMA_AUDIT':raise RuntimeError('unexpected status')
    paths={'source_screen.json':SCREEN,'predeclared.json':PRE,'implementation_amendment.json':AMEND,'download_progress.json':PROGRESS,'build_cftc_rss_archive_corpus_v15.py':Path(__file__),'corpus.json':OUT/'corpus.json','excluded.json':OUT/'excluded.json'}
    for name,path in paths.items():
        if sha(path.read_bytes())!=manifest['files'][name]:raise RuntimeError(f'hash mismatch: {name}')
    for row in corpus['records']:
        available=datetime.fromisoformat(row['archive_capture_at']);published=datetime.fromisoformat(row['publisher_pubdate'])
        if available.tzinfo is None or published.tzinfo is None or published.astimezone(timezone.utc)>available.astimezone(timezone.utc):raise RuntimeError('timestamp contract failure')
        if previous and available<previous:raise RuntimeError('order failure')
        if row['canonical_link'] in seen_links or row['record_id'] in seen_ids:raise RuntimeError('duplicate identity')
        if not row['text'].startswith('TITLE: ') or '\nDESCRIPTION: ' not in row['text']:raise RuntimeError('text contract failure')
        if any(token in row for token in ('price','return','target','label','feature','outcome')):raise RuntimeError('forbidden market/outcome field')
        previous=available;seen_links.add(row['canonical_link']);seen_ids.add(row['record_id'])
    return {'status':'SCHEMA_AUDIT_PASS','records':len(corpus['records']),'information_sets':len({r['archive_capture_at'] for r in corpus['records']}),'first':corpus['records'][0]['archive_capture_at'] if corpus['records'] else None,'last':corpus['records'][-1]['archive_capture_at'] if corpus['records'] else None}

def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args();print(json.dumps(verify() if args.verify else build(),indent=2))
if __name__=='__main__':main()