"""Create reviewer provenance summary and an outcome-free power diagnostic."""
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
import zipfile

from audit_social_intake_v9 import ROOT, save


def approximate_correlation_mde(n, alpha=0.05, power=0.80):
    if n <= 3 or not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError('Invalid planning inputs')
    z = NormalDist()
    return math.tanh((z.inv_cdf(1 - alpha / 2) + z.inv_cdf(power)) / math.sqrt(n - 3))


def main():
    result_dir = ROOT / 'paper/input/results/llm/v10'
    audit_path = result_dir / 'fomc_archived_version_audit_v10_2.json'
    corpus_path = result_dir / 'open_fomc_pilot/corpus.json'
    package_path = result_dir / 'open_fomc_pilot/reviewer_text_pilot.zip'
    out = result_dir / 'fomc_provenance_summary_v10.json'
    archive_out = result_dir / 'fomc_provenance_addendum_v10.zip'
    if out.exists() or archive_out.exists():
        raise SystemExit('Addendum exists; preserve it and version any replacement.')
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    corpus = json.loads(corpus_path.read_text(encoding='utf-8'))
    counts = audit['status_counts']
    n = len(corpus)
    summary = {
        'status': 'TEXT_REPRODUCIBLE_PILOT_MODEL_NOT_AUTHORIZED_BY_POWER_GATE',
        'records': n,
        'near_release_text_matches': counts.get('TEXT_MATCH', 0),
        'near_release_text_mismatches': counts.get('TEXT_MISMATCH', 0),
        'archive_check_errors': counts.get('ARCHIVE_CHECK_ERROR', 0),
        'historical_availability_certified': False,
        'model_run': False, 'market_outcomes_accessed': False,
        'approximate_two_sided_correlation_mde': approximate_correlation_mde(n),
        'planning_assumptions': {'alpha': 0.05, 'power': 0.80,
                                 'formula': 'tanh((z_(1-alpha/2)+z_power)/sqrt(n-3))',
                                 'scope': 'approximate independent-correlation planning only'},
        'decision': ('Do not run the predictive gate on 24 events. Expand a pre-specified, '
                     'redistributable official-release corpus first.'),
        'limitations': [
            'MDE is optimistic for temporal dependence, model fitting and multiple comparisons.',
            'Archive text equality is not proof of trader availability at the capture timestamp.',
            'Five archive checks remain unresolved due to network errors; none is a mismatch.',
            'The reviewer package reproduces text bytes, not a full prediction experiment.'],
        'inputs': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (audit_path, corpus_path, package_path)}
    }
    save(out, json.dumps(summary, indent=2).encode())
    with zipfile.ZipFile(archive_out, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(out, out.name)
        archive.write(audit_path, audit_path.name)
        archive.write(Path(__file__), Path(__file__).name)
    print(json.dumps({'records': n, 'matches': summary['near_release_text_matches'],
                      'mismatches': summary['near_release_text_mismatches'],
                      'errors': summary['archive_check_errors'],
                      'correlation_mde': summary['approximate_two_sided_correlation_mde'],
                      'decision': summary['decision']}))


if __name__ == '__main__':
    main()
