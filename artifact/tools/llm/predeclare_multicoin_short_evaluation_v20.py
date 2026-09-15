import json
from datetime import datetime,timezone
from pathlib import Path
from multicoin_event_transfer_v19_v20_common import ASSETS,CATALYST_TYPES,feature_names,is_asset_event,next_4h_open_ms,sha256,write_json

def norm(s): return ' '.join(s.casefold().split())
def main():
    root=Path(__file__).resolve().parents[2]; screen_path=root/'paper/input/results/llm/v20/llm_only_multicoin_short_screen_v20.json'; screen=json.loads(screen_path.read_text(encoding='utf-8'))
    inputs_path=root/'paper/input/results/llm/v3/llm_event_extraction_inputs_v3_development.json'; extraction_path=root/'paper/input/results/llm/v3/llm_event_extractor_v3_9_full_development.json'; inputs=json.loads(inputs_path.read_text(encoding='utf-8'))['records']; events=json.loads(extraction_path.read_text(encoding='utf-8'))['records']; by_id={r['headline_id']:r for r in events}; seen=set(); ordered=[]
    for row in sorted(inputs,key=lambda r:(r['published_at'],r['headline_id'])):
        key=norm(row['headline'])
        if key not in seen: seen.add(key); ordered.append((row,by_id[row['headline_id']]))
    metadata,generic,event=feature_names(); assets={}; bars={}; allowed=set(CATALYST_TYPES)
    for symbol in screen['eligible_assets']:
        times=sorted({next_4h_open_ms(i['published_at']) for i,e in ordered if is_asset_event(e,ASSETS[symbol]['aliases']) and e['event_type'] in allowed}); iso=[datetime.fromtimestamp(t/1000,timezone.utc).isoformat() for t in times]; counts=[]
        for fold in json.loads((root/'paper/input/results/llm/v20/llm_only_multicoin_short_screen_v20_predeclared.json').read_text(encoding='utf-8'))['folds']:
            counts.append({**fold,'train_records':sum(t<=fold['train_end'] for t in iso),'valid_records':sum(fold['valid_start']<=t<=fold['valid_end'] for t in iso)})
        assets[symbol]={'experiment_id':screen['assets'][symbol]['experiment_id'],'outcome_free_bucket_count':len(times),'folds':counts}; path=root/'results/bybit_lifecycle_4h'/f'{symbol}_1660348800000_1786492800000.json'; bars[symbol]={'path':str(path),'sha256':sha256(path)}
    protocol=root/'paper/working/protocols/LLM_Only_Multicoin_Short_Horizon_Transfer_Protocol_v20.md'; common=root/'tools/llm/multicoin_event_transfer_v19_v20_common.py'; builder=root/'tools/llm/build_multicoin_short_panel_v20.py'; evaluator=root/'tools/llm/evaluate_multicoin_short_transfer_v20.py'
    payload={'schema_version':1,'family_id':screen['family_id'],'stage':'PREDECLARED_BEFORE_TARGET_BUILD','frozen_at':datetime.now(timezone.utc).isoformat(),'target_values_consulted':False,'eligible_assets':screen['eligible_assets'],'assets':assets,'eligibility':{'event_types':CATALYST_TYPES,'dedupe':'first global normalized headline','asset_relation':'affected_assets closed aliases'},'target':{'field':'h4_return','formula':'open[next 4h]/open[current 4h]-1'},'feature_contract':{'metadata':metadata,'generic':generic,'event':event,'comparator_note':'metadata conditional on LLM asset/event selection'},'model':{'family':'Ridge','alpha':10.0,'standardization':'training fold only','tuning':False},'bootstrap':{'iterations':5000,'block_length':42,'seed_base':20260920},'gate':{'minimum_fold_wins':3,'holm_alpha':0.05,'requires_both_comparators':True},'sources':{'screen':{'path':str(screen_path),'sha256':sha256(screen_path)},'inputs':{'path':str(inputs_path),'sha256':sha256(inputs_path)},'extraction':{'path':str(extraction_path),'sha256':sha256(extraction_path)},'bars':bars,'protocol':{'path':str(protocol),'sha256':sha256(protocol)},'code':[{'path':str(p),'sha256':sha256(p)} for p in (common,builder,evaluator)]}}
    out=root/'paper/input/results/llm/v20/llm_only_multicoin_short_evaluation_v20_predeclared.json'; write_json(out,payload); print(out)
if __name__=='__main__': main()
