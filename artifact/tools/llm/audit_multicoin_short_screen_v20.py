import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from multicoin_event_transfer_v19_v20_common import is_asset_event, next_4h_open_ms, sha256, write_json

def norm(s): return ' '.join(s.casefold().split())
def main():
    root=Path(__file__).resolve().parents[2]; pre_path=root/'paper/input/results/llm/v20/llm_only_multicoin_short_screen_v20_predeclared.json'; pre=json.loads(pre_path.read_text(encoding='utf-8'))
    if pre['stage']!='PREDECLARED_BEFORE_OUTCOME_FREE_BUCKET_SCREEN' or pre['outcomes_consulted_for_v20_design'] is not False: raise ValueError('invalid predeclaration')
    for item in [pre['sources']['protocol'],*pre['sources']['code']]:
        if sha256(Path(item['path']))!=item['sha256']: raise ValueError('frozen source changed')
    inputs=json.loads(Path(pre['sources']['inputs']['path']).read_text(encoding='utf-8'))['records']; events=json.loads(Path(pre['sources']['extraction']['path']).read_text(encoding='utf-8'))['records']; by_id={r['headline_id']:r for r in events}; seen=set(); ordered=[]
    for row in sorted(inputs,key=lambda r:(r['published_at'],r['headline_id'])):
        key=norm(row['headline'])
        if key in seen: continue
        seen.add(key); ordered.append((row,by_id[row['headline_id']]))
    results={}; t=pre['thresholds']; allowed=set(pre['eligibility']['event_types'])
    for symbol,spec in pre['assets'].items():
        aliases=set(spec['aliases']); selected=[(i,e) for i,e in ordered if is_asset_event(e,aliases) and e['event_type'] in allowed and e.get('status')=='success' and e.get('error') is None]; buckets=Counter(next_4h_open_ms(i['published_at']) for i,e in selected); fold_counts=[]
        for fold in pre['folds']:
            count=sum(fold['valid_start']<=datetime.fromtimestamp(ts/1000,timezone.utc).isoformat()<=fold['valid_end'] for ts in buckets); fold_counts.append({'fold':fold['fold'],'buckets':count})
        bar_exists=Path(spec['bar_path']).is_file(); checks={'eligible_events':len(selected)>=t['minimum_eligible_events'],'unique_buckets':len(buckets)>=t['minimum_unique_buckets'],'each_oos_fold':all(x['buckets']>=t['minimum_buckets_each_oos_fold'] for x in fold_counts),'bar_file_present':bar_exists}; passed=all(checks.values())
        results[symbol]={'experiment_id':spec['experiment_id'],'priority':spec['priority'],'passed':passed,'status':'PASS_TARGET_PREDECLARATION_AUTHORIZED' if passed else 'FAIL_STOP_BEFORE_TARGET','summary':{'eligible_events':len(selected),'unique_buckets':len(buckets),'fold_counts':fold_counts,'bar_file_present':bar_exists},'checks':checks}
    payload={'schema_version':1,'family_id':pre['family_id'],'generated_at':datetime.now(timezone.utc).isoformat(),'status':'SCREEN_COMPLETE','outcomes_consulted':False,'predeclaration':{'path':str(pre_path),'sha256':sha256(pre_path)},'assets':results,'eligible_assets':[s for s,r in results.items() if r['passed']],'stopped_assets':[s for s,r in results.items() if not r['passed']]}
    out=root/'paper/input/results/llm/v20/llm_only_multicoin_short_screen_v20.json'; write_json(out,payload); print(json.dumps(payload,indent=2,ensure_ascii=False))
if __name__=='__main__': main()
