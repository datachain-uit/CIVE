import argparse,json,math
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from multicoin_event_transfer_v19_v20_common import ASSETS, FOUR_HOURS_MS, aggregate_features, is_asset_event, sha256, write_json

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',type=Path,required=True); ap.add_argument('--output',type=Path,required=True); a=ap.parse_args(); cfg=json.loads(a.config.read_text(encoding='utf-8'))
    if cfg['stage']!='PREDECLARED_BEFORE_TARGET_BUILD' or cfg['risk_target_values_consulted'] is not False: raise ValueError('invalid config')
    for item in [cfg['sources']['screen'],cfg['sources']['inputs'],cfg['sources']['extraction'],cfg['sources']['information_sets'],cfg['sources']['protocol'],*cfg['sources']['code']]:
        if sha256(Path(item['path']))!=item['sha256']: raise ValueError(f"hash mismatch {item['path']}")
    inputs=json.loads(Path(cfg['sources']['inputs']['path']).read_text(encoding='utf-8'))['records']; events=json.loads(Path(cfg['sources']['extraction']['path']).read_text(encoding='utf-8'))['records']; info=json.loads(Path(cfg['sources']['information_sets']['path']).read_text(encoding='utf-8'))['records']; input_by_id={r['headline_id']:r for r in inputs}
    assets={}
    for symbol in cfg['eligible_assets']:
        bar_spec=cfg['sources']['bars'][symbol]; bar_path=Path(bar_spec['path'])
        if sha256(bar_path)!=bar_spec['sha256']: raise ValueError('bar hash mismatch')
        by_time={int(r[0]):r for r in json.loads(bar_path.read_text(encoding='utf-8'))}; grouped=defaultdict(list); aliases=ASSETS[symbol]['aliases']
        for event in events:
            if event.get('status')=='success' and event.get('error') is None and is_asset_event(event,aliases): grouped[event['information_date']].append((event,input_by_id[event['headline_id']]))
        rows=[]
        for day in info:
            cutoff=int(datetime.fromisoformat(day['available_at']).astimezone(timezone.utc).timestamp()*1000); entry_ms=cutoff+FOUR_HOURS_MS; exit_ms=entry_ms+6*FOUR_HOURS_MS
            path=[by_time.get(ts) for ts in range(entry_ms,exit_ms,FOUR_HOURS_MS)]
            if by_time.get(entry_ms) is None or by_time.get(exit_ms) is None or any(r is None for r in path): continue
            entry=float(by_time[entry_ms][1]); closes=[float(r[4]) for r in path]; logs=[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes))]; min_low=min(float(r[3]) for r in path); features=aggregate_features(grouped.get(day['information_date'],[]))
            rows.append({'information_date':day['information_date'],'entry_at':datetime.fromtimestamp(entry_ms/1000,timezone.utc).isoformat(),'targets':{'h24_realized_volatility':math.sqrt(sum(x*x for x in logs)),'h24_adverse_excursion_magnitude':max(0.0,1.0-min_low/entry)},'features':features})
        assets[symbol]={'experiment_id':cfg['assets'][symbol]['experiment_id'],'records':rows,'summary':{'records':len(rows),'start':rows[0]['information_date'] if rows else None,'end':rows[-1]['information_date'] if rows else None}}
    payload={'schema_version':1,'family_id':cfg['family_id'],'status':'DEVELOPMENT_RISK_PANEL','outcomes_consulted':True,'assets':assets,'predeclaration':{'path':str(a.config),'sha256':sha256(a.config)}}; write_json(a.output,payload); print(json.dumps({s:v['summary'] for s,v in assets.items()},indent=2))
if __name__=='__main__': main()
