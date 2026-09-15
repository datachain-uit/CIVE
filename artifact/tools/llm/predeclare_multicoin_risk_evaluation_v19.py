import json
from datetime import datetime, timezone
from pathlib import Path
from multicoin_event_transfer_v19_v20_common import DAILY_FOLDS, feature_names, sha256, write_json

def main():
    root=Path(__file__).resolve().parents[2]; screen_path=root/'paper/input/results/llm/v19/llm_only_multicoin_risk_screen_v19.json'; screen=json.loads(screen_path.read_text(encoding='utf-8'))
    if screen['outcomes_consulted'] is not False: raise ValueError('screen is not outcome-free')
    common=root/'tools/llm/multicoin_event_transfer_v19_v20_common.py'; builder=root/'tools/llm/build_multicoin_risk_panel_v19.py'; evaluator=root/'tools/llm/evaluate_multicoin_risk_transfer_v19.py'; protocol=root/'paper/working/protocols/LLM_Only_Multicoin_Risk_Transfer_Protocol_v19.md'; inputs=root/'paper/input/results/llm/v3/llm_event_extraction_inputs_v3_development.json'; extraction=root/'paper/input/results/llm/v3/llm_event_extractor_v3_9_full_development.json'; info=root/'paper/input/results/llm/llm_daily_information_sets_multisource_v2_development.json'
    metadata,generic,event=feature_names(); bars={}
    for symbol in screen['eligible_assets']:
        path=root/'results/bybit_lifecycle_4h'/f'{symbol}_1660348800000_1786492800000.json'; bars[symbol]={'path':str(path),'sha256':sha256(path)}
    payload={'schema_version':1,'family_id':screen['family_id'],'stage':'PREDECLARED_BEFORE_TARGET_BUILD','frozen_at':datetime.now(timezone.utc).isoformat(),'risk_target_values_consulted':False,'eligible_assets':screen['eligible_assets'],'assets':{s:{'experiment_id':screen['assets'][s]['experiment_id']} for s in screen['eligible_assets']},'targets':{'primary':'h24_realized_volatility','secondary_diagnostic':'h24_adverse_excursion_magnitude'},'target_contract':{'entry_delay_hours':4,'horizon_hours':24,'realized_volatility':'sqrt(sum squared 4h close-to-close log returns), exact v3.2 convention','adverse_excursion_magnitude':'max(0, 1-min(low_path)/entry_open)'},'feature_contract':{'metadata':metadata,'generic':generic,'event':event,'comparator_note':'metadata is conditional on LLM affected_assets selection'},'model':{'family':'Ridge','alpha':10.0,'standardization':'training fold only','tuning':False},'folds':DAILY_FOLDS,'bootstrap':{'iterations':5000,'block_length':7,'seed_base':20260919},'gate':{'required_oos_records':699,'minimum_fold_wins':3,'primary_only':True,'holm_alpha':0.05},'sources':{'screen':{'path':str(screen_path),'sha256':sha256(screen_path)},'inputs':{'path':str(inputs),'sha256':sha256(inputs)},'extraction':{'path':str(extraction),'sha256':sha256(extraction)},'information_sets':{'path':str(info),'sha256':sha256(info)},'bars':bars,'protocol':{'path':str(protocol),'sha256':sha256(protocol)},'code':[{'path':str(p),'sha256':sha256(p)} for p in (common,builder,evaluator)]}}
    out=root/'paper/input/results/llm/v19/llm_only_multicoin_risk_evaluation_v19_predeclared.json'; write_json(out,payload); print(out)
if __name__=='__main__': main()
