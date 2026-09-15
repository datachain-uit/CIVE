"""Group same-time policy documents into independent event units; no outcomes."""
import hashlib
import json
from collections import Counter
from pathlib import Path

from audit_social_intake_v9 import ROOT, save
from build_fomc_provenance_addendum_v10 import approximate_correlation_mde


def group_documents(documents):
    groups = {}
    for row in documents:
        groups.setdefault(row['published_at_claimed_utc'], []).append(row)
    events = []
    for published_at, rows in sorted(groups.items()):
        rows.sort(key=lambda row: row['id'])
        ids = [row['id'] for row in rows]
        sections = [f"DOCUMENT {index + 1}\n{row['text']}" for index, row in enumerate(rows)]
        text = '\n\n'.join(sections)
        event_id = hashlib.sha256((published_at + '|' + '|'.join(ids)).encode()).hexdigest()[:20]
        events.append({'event_id': event_id, 'published_at_claimed_utc': published_at,
                       'document_ids': ids, 'document_count': len(rows),
                       'categories': sorted({row['category'] for row in rows}),
                       'text': text, 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                       'historical_first_version_verified': all(
                           row['historical_first_version_verified'] for row in rows)})
    return events


def main():
    source = ROOT / 'paper/input/results/llm/v11/open_fed_policy_corpus_v11_0_1/corpus.json'
    out = ROOT / 'paper/input/results/llm/v11/open_fed_policy_events_v11'
    if out.exists():
        raise SystemExit('Event artifact exists; preserve it and version changes.')
    documents = json.loads(source.read_text(encoding='utf-8'))
    events = group_documents(documents)
    years = Counter(row['published_at_claimed_utc'][:4] for row in events)
    category_sets = Counter('+'.join(row['categories']) for row in events)
    lengths = sorted(len(row['text']) for row in events)
    audit = {'status': 'EVENT_CORPUS_READY_FOR_ARCHIVE_AUDIT_NOT_MODEL_RUN',
             'source': str(source.relative_to(ROOT)),
             'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
             'documents': len(documents), 'events': len(events),
             'same_time_documents_collapsed': len(documents) - len(events),
             'events_per_year': dict(years), 'event_category_sets': dict(category_sets),
             'text_chars': {'min': min(lengths), 'median_lower': lengths[(len(lengths)-1)//2],
                            'max': max(lengths)},
             'approximate_two_sided_correlation_mde': approximate_correlation_mde(len(events)),
             'planning_assumptions': {'alpha': 0.05, 'power': 0.80,
                                      'independent_event_correlation': True,
                                      'optimistic_for_temporal_modeling': True},
             'model_run': False, 'market_data_accessed': False,
             'historical_availability_certified': False,
             'next_gate': ['Archive-version audit without outcome selection',
                           'Freeze one target/window and temporal split',
                           'Freeze model hash, prompt, decoding and thermal runner']}
    save(out / 'events.json', json.dumps(events, ensure_ascii=False, indent=2).encode())
    save(out / 'audit.json', json.dumps(audit, indent=2).encode())
    print(json.dumps({'events': len(events), 'events_per_year': dict(years),
                      'same_time_documents_collapsed': audit['same_time_documents_collapsed'],
                      'correlation_mde': audit['approximate_two_sided_correlation_mde']}))


if __name__ == '__main__':
    main()
