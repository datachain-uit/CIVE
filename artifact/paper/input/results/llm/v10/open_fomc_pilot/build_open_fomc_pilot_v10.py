"""Build a bounded, redistributable text pilot; no model or market data."""
import hashlib
from html.parser import HTMLParser
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import time
import zipfile
from audit_social_intake_v9 import ROOT, fetch, save

BASE = 'https://www.federalreserve.gov'
YEARS = (2022, 2023, 2024)


class ReleaseParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.paragraphs, self.values = [], [], {}
        self.depth = 0
        self.body = None
        self.capture = None
        self.parts = []

    def finish(self):
        if self.capture:
            text = ' '.join(''.join(self.parts).split())
            if self.capture == 'body':
                if text and not text.startswith('For media inquiries'):
                    self.paragraphs.append(text)
            else:
                self.values[self.capture] = text
        self.capture, self.parts = None, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get('class', '').split())
        if tag in ('p', 'ul', 'h3', 'div'):
            self.finish()
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])
        if tag == 'div':
            self.depth += 1
            if classes == {'col-xs-12', 'col-sm-8', 'col-md-8'}:
                self.body = self.depth
            if attrs.get('id') == 'lastUpdate':
                self.capture = 'last_update'
        if tag == 'p':
            if 'article__time' in classes:
                self.capture = 'date'
            elif 'releaseTime' in classes:
                self.capture = 'release'
            elif self.body is not None:
                self.capture = 'body'
        if tag == 'h3' and 'title' in classes:
            self.capture = 'title'

    def handle_endtag(self, tag):
        if tag in ('p', 'h3', 'div'):
            self.finish()
        if tag == 'div':
            if self.depth == self.body:
                self.body = None
            self.depth -= 1

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)


def timestamp(date, release):
    match = re.fullmatch(r'For release at (\d{1,2}):(\d{2}) (a\.m\.|p\.m\.) (EST|EDT)', release)
    if not match:
        raise ValueError('Ambiguous release clock: ' + release)
    hour, minute, meridian, zone = match.groups()
    if not 1 <= int(hour) <= 12 or not 0 <= int(minute) <= 59:
        raise ValueError('Invalid clock')
    hour = int(hour) % 12 + (12 if meridian == 'p.m.' else 0)
    value = datetime.strptime(date, '%B %d, %Y').replace(
        hour=hour, minute=int(minute), tzinfo=timezone(timedelta(hours=-5 if zone == 'EST' else -4)))
    return value.astimezone(timezone.utc).isoformat()


def extract(data):
    parser = ReleaseParser()
    parser.feed(data.decode('utf-8-sig'))
    parser.finish()
    if parser.values.get('title') != 'Federal Reserve issues FOMC statement':
        raise ValueError('Unexpected release type')
    if len(parser.paragraphs) < 3 or not any('Voting for' in p for p in parser.paragraphs):
        raise ValueError('Incomplete statement extraction')
    text = '\n\n'.join(parser.paragraphs)
    return {'text': text, 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'published_at_claimed_utc': timestamp(parser.values['date'], parser.values['release']),
            'release_clock_original': parser.values['release'],
            'last_update_label': parser.values.get('last_update'),
            'historical_first_version_verified': False}


