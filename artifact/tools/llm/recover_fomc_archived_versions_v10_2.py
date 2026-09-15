"""Recover gzip-encoded v10.1 snapshots offline; no network access."""
import hashlib
import json
from datetime import datetime, timezone

from audit_social_intake_v9 import ROOT, save
from audit_fomc_archived_versions_v10 import choose_capture, decode_archive_payload
from build_open_fomc_pilot_v10 import extract


def main():
    prior_path = ROOT / 'paper/input/results/llm/v10/fomc_archived_version_audit_v10_1.json'
    out = ROOT / 'paper/input/results/llm/v10/fomc_archived_version_audit_v10_2.json'
    refs = ROOT / 'paper/input/references/source_artifacts/open_fomc_v10/wayback_near_release_v10_1'
    if out.exists():
        raise SystemExit('Recovery exists; preserve it.')
    prior = json.loads(prior_path.read_text(encoding='utf-8'))
    results = []
    for old in prior['results']:
        row = dict(old)
        if old['status'] == 'ARCHIVE_CHECK_ERROR' and 'decode byte 0x8b' in old.get('error', ''):
            cdx_path = refs / (old['id'] + '_cdx.json')
            table = json.loads(cdx_path.read_bytes())
            rows = [dict(zip(table[0], values)) for values in table[1:]]
            release = datetime.fromisoformat(old['release_utc'])
            selected = choose_capture(rows, release)
            archive_path = refs / f"{old['id']}_{selected['timestamp']}.html"
            archived = extract(decode_archive_payload(archive_path.read_bytes()))
            capture = datetime.strptime(selected['timestamp'], '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
            row = {k: v for k, v in row.items() if k not in ('error', 'error_type')}
            row.update({'status': ('TEXT_MATCH' if archived['text_sha256'] == old['current_text_sha256']
                                   else 'TEXT_MISMATCH'),
                        'capture_timestamp_utc': capture.isoformat(),
                        'capture_offset_seconds': int((capture - release).total_seconds()),
                        'archived_text_sha256': archived['text_sha256'],
                        'wayback_digest': selected.get('digest'),
                        'local_archive_path': str(archive_path.relative_to(ROOT)),
                        'local_archive_sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                        'recovery': 'gzip payload decoded offline from v10.1 source artifact'})
        results.append(row)
    counts = {}
    for row in results:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    report = {'status': 'ARCHIVED_VERSION_RECOVERED_NOT_AVAILABILITY_CERTIFIED',
              'derived_from': str(prior_path.relative_to(ROOT)),
              'derived_from_sha256': hashlib.sha256(prior_path.read_bytes()).hexdigest(),
              'network_access': False, 'records': len(results), 'status_counts': counts,
              'results': results,
              'interpretation': prior['interpretation'] + [
                  'Recovered rows use the exact compressed response bytes already saved by v10.1.']}
    save(out, json.dumps(report, indent=2).encode())
    print(json.dumps({'status': report['status'], 'status_counts': counts}))


if __name__ == '__main__':
    main()
