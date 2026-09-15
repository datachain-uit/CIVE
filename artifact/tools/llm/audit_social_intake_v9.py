"""Bounded source intake; never joins market outcomes or produces model inputs."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
REFS = ROOT / 'paper/input/references/source_artifacts/social_corpus_v9'
OUT = ROOT / 'paper/input/results/llm/v9'
HF = 'https://huggingface.co'
AUTHOR_REPO = 'CorsiDanilo/Leveraging-LLMs-for-Informed-Bitcoin-Trading-Decisions'
AUTHOR_SHA = 'b8d0ead2c6d6cace48fa9159a765350f8c88aa14'


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_bytes(data)
    temp.replace(path)


def fetch(url, path, limit=4_000_000, prefix=False):
    headers = {'User-Agent': 'Thesis-social-intake/9.0'}
    if prefix:
        headers['Range'] = f'bytes=0-{limit - 1}'
    with urlopen(Request(url, headers=headers), timeout=45) as response:
        data = response.read(limit if prefix else limit + 1)
        if len(data) > limit:
            raise ValueError('Document exceeds intake limit')
        info = {'url': url, 'http_status': response.status,
                'content_range': response.headers.get('Content-Range'),
                'partial_sample': prefix, 'bytes': len(data),
                'sha256': hashlib.sha256(data).hexdigest(),
                'path': str(path.relative_to(ROOT)),
                'fetched_at': datetime.now(timezone.utc).isoformat()}
    save(path, data)
    return data, info


def record_reasons(record, cutoff):
    """Conservative prospective schema gate, not a corpus-level PIT proof."""
    reasons = []
    times = {}
    for key in ('created_at', 'observed_at'):
        try:
            value = datetime.fromisoformat(record[key].replace('Z', '+00:00'))
            if value.tzinfo is None:
                raise ValueError('Timezone missing')
            times[key] = value
        except (KeyError, TypeError, AttributeError, ValueError):
            reasons.append(key + '_missing_or_ambiguous')
    if cutoff.tzinfo is None:
        raise ValueError('Cutoff must be timezone-aware')
    if len(times) == 2:
        if times['observed_at'] < times['created_at']:
            reasons.append('observation_before_creation')
        if max(times.values()) > cutoff:
            reasons.append('not_available_at_cutoff')
    if record.get('text_version_verified') is not True:
        reasons.append('text_version_unverified')
    if record.get('selection_asof_verified') is not True:
        reasons.append('selection_asof_unverified')
    if record.get('usage_reviewed') is not True:
        reasons.append('usage_unreviewed')
    if not isinstance(record.get('text'), str) or record['text'].strip() in ('', '[deleted]', '[removed]'):
        reasons.append('text_unavailable')
    return reasons


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-name', default='social_source_audit_v9.json')
    args = parser.parse_args()
    if Path(args.output_name).name != args.output_name:
        parser.error('output-name must be a filename')
    output = OUT / args.output_name
    if output.exists():
        parser.error('Audit exists; use a new output-name and preserve prior evidence')
    sources = []
    snapshot_dir = REFS / output.stem
    if snapshot_dir.exists():
        parser.error('Snapshot exists; use a new output-name')

    def get(url, name, **kwargs):
        data, info = fetch(url, snapshot_dir / name, **kwargs)
        sources.append(info)
        return data

    tweet_id = 'Joi123/bitcoin-tweets-2023'
    meta = json.loads(get(f'{HF}/api/datasets/{tweet_id}', 'tweet_metadata.json'))
    revision = meta['sha']
    get(f'{HF}/datasets/{tweet_id}/raw/{revision}/README.md', 'tweet_README.md')
    get(f'{HF}/datasets/{tweet_id}/discussions/1', 'tweet_description.html')
    get(f'{HF}/api/datasets/{tweet_id}/tree/{revision}?recursive=true', 'tweet_tree.json')
    sample = get(f'{HF}/datasets/{tweet_id}/resolve/{revision}/tweets.csv',
                 'tweet_prefix.bin', prefix=True, limit=1_048_576)
    try:
        sample.decode('utf-8')
        encoding_status = 'utf8_prefix_decodes_only_not_full_file_validation'
    except UnicodeDecodeError as error:
        encoding_status = f'utf8_prefix_error_at_byte_{error.start}'
    author_id = 'danilocorsi/LLMs-Sentiment-Augmented-Bitcoin-Dataset'
    author_meta = json.loads(get(f'{HF}/api/datasets/{author_id}', 'reddit_metadata.json'))
    get(f'{HF}/datasets/{author_id}/raw/{author_meta["sha"]}/README.md', 'reddit_README.md')
    github = f'https://raw.githubusercontent.com/{AUTHOR_REPO}/{AUTHOR_SHA}'
    converter = get(github + '/data_mining/utils/reddit_to_csv.py', 'upstream_reddit_to_csv.py').decode('utf-8')
    notebook = json.loads(get(github + '/data_mining/reddit.ipynb', 'upstream_reddit.ipynb'))
    cells = [(i, ''.join(cell.get('source', []))) for i, cell in enumerate(notebook['cells'])
             if cell.get('cell_type') == 'code']
    matches = {term: [i for i, code in cells if term in code]
               for term in ('MIN_COMMENTS = 10', 'MIN_SCORE = 10', "comment[2].startswith(curr_timestamp)")}
    arctic_meta = json.loads(get('https://api.github.com/repos/ArthurHeitmann/arctic_shift/commits/master', 'arctic_commit.json'))
    get('https://raw.githubusercontent.com/ArthurHeitmann/arctic_shift/' + arctic_meta['sha'] +
        '/file_content_explanations.md', 'arctic_collection.md')
    report = {
        'version': 'v9.0-intake', 'status': 'DATA_NOT_ADMITTED',
        'scope': 'source_code_and_metadata_audit_plus_bounded_tweet_prefix',
        'model_run': False, 'outcomes_opened': False, 'technical_features_used': False,
        'sources': sources,
        'candidates': [
            {'id': author_id, 'revision': author_meta['sha'], 'decision': 'REJECT_AS_PIT_INPUT',
             'evidence': {'notebook_cell_indices_zero_based': matches,
                          'local_timezone_conversion': "dt.fromtimestamp(int(obj['created_utc']))" in converter},
             'reasons': ['Selection uses archive score/comment totals without as-of snapshots.',
                         'Local timezone conversion drops timezone and seconds.',
                         'Dropping score columns cannot reverse upstream selection.',
                         'Raw merged table also contains future-price targets: prohibit direct model ingestion.']},
            {'id': tweet_id, 'revision': revision, 'decision': 'QUARANTINE',
             'encoding_check': encoding_status,
             'dataset_card_license': meta.get('cardData', {}).get('license'),
             'reasons': ['Uploader real-time and latency description is not a per-record receipt log.',
                         'No verified usage permission or complete schema/encoding audit.',
                         'Prefix is not representative; no corpus counts or coverage inferred.']},
            {'id': 'ArthurHeitmann/arctic_shift', 'revision': arctic_meta['sha'],
             'decision': 'NEXT_RAW_ARCHIVE_CANDIDATE',
             'reasons': ['Preserves retrieved_on in documented newer dumps.',
                         'Second retrieval can restore text: gate text versions and restoration metadata.',
                         'Need bounded raw pilot, coverage and usage review before admission.']}],
        'next_gate': ['Verify usage basis and original raw snapshot.',
                      'Preserve UTC creation AND observation time; reject ambiguous timestamps.',
                      'No hindsight engagement selection or future edited/restored text.',
                      'Deduplicate IDs with version-aware as-of selection before temporal split.',
                      'Freeze social-only protocol before joining any market labels.']}
    save(output, json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
    print(json.dumps({'output': str(output), 'status': report['status'],
                      'source_artifacts': len(sources), 'tweet_encoding': encoding_status}))


if __name__ == '__main__':
    main()