def main():
    out = ROOT / 'paper/input/results/llm/v10/open_fomc_pilot'
    raw = ROOT / 'runtime/external/open_fomc_v10'
    refs = ROOT / 'paper/input/references/source_artifacts/open_fomc_v10'
    if any(p.exists() for p in (out, raw, refs)):
        raise SystemExit('Output exists; preserve snapshots and version the next build.')
    declaration = {'years': YEARS, 'selection': 'all monetaryYYYYMMDDa.htm statement links in official calendar',
                   'max_statements': 40, 'model_run': False, 'market_data_accessed': False,
                   'created_at': datetime.now(timezone.utc).isoformat(),
                   'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save(out / 'predeclared.json', json.dumps(declaration, indent=2).encode())
    sources = []
    for name, url in [('policy', BASE + '/disclaimer.htm'), ('calendar', BASE + '/monetarypolicy/fomccalendars.htm')]:
        data, info = fetch(url, refs / (name + '.html'))
        sources.append(info)
        if name == 'calendar':
            calendar = data
        elif b'public domain' not in data:
            raise ValueError('Policy changed: manual review required')
    parser = ReleaseParser()
    parser.feed(calendar.decode('utf-8-sig'))
    paths = sorted({p for p in parser.links if re.fullmatch(r'/newsevents/pressreleases/monetary(?:2022|2023|2024)\d{4}a.htm', p)})
    if not paths or len(paths) > 40 or any(not any(f'monetary{y}' in p for p in paths) for y in YEARS):
        raise ValueError('Calendar coverage absent or exceeds declared bound')
    corpus = []
    for path in paths:
        data, info = fetch(BASE + path, raw / Path(path).name)
        sources.append(info)
        record = extract(data)
        record.update({'id': Path(path).stem, 'source_url': BASE + path,
                       'source_sha256': info['sha256'], 'fetched_at': info['fetched_at'],
                       'attribution': 'Board of Governors of the Federal Reserve System',
                       'rights_basis': BASE + '/disclaimer.htm'})
        corpus.append(record)
        time.sleep(0.5)
    save(out / 'corpus.json', json.dumps(corpus, ensure_ascii=False, indent=2).encode())
    notice = '''# Reproducible FOMC text pilot

Source: Board of Governors of the Federal Reserve System, federalreserve.gov.
Board-authored information is public domain unless otherwise indicated; cite the
Board. See https://www.federalreserve.gov/disclaimer.htm. This package contains
extracted statement text only, no seals, logos, photos or linked third-party works.
Extraction removes navigation/contact details and normalizes whitespace. This is
an independent research derivative, not an official Board product or endorsement.

Run `python verify.py` offline to verify every included file and statement hash.
No third-party Python packages are needed. Build script also requires the supplied
audit_social_intake_v9.py helper; rebuilding from live URLs can yield new versions.
The supplied text snapshot, not a new download, defines this pilot's exact input.

Release clocks are official page claims converted from explicit EST/EDT to UTC.
Fetching and hashing today does NOT prove the original release-time text version.
No model results, market labels or sealed-holdout data are included. A small event
corpus is not proof of predictive power. Corpus data is not technical features:
only text may enter a future LLM; timestamps/IDs are audit metadata only.
'''
    save(out / 'NOTICE.md', notice.encode())
    verifier = '''import hashlib, json
from pathlib import Path
root = Path(__file__).resolve().parent
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
for name, expected in manifest["files"].items():
    if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
        raise SystemExit("Hash mismatch: " + name)
for row in json.loads((root / "corpus.json").read_text(encoding="utf-8")):
    if hashlib.sha256(row["text"].encode()).hexdigest() != row["text_sha256"]:
        raise SystemExit("Text mismatch: " + row["id"])
print("PASS: packaged files and text hashes verified; not historical PIT certification")
'''
    save(out / 'verify.py', verifier.encode())
    save(out / 'build_open_fomc_pilot_v10.py', Path(__file__).read_bytes())
    save(out / 'audit_social_intake_v9.py', Path(__file__).with_name('audit_social_intake_v9.py').read_bytes())
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
    manifest = {'status': 'REPRODUCIBLE_TEXT_PILOT_NOT_PREDICTIVE_ADMISSION',
                'statements': len(corpus), 'per_year': {str(y): sum(r['published_at_claimed_utc'].startswith(str(y)) for r in corpus) for y in YEARS},
                'files': files, 'sources': sources,
                'historical_first_version_verified': False, 'model_run': False,
                'technical_features_used': False, 'market_data_accessed': False,
                'remaining': ['Independent original-version checks', 'Power/coverage assessment',
                              'Frozen model protocol and model/prompt/environment artifacts',
                              'Separate market-label redistribution rights before any full experiment release']}
    save(out / 'manifest.json', json.dumps(manifest, indent=2).encode())
    with zipfile.ZipFile(out / 'reviewer_text_pilot.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted([*files, 'manifest.json']):
            archive.write(out / name, name)
    print(json.dumps({'statements': len(corpus), 'per_year': manifest['per_year'], 'status': manifest['status']}))


if __name__ == '__main__':
    main()
