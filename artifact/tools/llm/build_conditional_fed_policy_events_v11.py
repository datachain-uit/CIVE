"""Apply an outcome-blind same-day provenance gate and group event documents."""
import hashlib
import json
from collections import Counter
from datetime import datetime

from audit_social_intake_v9 import ROOT, save
from build_fomc_provenance_addendum_v10 import approximate_correlation_mde
from build_open_fed_policy_events_v11 import group_documents


def update_date(row):
    prefix = 'Last Update:'
    label = row.get('last_update_label')
    if not isinstance(label, str) or not label.startswith(prefix):
        return None
    try:
        return datetime.strptime(label[len(prefix):].strip(), '%B %d, %Y').date()
    except ValueError:
        return None


def listed_date(row):
    try:
        return datetime.strptime(row['listed_date'], '%m/%d/%Y').date()
    except (KeyError, TypeError, ValueError):
        return None


def main():
    source = ROOT / 'paper/input/results/llm/v11/open_fed_policy_corpus_v11_0_1/corpus.json'
    out = ROOT / 'paper/input/results/llm/v11/conditional_fed_policy_events_v11'
    if out.exists():
        raise SystemExit('Conditional gate exists; preserve and version changes.')
    rows = json.loads(source.read_text(encoding='utf-8'))
    admitted, quarantine = [], []
    for row in rows:
        release_day, last_update = listed_date(row), update_date(row)
        reasons = []
        if release_day is None or last_update is None:
            reasons.append('date_parse_failure')
        elif last_update != release_day:
            reasons.append('last_update_not_release_day')
        if reasons:
            quarantine.append({'id': row['id'], 'listed_date': row.get('listed_date'),
                               'last_update_label': row.get('last_update_label'),
                               'reasons': reasons})
        else:
            admitted.append(row)
    events = group_documents(admitted)
    years = Counter(row['published_at_claimed_utc'][:4] for row in events)
    audit = {'status': 'CONDITIONAL_DEVELOPMENT_CORPUS_NOT_STRICT_PIT_NOT_MODEL_RUN',
             'source': str(source.relative_to(ROOT)),
             'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
             'documents_before_gate': len(rows), 'same_day_documents': len(admitted),
             'quarantined_documents': len(quarantine), 'events': len(events),
             'same_time_documents_collapsed': len(admitted) - len(events),
             'events_per_year': dict(years),
             'approximate_two_sided_correlation_mde': approximate_correlation_mde(len(events)),
             'gate_uses_market_outcomes': False, 'market_data_accessed': False,
             'model_run': False, 'strict_point_in_time': False,
             'interpretation': [
                 'Same-day Last Update is weaker than first-version proof and permits unknown intraday edits.',
                 'Quarantine is a provenance gate fixed before outcomes, not a favorable-result filter.',
                 'Current snapshots define reproducible input bytes; they do not certify historical availability.',
                 'The MDE assumes independent correlations and is optimistic for temporal model evaluation.'],
             'next_gate': ['Freeze one development target and no-sweep horizon.',
                           'Freeze model/checkpoint, prompt/schema, decoding and temporal split.',
                           'Keep a no-information prior and generic LLM sentiment as mandatory comparators.']}
    save(out / 'events.json', json.dumps(events, ensure_ascii=False, indent=2).encode())
    save(out / 'quarantine.json', json.dumps(quarantine, indent=2).encode())
    save(out / 'audit.json', json.dumps(audit, indent=2).encode())
    print(json.dumps({'status': audit['status'], 'events': len(events),
                      'events_per_year': dict(years),
                      'quarantined_documents': len(quarantine),
                      'correlation_mde': audit['approximate_two_sided_correlation_mde']}))


if __name__ == '__main__':
    main()
