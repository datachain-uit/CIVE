from datetime import datetime, timezone
from pathlib import Path
from multicoin_event_transfer_v19_v20_common import ASSETS, EXPERIMENTS_V19, DAILY_FOLDS, sha256, write_json

def main():
    root=Path(__file__).resolve().parents[2]; out=root/'paper/input/results/llm/v19/llm_only_multicoin_risk_screen_v19_predeclared.json'
    protocol=root/'paper/working/protocols/LLM_Only_Multicoin_Risk_Transfer_Protocol_v19.md'; common=root/'tools/llm/multicoin_event_transfer_v19_v20_common.py'; audit=root/'tools/llm/audit_multicoin_risk_screen_v19.py'
    bars_dir=root/'results/bybit_lifecycle_4h'
    bars={s:str(bars_dir/f'{s}_1660348800000_1786492800000.json') for s in ASSETS}
    inputs=root/'paper/input/results/llm/v3/llm_event_extraction_inputs_v3_development.json'; extraction=root/'paper/input/results/llm/v3/llm_event_extractor_v3_9_full_development.json'; info=root/'paper/input/results/llm/llm_daily_information_sets_multisource_v2_development.json'
    payload={'schema_version':1,'family_id':'LLM-077--LLM-080-multicoin-risk-v19','stage':'PREDECLARED_BEFORE_OUTCOME_FREE_SCREEN','frozen_at':datetime.now(timezone.utc).isoformat(),'outcomes_consulted_for_v19_design':False,'prior_project_results_known':True,'assets':{s:{'experiment_id':EXPERIMENTS_V19[s],'aliases':sorted(v['aliases']),'priority':v['priority'],'bar_path':bars[s]} for s,v in ASSETS.items()},'folds':DAILY_FOLDS,'thresholds':{'minimum_direct_event_records':1000,'minimum_direct_event_dates':700,'minimum_event_dates_each_oos_fold':100,'maximum_fallback_fraction':0.05,'bar_file_required':True},'sources':{'inputs':{'path':str(inputs),'sha256':sha256(inputs)},'extraction':{'path':str(extraction),'sha256':sha256(extraction)},'information_sets':{'path':str(info),'sha256':sha256(info)},'protocol':{'path':str(protocol),'sha256':sha256(protocol)},'code':[{'path':str(p),'sha256':sha256(p)} for p in (common,audit)]}}
    write_json(out,payload); print(out)
if __name__=='__main__': main()
