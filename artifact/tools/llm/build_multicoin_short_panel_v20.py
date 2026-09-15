import argparse,json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from multicoin_event_transfer_v19_v20_common import ASSETS,FOUR_HOURS_MS,aggregate_features,is_asset_event,next_4h_open_ms,sha256,write_json

def norm(s): return ' '.join(s.casefold().split())
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',type=Path,required=True); ap.add_argument('--output',type=Path,required=True); a=ap.parse_args(); cfg=json.loads(a.config.read_text(encoding='utf-8'))
    if cfg['stage']!='PREDECLARED_BEFORE_TARGET_BUILD' or cfg['target_values_consulted'] is not False: raise ValueError('invalid config')
    for item in [cfg['sources']['screen'],cfg['sources']['inputs'],cfg['sources']['extraction'],cfg['sources']['protocol'],*cfg['sources']['code']]:
        if sha256(Path(item['path']))!=item['sha256']: raise ValueError('frozen source changed')
    inputs=json.loads(Path(cfg['sources']['inputs']['path']).read_text(encoding='utf-8'))['records']; events=json.loads(Path(cfg['sources']['extraction']['path']).read_text(encoding='utf-8'))['records']; by_id={r['headline_id']:r for r in events}; seen=set(); ordered=[]
    for row in sorted(inputs,key=lambda r:(r['published_at'],r['headline_id'])):
        key=norm(row['headline'])
        if key not in seen: seen.add(key); ordered.append((row,by_id[row['headline_id']]))
    allowed=set(cfg['eligibility']['event_types']); assets={}
    for symbol in cfg['eligible_assets']:
        bar=cfg['sources']['bars'][symbol]; path=Path(bar['path'])
        if sha256(path)!=bar['sha256']: raise ValueError('bar hash mismatch')
        bars={int(r[0]):r for r in json.loads(path.read_text(encoding='utf-8'))}; groups=defaultdict(list)
        for source,event in ordered:
            if is_asset_event(event,ASSETS[symbol]['aliases']) and event['event_type'] in allowed and event.get('status')=='success' and event.get('error') is None: groups[next_4h_open_ms(source['published_at'])].append((event,source))
        rows=[]; missing=0
        for ts in sorted(groups):
            if ts not in bars or ts+FOUR_HOURS_MS not in bars: missing+=1; continue
            rows.append({'decision_at':datetime.fromtimestamp(ts/1000,timezone.utc).isoformat(),'target_h4_return':float(bars[ts+FOUR_HOURS_MS][1])/float(bars[ts][1])-1.0,'features':aggregate_features(groups[ts]),'event_count':len(groups[ts])})
        assets[symbol]={'experiment_id':cfg['assets'][symbol]['experiment_id'],'records':rows,'summary':{'records':len(rows),'missing_target_buckets':missing,'start':rows[0]['decision_at'] if rows else None,'end':rows[-1]['decision_at'] if rows else None}}
    payload={'schema_version':1,'family_id':cfg['family_id'],'status':'DEVELOPMENT_SHORT_HORIZON_PANEL','outcomes_consulted':True,'assets':assets,'predeclaration':{'path':str(a.config),'sha256':sha256(a.config)}}; write_json(a.output,payload); print(json.dumps({s:v['summary'] for s,v in assets.items()},indent=2))
if __name__=='__main__': main()
