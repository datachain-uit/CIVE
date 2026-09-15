"""Small, sequential provenance pilot. No inference or price access."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from urllib.parse import urlencode

from audit_social_intake_v9 import ROOT, fetch, save

REVISION = 'ec2e6b75b0dbb40788dc297a2ef73e61a0629522'
WINDOWS = [('2023-04-01', '2023-04-02'), ('2024-01-01', '2024-01-02'),
           ('2025-01-01', '2025-01-02')]
KEEP = {'id', 'subreddit', 'created_utc', 'retrieved_on', 'edited', '_meta',
        'title', 'selftext', 'body', 'link_id', 'parent_id'}


def epoch(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and 0 < value < 4_102_444_800 else None


def inspect(record, kind):
    reasons = []
    created, observed = epoch(record.get('created_utc')), epoch(record.get('retrieved_on'))
    if created is None:
        reasons.append('creation_missing_or_invalid')
    if observed is None:
        reasons.append('observation_missing_or_invalid')
    lag = None
    if created is not None and observed is not None:
        lag = observed - created
        if lag < 0:
            reasons.append('observation_before_creation')
    if record.get('edited') is not False:
        reasons.append('edited_or_edit_status_unknown')
    meta = record.get('_meta')
    if not isinstance(meta, dict):
        reasons.append('version_metadata_missing')
        meta = {}
    if meta.get('is_edited'):
        reasons.append('second_retrieval_edited')
    if meta.get('was_initially_deleted') or meta.get('note') == 'initially_unavailable':
        reasons.append('restored_content_not_initial_version')
    if meta.get('was_deleted_later'):
        reasons.append('deleted_later_excluded_from_pilot')
    if meta.get('note') not in (None, 'no_2nd_retrieval', 'initially_unavailable'):
        reasons.append('unknown_version_note')
    second = meta.get('retrieved_2nd_on')
    if second is not None and (epoch(second) is None or (observed is not None and second < observed)):
        reasons.append('second_retrieval_time_invalid')
    fields = ['title', 'selftext'] if kind == 'posts' else ['body']
    text_fields = [record.get(key, '') for key in fields]
    if any(not isinstance(value, str) for value in text_fields):
        reasons.append('invalid_text_schema')
    else:
        if any(value.strip() in ('[deleted]', '[removed]') for value in text_fields):
            reasons.append('deleted_or_removed_text')
        if not any(value.strip() for value in text_fields):
            reasons.append('empty_text')
    return {'reasons': sorted(set(reasons)), 'observation_delay_seconds': lag,
            'next_4h_creation_boundary_observed': (
                observed < (int(created) // 14400 + 1) * 14400
                if created is not None and observed is not None and lag >= 0 else None)}


def audit(records, kind, start, end):
    begin = datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp()
    finish = datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp()
    seen = set()
    reasons = Counter()
    fields = Counter()
    notes = Counter()
    lags = []
    candidates = 0
    before_boundary = 0
    for record in records:
        result = inspect(record, kind)
        identity = record.get('id')
        if not isinstance(identity, str) or not identity:
            result['reasons'].append('id_missing')
        elif identity in seen:
            result['reasons'].append('duplicate_id')
        else:
            seen.add(identity)
        created = epoch(record.get('created_utc'))
        if created is not None and not begin <= created < finish:
            result['reasons'].append('outside_requested_window')
        if str(record.get('subreddit', '')).casefold() != 'bitcoin':
            result['reasons'].append('outside_requested_subreddit')
        reasons.update(set(result['reasons']))
        fields.update(record.keys())
        meta = record.get('_meta')
        notes[str(meta.get('note')) if isinstance(meta, dict) else 'metadata_missing'] += 1
        lag = result['observation_delay_seconds']
        if lag is not None and lag >= 0:
            lags.append(lag)
        if not result['reasons']:
            candidates += 1
            before_boundary += result['next_4h_creation_boundary_observed'] is True
    lags.sort()
    return {'kind': kind, 'start': start, 'end': end, 'rows': len(records),
            'unique_ids': len(seen), 'sample_cap_reached': len(records) == 100,
            'coverage_complete': False, 'reason_counts': dict(reasons),
            'field_presence_counts': dict(fields), 'version_notes': dict(notes),
            'conditional_temporal_candidates': candidates,
            'candidates_observed_before_next_4h_boundary': before_boundary,
            'delay_seconds': {'count': len(lags), 'min': min(lags) if lags else None,
                              'median_lower': lags[(len(lags)-1)//2] if lags else None,
                              'max': max(lags) if lags else None}}


def main():
    raise SystemExit(
        'Arctic collection suspended pending source-specific authorization and '
        'version evidence. See social_access_review_v9_2.json. No network request made.'
    )


def _historical_pilot_main_not_authorized_to_run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='arctic_raw_pilot_v9_1')
    args = parser.parse_args()
    if not args.run or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for c in args.run):
        parser.error('Use lowercase letters, digits, underscore or hyphen for run')
    out = ROOT / 'paper/input/results/llm/v9' / args.run
    raw = ROOT / 'runtime/external/social_v9' / args.run
    refs = ROOT / 'paper/input/references/source_artifacts/social_corpus_v9' / args.run
    if any(path.exists() for path in (out, raw, refs)):
        parser.error('Run already exists: preserve it and choose a new run name')
    declaration = {'scope': 'bounded_schema_provenance_pilot_not_prediction',
                   'created_at': datetime.now(timezone.utc).isoformat(),
                   'windows': WINDOWS, 'kinds': ['posts', 'comments'], 'subreddit': 'Bitcoin',
                   'sort': 'asc', 'limit_per_request': 100, 'requests': 6,
                   'pagination': False, 'max_bytes_per_response': 4_000_000,
                   'engagement_selection': False, 'outcomes_accessed': False,
                   'sampling_note': 'Earliest bounded records, not representative or complete.',
                   'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save(out / 'predeclared.json', json.dumps(declaration, indent=2).encode())
    sources, summaries, failures = [], [], []
    base = f'https://raw.githubusercontent.com/ArthurHeitmann/arctic_shift/{REVISION}'
    for name in ('README.md', 'api/README.md', 'file_content_explanations.md'):
        _, info = fetch(base + '/' + name, refs / name.replace('/', '_'))
        sources.append(info)
    for start, end in WINDOWS:
        for kind in ('posts', 'comments'):
            url = 'https://arctic-shift.photon-reddit.com/api/' + kind + '/search?' + urlencode(
                {'subreddit': 'Bitcoin', 'after': start + 'T00:00:00Z',
                 'before': end + 'T00:00:00Z', 'sort': 'asc', 'limit': 100})
            name = start + '_' + kind + '.json'
            try:
                # Full response is local quarantine only: field projection omits version metadata.
                data, info = fetch(url, raw / name)
                sources.append(info)
                rows = json.loads(data)['data']
                if not isinstance(rows, list) or len(rows) > 100 or any(not isinstance(r, dict) for r in rows):
                    raise ValueError('Unexpected API schema or cap')
                projected = [{k: v for k, v in row.items() if k in KEEP} for row in rows]
                save(raw / ('projected_' + name), json.dumps(projected, ensure_ascii=False).encode())
                summaries.append(audit(projected, kind, start, end))
            except Exception as error:
                failures.append({'url': url, 'error_type': type(error).__name__, 'message': str(error)})
                break
            time.sleep(1)
        if failures:
            break
    report = {'status': 'PILOT_INCOMPLETE' if failures else 'PILOT_AUDITED_NOT_ADMITTED',
              'model_run': False, 'outcomes_accessed': False, 'technical_features_used': False,
              'sources': sources, 'samples': summaries, 'failures': failures,
              'rows': sum(x['rows'] for x in summaries),
              'conditional_temporal_candidates': sum(x['conditional_temporal_candidates'] for x in summaries),
              'admitted_model_inputs': 0,
              'limitations': ['Conditional record checks are not complete PIT certification.',
                              'Exclusion by later edits/deletions is diagnostic, not causal sample selection.',
                              'Public API/dump documentation is not a verified content usage license.',
                              'No full-period coverage, deletion bias or model contamination audit.',
                              'API snapshot is retrieved now, not an independently verified historical dump.',
                              'Next 4h boundary is a latency diagnostic, not a selected predictive target.'],
              'next_required': ['Resolve usage basis with thesis supervisor/source owner.',
                                'Validate pinned monthly dump and API version semantics.',
                                'Audit complete chronological development coverage before model freeze.']}
    save(out / 'audit.json', json.dumps(report, indent=2).encode())
    print(json.dumps({k: report[k] for k in ('status', 'rows', 'conditional_temporal_candidates', 'admitted_model_inputs')}))
    print(str(out / 'audit.json'))


if __name__ == '__main__':
    main()
