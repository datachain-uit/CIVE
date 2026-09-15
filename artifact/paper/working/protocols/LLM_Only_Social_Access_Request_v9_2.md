# Social v9.2: access and historical-version request

Status: DRAFT, NOT SENT. No permission, institutional sponsorship or ethics
approval is asserted. This is operational preparation, not a legal conclusion.

## Decision

Do not download more Arctic Shift data or run it through the model. Current Reddit
policy directs research through RFR. The source review is recorded in
`paper/input/results/llm/v9/social_access_review_v9_2.json`; official document
were readable via the web tool, but direct HTML downloads returned 403. Stored
source notes and short excerpts (not HTML snapshots) are in
`paper/input/references/source_artifacts/social_corpus_v9/access_v9_2_web_evidence.json`.
No existing audit artifacts have been deleted or reclassified as approved.

RFR access alone does not establish point-in-time validity. Its published dataset
description uses updated content versions and removes deleted content. Therefore
a historical short-horizon experiment needs additional version evidence, or a
different, explicitly retrospective research claim. Moving a date or silently
dropping later-deleted posts cannot repair that distinction.

## Applicant Information Still Required

- [REQUIRED] Applicant name and institutional email.
- [REQUIRED] Institution, department and supervisor/sponsor institutional email.
- [REQUIRED] Ethics review approval or exemption, with authorized documentation.
- [REQUIRED] Approved project scope and exact data-access terms, if already held.

Do not invent these fields or submit on someone's behalf without authorization.

## Draft Request To Reddit Research Access Team

Subject: Academic LLM-only social-text study: access scope and version provenance

We are preparing a non-commercial thesis study of whether aggregate information
extracted from public r/Bitcoin text predicts subsequent Bitcoin market responses.
Institutional applicant, sponsor and ethics-review documentation will be supplied
before application submission; this draft does not assert existing approval.

We propose frozen-model inference on authorized text only. Market data would be
used solely for outcome labels and evaluation, not as predictive inputs. Any
supervised calibration or fine-tuning would require separately confirmed scope.
No user profiling, deanonymization, community interaction or live trading is planned.

Please clarify:

1. Is this project eligible, and does approval permit local frozen-LLM inference,
   aggregate feature retention and supervised calibration? What export, retention,
   deletion and publication requirements apply to each operation?
2. Can the authorized source provide first-observed text versions, UTC creation
   and observation timestamps, version histories and collection coverage? We need
   to avoid treating subsequently edited text as available at original posting.
3. If only latest versions are supplied, is prospective observation through an
   approved route available? How should researchers handle required deletions
   without claiming an unchanged historical information set?
4. Is any use of pre-existing third-party archive material authorized for this
   specific project? We will not infer that RFR approval covers external archives.

Requested scope for feasibility review: public r/Bitcoin posts/comments within
the already-viewed development years, excluding sealed-holdout evaluation. Exact
dates and sample limits will be fixed after authorized coverage is confirmed and
before any new outcome evaluation. We request only necessary text/version fields;
no direct identifiers or engagement-based rankings are required.

## Draft Provenance Questions To Archive Maintainer

Not a substitute for Reddit/rightsholder approval. Do not send until authorized.

- For the pinned archive format, does is_edited retain the original text or the
  revised text? What timestamp belongs to the retained version?
- Is a byte-identifiable first-retrieval snapshot available? Can restoration and
  later deletion be handled without selecting the sample using future metadata?
- Which fields and collection gaps differ between API responses and monthly dumps?

## Completion Criteria

Documented source-specific access scope; permitted inference/training operations;
verifiable version/time semantics; authorized coverage audit; and a frozen
predictive protocol. Until then no model result may be claimed. Synthetic smoke
tests can validate software only, not prediction, and are not a substitute here.
