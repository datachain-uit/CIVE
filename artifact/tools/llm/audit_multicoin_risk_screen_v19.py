import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from multicoin_event_transfer_v19_v20_common import ASSETS, DAILY_FOLDS, is_asset_event, sha256, write_json

def main():
    root=Path(__file__).resolve().parents[2]; pre_path=root/'paper/input/results/llm/v19/llm_only_multicoin_risk_screen_v19_predeclared.json'; pre=json.loads(pre_path.read_text(encoding='utf-8'))
    if pre['stage']!='PREDECLARED_BEFORE_OUTCOME_FREE_SCREEN' or pre['outcomes_consulted_for_v19_design'] is not False: raise ValueError('invalid predeclaration')
    for item in [pre['sources']['protocol'],*pre['sources']['code']]:
        if sha256(Path(item['path']))!=item['sha256']: raise ValueError('frozen source changed')
    inputs=json.loads(Path(pre['sources']['inputs']['path']).read_text(encoding='utf-8'))['records']; extraction=json.loads(Path(pre['sources']['extraction']['path']).read_text(encoding='utf-8'))['records']; dates=[r['information_date'] for r in json.loads(Path(pre['sources']['information_sets']['path']).read_text(encoding='utf-8'))['records']]
    if len(inputs)!=len(extraction) or {r['headline_id'] for r in inputs}!={r['headline_id'] for r in extraction}: raise ValueError('extractor/input mismatch')
    results={}; t=pre['thresholds']
    for symbol,spec in pre['assets'].items():
        aliases=set(spec['aliases']); events=[r for r in extraction if is_asset_event(r,aliases)]; event_dates={r['information_date'] for r in events}; folds=[]
        for fold in DAILY_FOLDS:
            valid={d for d in dates if fold['valid_start']<=d<=fold['valid_end']}; folds.append({'fold':fold['fold'],'event_dates':len(valid&event_dates),'event_records':sum(r['information_date'] in valid for r in events)})
        fallback=sum(r.get('evidence_fallback') is True for r in events); bar_exists=Path(spec['bar_path']).is_file()
        checks={'direct_records':len(events)>=t['minimum_direct_event_records'],'direct_dates':len(event_dates)>=t['minimum_direct_event_dates'],'each_oos_fold':all(x['event_dates']>=t['minimum_event_dates_each_oos_fold'] for x in folds),'fallback_fraction':bool(events) and fallback/len(events)<t['maximum_fallback_fraction'],'bar_file_present':bar_exists}
        passed=all(checks.values()); results[symbol]={'experiment_id':spec['experiment_id'],'priority':spec['priority'],'passed':passed,'status':'PASS_TARGET_PREDECLARATION_AUTHORIZED' if passed else 'FAIL_STOP_BEFORE_TARGET','summary':{'event_records':len(events),'event_dates':len(event_dates),'fallback_records':fallback,'fallback_fraction':fallback/len(events) if events else None,'fold_counts':folds,'direction_counts':dict(Counter(r['direction'] for r in events)),'bar_file_present':bar_exists},'checks':checks}
    payload={'schema_version':1,'family_id':pre['family_id'],'generated_at':datetime.now(timezone.utc).isoformat(),'status':'SCREEN_COMPLETE','outcomes_consulted':False,'predeclaration':{'path':str(pre_path),'sha256':sha256(pre_path)},'assets':results,'eligible_assets':[s for s,r in results.items() if r['passed']],'stopped_assets':[s for s,r in results.items() if not r['passed']]}
    out=root/'paper/input/results/llm/v19/llm_only_multicoin_risk_screen_v19.json'; write_json(out,payload); print(json.dumps(payload,indent=2,ensure_ascii=False))
if __name__=='__main__': main()
