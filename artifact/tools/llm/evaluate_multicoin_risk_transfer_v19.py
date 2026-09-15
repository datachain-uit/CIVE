import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from multicoin_event_transfer_v19_v20_common import bootstrap,metrics,ridge_predict,sha256,write_json

def holm(values):
    ordered=sorted(values,key=values.get); n=len(ordered); out={}; running=0.0
    for i,key in enumerate(ordered): running=max(running,min(1.0,(n-i)*values[key])); out[key]=running
    return out
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',type=Path,required=True); ap.add_argument('--panel',type=Path,required=True); ap.add_argument('--predictions',type=Path,required=True); ap.add_argument('--output',type=Path,required=True); a=ap.parse_args(); cfg=json.loads(a.config.read_text(encoding='utf-8'))
    for item in [cfg['sources']['screen'],cfg['sources']['inputs'],cfg['sources']['extraction'],cfg['sources']['information_sets'],cfg['sources']['protocol'],*cfg['sources']['code']]:
        if sha256(Path(item['path']))!=item['sha256']: raise ValueError('frozen source changed')
    panel=json.loads(a.panel.read_text(encoding='utf-8')); results={}; pred_assets={}; raw_p={}
    for asset_index,symbol in enumerate(cfg['eligible_assets']):
        rows=panel['assets'][symbol]['records']; all_pred=[]; fold_payload=[]; boot_folds=[]
        for fold in cfg['folds']:
            train=[r for r in rows if r['information_date']<=fold['train_end']]; valid=[r for r in rows if fold['valid_start']<=r['information_date']<=fold['valid_end']]
            fold_targets={}; fold_preds={}
            for target in cfg['targets'].values():
                y_train=np.asarray([r['targets'][target] for r in train]); y=np.asarray([r['targets'][target] for r in valid]); fold_targets[target]=y; fold_preds[target]={}
                for arm in ('metadata','generic','event'):
                    names=cfg['feature_contract'][arm]; xt=np.asarray([[r['features'][arm][n] for n in names] for r in train]); xv=np.asarray([[r['features'][arm][n] for n in names] for r in valid]); fold_preds[target][arm]=ridge_predict(xt,y_train,xv,float(cfg['model']['alpha']))
            for i,row in enumerate(valid): all_pred.append({'information_date':row['information_date'],'targets':row['targets'],'predictions':{t:{arm:float(fold_preds[t][arm][i]) for arm in fold_preds[t]} for t in fold_preds}})
            fold_payload.append({'fold':fold['fold'],'records':len(valid),'metrics':{t:{arm:metrics(fold_targets[t],fold_preds[t][arm]) for arm in fold_preds[t]} for t in fold_targets}})
            packed={}
            for t in fold_targets:
                packed[t]=fold_targets[t]
                for arm in ('metadata','generic','event'): packed[f'{t}_{arm}']=fold_preds[t][arm]
            boot_folds.append(packed)
        target_results={}
        for target_index,target in enumerate(cfg['targets'].values()):
            y=np.asarray([r['targets'][target] for r in all_pred]); predictions={arm:np.asarray([r['predictions'][target][arm] for r in all_pred]) for arm in ('metadata','generic','event')}; overall={arm:metrics(y,predictions[arm]) for arm in predictions}; unc=bootstrap(boot_folds,target,5000,7,int(cfg['bootstrap']['seed_base'])+asset_index*10+target_index); wins_meta=sum(f['metrics'][target]['event']['mse']<f['metrics'][target]['metadata']['mse'] for f in fold_payload); wins_generic=sum(f['metrics'][target]['event']['mse']<f['metrics'][target]['generic']['mse'] for f in fold_payload)
            target_results[target]={'overall':overall,'event_minus_metadata':{'delta_mse':overall['metadata']['mse']-overall['event']['mse'],'fold_wins':wins_meta},'event_minus_generic':{'delta_mse':overall['generic']['mse']-overall['event']['mse'],'fold_wins':wins_generic},'uncertainty':unc}
        primary=target_results[cfg['targets']['primary']]; raw_p[symbol]=primary['uncertainty']['one_sided_p_event_vs_metadata']; results[symbol]={'experiment_id':cfg['assets'][symbol]['experiment_id'],'oos_records':len(all_pred),'targets':target_results,'folds':fold_payload}; pred_assets[symbol]=all_pred
    adjusted=holm(raw_p)
    for symbol,res in results.items():
        p=res['targets'][cfg['targets']['primary']]; checks={'required_oos_records':res['oos_records']==cfg['gate']['required_oos_records'],'delta_mse_ci_lower_gt_zero':p['uncertainty']['event_minus_metadata_delta_mse_95_ci'][0]>0,'event_pearson_ci_lower_gt_zero':p['uncertainty']['event_pearson_95_ci'][0]>0,'fold_wins_at_least_3':p['event_minus_metadata']['fold_wins']>=cfg['gate']['minimum_fold_wins'],'prediction_nonconstant':p['overall']['event']['prediction_std']>0,'holm_p_below_alpha':adjusted[symbol]<cfg['gate']['holm_alpha']}; res['holm_adjusted_p']=adjusted[symbol]; res['checks']=checks; res['passed']=all(checks.values())
    family_pass=any(r['passed'] for r in results.values()); pred={'schema_version':1,'family_id':cfg['family_id'],'assets':pred_assets}; write_json(a.predictions,pred); payload={'schema_version':1,'family_id':cfg['family_id'],'evaluated_at':datetime.now(timezone.utc).isoformat(),'status':'PASS_RISK_TRANSFER' if family_pass else 'FAIL_RISK_TRANSFER','passed':family_pass,'assets':results,'stopped_assets':json.loads(Path(cfg['sources']['screen']['path']).read_text(encoding='utf-8'))['stopped_assets'],'inputs':{'predeclaration':{'path':str(a.config),'sha256':sha256(a.config)},'panel':{'path':str(a.panel),'sha256':sha256(a.panel)},'predictions':{'path':str(a.predictions),'sha256':sha256(a.predictions)}},'next_action':'Predeclare Tech risk overlay' if family_pass else 'Stop before Tech drawdown/cost evaluation'}; write_json(a.output,payload); print(json.dumps(payload,indent=2,ensure_ascii=False))
if __name__=='__main__': main()
