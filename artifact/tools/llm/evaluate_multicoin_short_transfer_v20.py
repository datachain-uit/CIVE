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
    for item in [cfg['sources']['screen'],cfg['sources']['inputs'],cfg['sources']['extraction'],cfg['sources']['protocol'],*cfg['sources']['code']]:
        if sha256(Path(item['path']))!=item['sha256']: raise ValueError('frozen source changed')
    panel=json.loads(a.panel.read_text(encoding='utf-8')); results={}; pred_assets={}; p_meta={};p_generic={};p_corr={}
    for ai,symbol in enumerate(cfg['eligible_assets']):
        rows=panel['assets'][symbol]['records']; fold_results=[]; boot=[]; predictions=[]
        for fold in cfg['assets'][symbol]['folds']:
            train=[r for r in rows if r['decision_at']<=fold['train_end']]; valid=[r for r in rows if fold['valid_start']<=r['decision_at']<=fold['valid_end']]
            if len(train)!=fold['train_records'] or len(valid)!=fold['valid_records']: raise ValueError(f'fold count mismatch {symbol} {fold["fold"]}')
            yt=np.asarray([r['target_h4_return'] for r in train]); y=np.asarray([r['target_h4_return'] for r in valid]); pred={}
            for arm in ('metadata','generic','event'):
                names=cfg['feature_contract'][arm]; xt=np.asarray([[r['features'][arm][n] for n in names] for r in train]); xv=np.asarray([[r['features'][arm][n] for n in names] for r in valid]); pred[arm]=ridge_predict(xt,yt,xv,float(cfg['model']['alpha']))
            fold_results.append({'fold':fold['fold'],'records':len(valid),'metrics':{arm:metrics(y,pred[arm]) for arm in pred}}); boot.append({'h4_return':y,'h4_return_metadata':pred['metadata'],'h4_return_generic':pred['generic'],'h4_return_event':pred['event']})
            predictions.extend({'decision_at':row['decision_at'],'target_h4_return':float(y[i]),**{f'{arm}_prediction':float(pred[arm][i]) for arm in pred}} for i,row in enumerate(valid))
        y=np.asarray([r['target_h4_return'] for r in predictions]); pred={arm:np.asarray([r[f'{arm}_prediction'] for r in predictions]) for arm in ('metadata','generic','event')}; overall={arm:metrics(y,pred[arm]) for arm in pred}; unc=bootstrap(boot,'h4_return',5000,42,int(cfg['bootstrap']['seed_base'])+ai); wins_meta=sum(f['metrics']['event']['mse']<f['metrics']['metadata']['mse'] for f in fold_results); wins_generic=sum(f['metrics']['event']['mse']<f['metrics']['generic']['mse'] for f in fold_results)
        results[symbol]={'experiment_id':cfg['assets'][symbol]['experiment_id'],'oos_records':len(predictions),'overall':overall,'event_minus_metadata':{'delta_mse':overall['metadata']['mse']-overall['event']['mse'],'fold_wins':wins_meta},'event_minus_generic':{'delta_mse':overall['generic']['mse']-overall['event']['mse'],'fold_wins':wins_generic},'uncertainty':unc,'folds':fold_results}; pred_assets[symbol]=predictions; p_meta[symbol]=unc['one_sided_p_event_vs_metadata'];p_generic[symbol]=unc['one_sided_p_event_vs_generic'];p_corr[symbol]=unc['one_sided_p_pearson']
    adj_meta,adj_generic,adj_corr=holm(p_meta),holm(p_generic),holm(p_corr)
    for symbol,res in results.items():
        u=res['uncertainty']; checks={'event_vs_metadata_ci_lower_gt_zero':u['event_minus_metadata_delta_mse_95_ci'][0]>0,'event_vs_generic_ci_lower_gt_zero':u['event_minus_generic_delta_mse_95_ci'][0]>0,'event_pearson_ci_lower_gt_zero':u['event_pearson_95_ci'][0]>0,'wins_metadata_at_least_3':res['event_minus_metadata']['fold_wins']>=cfg['gate']['minimum_fold_wins'],'wins_generic_at_least_3':res['event_minus_generic']['fold_wins']>=cfg['gate']['minimum_fold_wins'],'prediction_nonconstant':res['overall']['event']['prediction_std']>0,'holm_all_below_alpha':max(adj_meta[symbol],adj_generic[symbol],adj_corr[symbol])<cfg['gate']['holm_alpha']};res['holm_adjusted_p']={'metadata':adj_meta[symbol],'generic':adj_generic[symbol],'pearson':adj_corr[symbol]};res['checks']=checks;res['passed']=all(checks.values())
    family_pass=any(r['passed'] for r in results.values()); pred_payload={'schema_version':1,'family_id':cfg['family_id'],'assets':pred_assets};write_json(a.predictions,pred_payload);screen=json.loads(Path(cfg['sources']['screen']['path']).read_text(encoding='utf-8'));payload={'schema_version':1,'family_id':cfg['family_id'],'evaluated_at':datetime.now(timezone.utc).isoformat(),'status':'PASS_SHORT_HORIZON_TRANSFER' if family_pass else 'FAIL_SHORT_HORIZON_TRANSFER','passed':family_pass,'assets':results,'stopped_assets':screen['stopped_assets'],'inputs':{'predeclaration':{'path':str(a.config),'sha256':sha256(a.config)},'panel':{'path':str(a.panel),'sha256':sha256(a.panel)},'predictions':{'path':str(a.predictions),'sha256':sha256(a.predictions)}},'next_action':'Predeclare overlay development' if family_pass else 'Stop before threshold/action/backtest'};write_json(a.output,payload);print(json.dumps(payload,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
