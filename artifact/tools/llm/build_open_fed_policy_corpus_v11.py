"""Build a resumable, outcome-blind official policy-release corpus."""
import hashlib
from html.parser import HTMLParser
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import time
import zipfile

from audit_social_intake_v9 import ROOT, fetch, save
from build_open_fomc_pilot_v10 import ReleaseParser, timestamp

BASE = 'https://www.federalreserve.gov'
YEARS = (2022, 2023, 2024)
CATEGORIES = ('Monetary Policy', 'Banking and Consumer Regulatory Policy')
EXPECTED_LINKS = {2022: 62, 2023: 56, 2024: 56}
URL_PATTERN = re.compile(r'/newsevents/pressreleases/[a-z]+\d{8}[a-z]\.htm$')


class ArchiveParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.current = None
        self.capture = None
        self.parts = []
        self.rows = []

    def finish_row(self):
        self.finish_capture()
        if self.current and {'path', 'listed_title', 'listed_date', 'category'} <= self.current.keys():
            self.rows.append(self.current)
        self.current = None

    def finish_capture(self):
        if self.capture and self.current is not None:
            self.current[self.capture] = ' '.join(''.join(self.parts).split())
        self.capture, self.parts = None, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get('class', '').split())
        if tag == 'div':
            self.depth += 1
        if tag == 'time':
            self.finish_row()
            self.current = {}
            self.capture = 'listed_date'
        if self.current is None:
            return
        if tag == 'time':
            return
        elif tag == 'p' and 'eventlist__press' in classes:
            self.capture = 'category'
        elif tag == 'a' and URL_PATTERN.fullmatch(attrs.get('href', '')):
            self.current['path'] = attrs['href']
            self.capture = 'listed_title'

    def handle_endtag(self, tag):
        if tag in ('time', 'p', 'a'):
            self.finish_capture()
        if tag == 'div':
            self.depth -= 1

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)


def parse_archive(data):
    parser = ArchiveParser()
    parser.feed(data.decode('utf-8-sig'))
    parser.finish_row()
    return parser.rows


def parse_release(data, listing):
    parser = ReleaseParser()
    parser.feed(data.decode('utf-8-sig'))
    parser.finish()
    reasons = []
    title = parser.values.get('title')
    if title != listing['listed_title']:
        reasons.append('title_mismatch')
    try:
        release_utc = timestamp(parser.values.get('date', ''), parser.values.get('release', ''))
    except ValueError:
        release_utc = None
        reasons.append('release_timestamp_missing_or_ambiguous')
    paragraphs = [p for p in parser.paragraphs if not p.startswith('For media inquiries')]
    body = '\n\n'.join(paragraphs)
    text = (title + '\n\n' + body) if title and body else ''
    if len(body) < 200:
        reasons.append('body_too_short')
    if re.search(r'(?i)\bcopyright\b|©', body):
        reasons.append('article_body_contains_rights_marker')
    return {'title': title, 'body': body, 'text': text, 'published_at_claimed_utc': release_utc,
            'release_clock_original': parser.values.get('release'),
            'last_update_label': parser.values.get('last_update'),
            'text_sha256': hashlib.sha256(text.encode()).hexdigest() if text else None,
            'historical_first_version_verified': False,
            'admission_reasons': sorted(set(reasons))}


def cached_fetch(url, path, limit=4_000_000):
    meta_path = path.with_suffix(path.suffix + '.source.json')
    if path.exists() and meta_path.exists():
        data = path.read_bytes()
        info = json.loads(meta_path.read_text(encoding='utf-8'))
        if info.get('url') != url or hashlib.sha256(data).hexdigest() != info.get('sha256'):
            raise ValueError('Cached source identity/hash mismatch: ' + str(path))
        info = dict(info, reused_from_cache=True)
        return data, info
    if path.exists() or meta_path.exists():
        raise ValueError('Incomplete cache pair: ' + str(path))
    data, info = fetch(url, path, limit=limit)
    save(meta_path, json.dumps(info, indent=2).encode())
    return data, info


