#!/usr/bin/env python3
"""Audit the frozen outcome-blind CFTC RSS Internet Archive corpus v15."""
from __future__ import annotations
import hashlib,json
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'paper/input/results/llm/v15/cftc_rss_archive_corpus_v15'
CORPUS=BASE/'corpus.json';EXCLUDED=BASE/'excluded.json';MANIFEST=BASE/'manifest.json';AMEND=BASE/'implementation_amendment.json';OUTPUT=BASE/'corpus_gate.json'
MINIMUM=96

def sha(path: Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def parse(value: str)->datetime:
    result=datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:raise ValueError('timestamp lacks offset')
    return result

def audit()->dict:
    corpus=json.loads(CORPUS.read_text(encoding='utf-8'));excluded=json.loads(EXCLUDED.read_text(encoding='utf-8'));manifest=json.loads(MANIFEST.read_text(encoding='utf-8'));amend=json.loads(AMEND.read_text(encoding='utf-8'))
    records=corpus['records'];times=sorted({r['archive_capture_at'] for r in records},key=parse)
    checks={
      'outcome_blind':corpus.get('selection_uses_outcomes') is False and corpus.get('market_data_accessed') is False and corpus.get('model_run') is False,
      'amendment_outcome_blind':all(amend.get(k) is False for k in ('outcomes_consulted','market_data_accessed','model_run','backtest_consulted')),
      'manifest_hashes_match':manifest['files']['corpus.json']==sha(CORPUS) and manifest['files']['excluded.json']==sha(EXCLUDED) and manifest['files']['implementation_amendment.json']==sha(AMEND),
      'record_count_matches':manifest['admitted_records']==len(records),
      'unique_record_ids':len({r['record_id'] for r in records})==len(records),
      'unique_canonical_links':len({r['canonical_link'] for r in records})==len(records),
      'timestamps_ordered':all(parse(records[i]['archive_capture_at'])<=parse(records[i+1]['archive_capture_at']) for i in range(len(records)-1)),
      'publisher_time_not_after_information_time':all(parse(r['publisher_pubdate'])<=parse(r['archive_capture_at']) for r in records),
      'required_plain_text_present':all(r['title'] and r['description'] and '<' not in r['description'] and '>' not in r['description'] for r in records),
      'minimum_information_sets_met':len(times)>=MINIMUM,
    }
    passed=all(checks.values())
    reasons=Counter(r['reason'] for r in excluded['records'])
    return {
      'schema_version':'cftc-rss-archive-corpus-gate-v15','status':'OUTCOME_BLIND_CORPUS_GATE_PASS_EXTRACTION_AUTHORIZED' if passed else 'OUTCOME_BLIND_CORPUS_GATE_FAIL_STOP','passed':passed,'extraction_authorized':passed,'target_join_authorized':False,'outcomes_consulted':False,'market_data_accessed':False,'model_run':False,
      'counts':{'downloaded_snapshots':manifest['snapshot_count'],'parseable_snapshots':sum(bool(s['parse_ok']) for s in manifest['snapshots']),'corpus_records':len(records),'information_sets':len(times),'minimum_information_sets':MINIMUM,'excluded_item_or_snapshot_records':len(excluded['records']),'feed_records':manifest['feed_counts']},
      'information_time_range':{'first':times[0] if times else None,'last':times[-1] if times else None},
      'exclusion_reasons':dict(sorted(reasons.items())),'checks':checks,
      'inputs':{name:{'path':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':sha(path)} for name,path in [('corpus',CORPUS),('excluded',EXCLUDED),('manifest',MANIFEST),('implementation_amendment',AMEND),('auditor',Path(__file__))]},
      'interpretation':'Pass authorizes only outcome-blind LLM extraction. Market targets, predictive metrics, thresholds, backtests, Tech+LLM, and sealed holdout remain prohibited.'}

def main()->None:
    result=audit();OUTPUT.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(result,indent=2,sort_keys=True))
    if not result['passed']:raise SystemExit(2)
if __name__=='__main__':main()