"""Compare current extracted text with independent near-release web archives."""
import hashlib
import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from urllib.parse import urlencode

from audit_social_intake_v9 import ROOT, fetch, save
from build_open_fomc_pilot_v10 import extract

CDX = 'https://web.archive.org/cdx/search/cdx?'
ARCHIVE = 'https://web.archive.org/web/{timestamp}id_/{url}'


def compact(value):
    return value.astimezone(timezone.utc).strftime('%Y%m%d%H%M%S')


def choose_capture(rows, release):
    candidates = []
    for row in rows:
        try:
            stamp = datetime.strptime(row['timestamp'], '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            continue
        distance = abs((stamp - release).total_seconds())
        if distance <= 24 * 3600:
            candidates.append((distance, stamp, row))
    return min(candidates, default=(None, None, None), key=lambda x: x[0])[2]


def decode_archive_payload(data):
    return gzip.decompress(data) if data.startswith(b'\x1f\x8b') else data


def main():
    corpus_path = ROOT / 'paper/input/results/llm/v10/open_fomc_pilot/corpus.json'
    out = ROOT / 'paper/input/results/llm/v10/fomc_archived_version_audit_v10_1.json'
    refs = ROOT / 'paper/input/references/source_artifacts/open_fomc_v10/wayback_near_release_v10_1'
    if out.exists() or refs.exists():
        raise SystemExit('Audit exists; preserve evidence and version the next run.')
    corpus = json.loads(corpus_path.read_text(encoding='utf-8'))
    results = []
    for record in corpus:
        release = datetime.fromisoformat(record['published_at_claimed_utc'])
        query = urlencode({'url': record['source_url'], 'output': 'json',
                           'filter': ['statuscode:200', 'mimetype:text/html'],
                           'fl': 'timestamp,original,digest,statuscode',
                           'from': compact(release - timedelta(hours=24)),
                           'to': compact(release + timedelta(hours=24)), 'limit': 20}, doseq=True)
        item = {'id': record['id'], 'release_utc': record['published_at_claimed_utc'],
                'source_url': record['source_url'], 'current_text_sha256': record['text_sha256']}
        try:
            cdx_data, cdx_info = fetch(CDX + query, refs / (record['id'] + '_cdx.json'), limit=1_000_000)
            table = json.loads(cdx_data)
            if not table or len(table) < 2:
                item.update({'status': 'NO_NEAR_RELEASE_CAPTURE', 'cdx_source': cdx_info})
            else:
                rows = [dict(zip(table[0], row)) for row in table[1:]]
                selected = choose_capture(rows, release)
                if selected is None:
                    item.update({'status': 'NO_NEAR_RELEASE_CAPTURE', 'cdx_source': cdx_info})
                else:
                    stamp = selected['timestamp']
                    archive_url = ARCHIVE.format(timestamp=stamp, url=record['source_url'])
                    archived_data, archive_info = fetch(archive_url, refs / (record['id'] + '_' + stamp + '.html'))
                    archived = extract(decode_archive_payload(archived_data))
                    capture = datetime.strptime(stamp, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
                    item.update({'status': ('TEXT_MATCH' if archived['text_sha256'] == record['text_sha256']
                                             else 'TEXT_MISMATCH'),
                                 'capture_timestamp_utc': capture.isoformat(),
                                 'capture_offset_seconds': int((capture - release).total_seconds()),
                                 'archived_text_sha256': archived['text_sha256'],
                                 'wayback_digest': selected.get('digest'),
                                 'cdx_source': cdx_info, 'archive_source': archive_info})
        except Exception as error:
            item.update({'status': 'ARCHIVE_CHECK_ERROR', 'error_type': type(error).__name__,
                         'error': str(error)})
        results.append(item)
        time.sleep(0.5)
    counts = {}
    for row in results:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    report = {'status': 'ARCHIVED_VERSION_AUDITED_NOT_AVAILABILITY_CERTIFIED',
              'corpus_sha256': hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
              'records': len(results), 'status_counts': counts, 'results': results,
              'interpretation': [
                  'TEXT_MATCH verifies equality with a near-release archived representation only.',
                  'Wayback capture time does not prove the Board page was publicly available to a trader then.',
                  'NO_NEAR_RELEASE_CAPTURE is missing evidence, not a mismatch.',
                  'This audit does not access prices, run a model, or establish predictive value.']}
    save(out, json.dumps(report, indent=2).encode())
    print(json.dumps({'status': report['status'], 'records': len(results), 'status_counts': counts}))


if __name__ == '__main__':
    main()