def main():
    out = ROOT / 'paper/input/results/llm/v11/open_fed_policy_corpus_v11_0_1'
    raw = ROOT / 'runtime/external/open_fed_policy_v11_0_1'
    refs = ROOT / 'paper/input/references/source_artifacts/open_fed_policy_v11_0_1'
    out.mkdir(parents=True, exist_ok=True)
    declaration_path = out / 'predeclared.json'
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    declaration = {'version': 'v11.0.1', 'years': YEARS, 'categories': CATEGORIES,
                   'deviation_from': 'v11.0 stopped before release downloads because archive row parser returned 1/62 links',
                   'expected_archive_links': EXPECTED_LINKS,
                   'schema_rules': ['official archive membership', 'exact category',
                                    'explicit EST/EDT release timestamp', 'body >= 200 chars',
                                    'no article-body rights marker'],
                   'selection_uses_outcomes': False, 'market_data_accessed': False,
                   'model_run': False, 'script_sha256': script_hash}
    if declaration_path.exists():
        old = json.loads(declaration_path.read_text(encoding='utf-8'))
        if old != declaration:
            raise SystemExit('Predeclaration differs; preserve run and version changes.')
    else:
        save(declaration_path, json.dumps(declaration, indent=2).encode())
    policy_data, policy_info = cached_fetch(BASE + '/disclaimer.htm', refs / 'policy.html')
    if b'public domain' not in policy_data:
        raise ValueError('Public-domain notice not found; manual review required')
    listings, sources = [], [policy_info]
    for year in YEARS:
        data, info = cached_fetch(BASE + f'/newsevents/pressreleases/{year}-press.htm',
                                  refs / f'{year}-press.html')
        sources.append(info)
        selected = [row for row in parse_archive(data) if row['category'] in CATEGORIES]
        if len(selected) != EXPECTED_LINKS[year]:
            raise ValueError(f'Archive count changed for {year}: {len(selected)}')
        listings.extend(selected)
    if len({row['path'] for row in listings}) != sum(EXPECTED_LINKS.values()):
        raise ValueError('Duplicate or missing archive URLs')
    admitted, excluded = [], []
    for index, listing in enumerate(sorted(listings, key=lambda row: (row['listed_date'], row['path']))):
        url = BASE + listing['path']
        data, info = cached_fetch(url, raw / Path(listing['path']).name)
        record = parse_release(data, listing)
        record.update(listing)
        record.update({'id': Path(listing['path']).stem, 'source_url': url,
                       'source_sha256': info['sha256'], 'source_fetched_at': info['fetched_at'],
                       'attribution': 'Board of Governors of the Federal Reserve System',
                       'rights_basis': BASE + '/disclaimer.htm'})
        (admitted if not record['admission_reasons'] else excluded).append(record)
        if not info.get('reused_from_cache'):
            time.sleep(0.35)
        if (index + 1) % 10 == 0:
            checkpoint = {'processed': index + 1, 'total': len(listings),
                          'admitted': len(admitted), 'excluded': len(excluded),
                          'updated_at': datetime.now(timezone.utc).isoformat()}
            save(out / 'checkpoint.json', json.dumps(checkpoint, indent=2).encode())
    admitted.sort(key=lambda row: (row['published_at_claimed_utc'], row['id']))
    excluded.sort(key=lambda row: row['id'])
    save(out / 'corpus.json', json.dumps(admitted, ensure_ascii=False, indent=2).encode())
    save(out / 'excluded.json', json.dumps(excluded, ensure_ascii=False, indent=2).encode())
    per_year = {str(year): sum(row['published_at_claimed_utc'].startswith(str(year)) for row in admitted)
                for year in YEARS}
    reason_counts = {}
    for row in excluded:
        for reason in row['admission_reasons']:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    duplicate_timestamps = {}
    for row in admitted:
        duplicate_timestamps.setdefault(row['published_at_claimed_utc'], []).append(row['id'])
    duplicate_timestamps = {key: value for key, value in duplicate_timestamps.items() if len(value) > 1}
    notice = '''# Federal Reserve policy-release corpus v11\n\nBoard-authored information is public domain unless otherwise indicated; cite the\nBoard. See https://www.federalreserve.gov/disclaimer.htm. This derivative contains\ntext only and excludes seals, logos, images and linked third-party works.\n\nThe package is an outcome-blind corpus artifact, not an official Board product,\nnot a historical-availability certification and not a predictive result. IDs,\ntimestamps and categories are audit metadata; only text may enter a future LLM.\nPages sharing one release timestamp must be grouped as one event before evaluation.\n'''
    save(out / 'NOTICE.md', notice.encode())
    verifier = '''import hashlib, json\nfrom pathlib import Path\nroot=Path(__file__).resolve().parent\nm=json.loads((root/'manifest.json').read_text(encoding='utf-8'))\nfor name,digest in m['files'].items():\n    if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:\n        raise SystemExit('Hash mismatch: '+name)\nfor row in json.loads((root/'corpus.json').read_text(encoding='utf-8')):\n    if hashlib.sha256(row['text'].encode()).hexdigest()!=row['text_sha256']:\n        raise SystemExit('Text mismatch: '+row['id'])\nprint('PASS: package and text hashes verified; not predictive or PIT certification')\n'''
    save(out / 'verify.py', verifier.encode())
    save(out / 'build_open_fed_policy_corpus_v11.py', Path(__file__).read_bytes())
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in out.iterdir() if p.is_file() and p.name not in ('checkpoint.json', 'manifest.json')
             and not p.name.endswith('.zip')}
    manifest = {'status': 'REPRODUCIBLE_EXPANDED_TEXT_CORPUS_NOT_PREDICTIVE_FREEZE',
                'archive_links': len(listings), 'admitted_documents': len(admitted),
                'excluded_documents': len(excluded), 'per_year': per_year,
                'exclusion_reason_counts': reason_counts,
                'same_timestamp_groups': len(duplicate_timestamps),
                'documents_in_same_timestamp_groups': sum(map(len, duplicate_timestamps.values())),
                'files': files, 'sources': sources,
                'market_data_accessed': False, 'model_run': False,
                'historical_first_version_verified': False,
                'next_gate': ['Archive-version audit', 'Event-level grouping and sample-size assessment',
                              'Freeze model/prompt/split/target before joining outcomes']}
    save(out / 'manifest.json', json.dumps(manifest, indent=2).encode())
    package = out / 'reviewer_text_corpus_v11.zip'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted([*files, 'manifest.json']):
            archive.write(out / name, name)
    print(json.dumps({key: manifest[key] for key in ('status', 'archive_links', 'admitted_documents',
                                                     'excluded_documents', 'per_year',
                                                     'same_timestamp_groups')}))


if __name__ == '__main__':
    main()
