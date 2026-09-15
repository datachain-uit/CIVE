"""Snapshot official access documentation; never download social records."""
import json
from datetime import datetime, timezone
from audit_social_intake_v9 import ROOT, fetch, save


def main():
    out = ROOT / 'paper/input/results/llm/v9/social_access_review_v9_2.json'
    refs = ROOT / 'paper/input/references/source_artifacts/social_corpus_v9/access_v9_2'
    if out.exists() or refs.exists():
        raise SystemExit('Review exists; preserve evidence and version the next review.')
    docs = {
        'responsible_builder': 'https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy',
        'researcher_program': 'https://support.reddithelp.com/hc/en-us/articles/49381918834964-Reddit-for-Researchers-Program',
        'public_content': 'https://support.reddithelp.com/hc/en-us/articles/26410290525844-Public-Content-Policy',
    }
    sources, errors = [], []
    for name, url in docs.items():
        try:
            _, info = fetch(url, refs / (name + '.html'))
            sources.append(info)
        except Exception as error:
            errors.append({'url': url, 'error': str(error)})
    report = {
        'status': 'EXTERNAL_AUTHORIZATION_AND_VERSION_EVIDENCE_REQUIRED',
        'reviewed_at': datetime.now(timezone.utc).isoformat(),
        'sources': sources, 'snapshot_errors': errors,
        'review_type': 'research_operations_source_review_not_legal_opinion',
        'findings': [
            {'source': docs['responsible_builder'],
             'finding': 'Current policy directs research through RFR and restricts unapproved training; public archive access is not project approval.'},
            {'source': docs['researcher_program'],
             'finding': 'Application requires institutional identity, sponsorship and ethics approval/exemption. Current-version monthly data does not by itself establish historical as-of text.'},
            {'source': docs['public_content'],
             'finding': 'Research support and public visibility do not remove applicable access and deletion requirements.'}],
        'resolved': ['Identified official approval route and specific provenance questions.',
                     'Separated frozen-model inference permission from model-training permission.',
                     'Identified latest-version/deletion selection risk independently of access approval.'],
        'unresolved': ['Project-specific authorization and applicable terms.',
                       'First-observed text/version availability and deletion-compatible study design.',
                       'Full-period coverage from an authorized source.'],
        'actions': {'additional_archive_download': False, 'model_run': False,
                    'training': False, 'market_labels_accessed': False,
                    'application_submitted': False, 'existing_artifacts_deleted': False},
        'admission_rule': 'No model corpus admission until all unresolved conditions have documented evidence.',
        'user_required': 'Institutional applicant and supervisor must provide or obtain project authorization; assistant cannot attest identity, ethics review or sign terms.'}
    save(out, json.dumps(report, indent=2).encode())
    print(json.dumps({'status': report['status'], 'sources_saved': len(sources), 'errors': errors, 'report': str(out)}))


if __name__ == '__main__':
    main()
