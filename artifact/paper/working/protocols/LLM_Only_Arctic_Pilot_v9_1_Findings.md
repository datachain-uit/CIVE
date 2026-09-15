# Arctic Shift v9.1: ket qua raw pilot

Subsequent v9.2 access review suspends further archive collection. Refer to
`LLM_Only_Social_Access_Request_v9_2.md` before any follow-up. Pilot numbers below
are unchanged; public access is not source-specific research authorization.

Status: PILOT_AUDITED_NOT_ADMITTED. Completed provenance pilot, not a predictive
experiment. No model inference, market features, price labels or sealed holdout.

Evidence: `paper/input/results/llm/v9/arctic_raw_pilot_v9_1/predeclared.json`
and `audit.json`. Source documents are pinned and hashed in that audit. Raw API
responses are kept locally in `runtime/external/social_v9/arctic_raw_pilot_v9_1/`;
they are quarantine artifacts, not model inputs and not for redistribution.

## Observed Results

Six chronological, capped API samples yielded 600 records from r/Bitcoin.
Each sample contains the earliest 100 posts or comments within one requested UTC
day. All hit the cap; none establishes full-day coverage or representativeness.

| UTC day | Type | Rows | Conditional version/time checks | Observed before next creation-based 4h boundary |
|---|---|---:|---:|---:|
| 2023-04-01 | posts | 100 | 0 | 0 |
| 2023-04-01 | comments | 100 | 80 | 0 |
| 2024-01-01 | posts | 100 | 80 | 80 |
| 2024-01-01 | comments | 100 | 80 | 80 |
| 2025-01-01 | posts | 100 | 39 | 39 |
| 2025-01-01 | comments | 100 | 88 | 88 |

367 records passed the conditional structural/version checks, but only 287 also
arrived before the diagnostic next 4h boundary. Neither count is an admission
count. Admitted model inputs remain zero. This boundary is a latency diagnostic,
not a selected prediction target or evidence of incremental predictive value.

For sampled 2024/2025 records, recorded observation delays span 12-31 seconds.
For sampled April 2023 records, delays span 7,017,889-9,660,534 seconds. Therefore
creation time alone cannot establish intraday availability. These are API field
measurements, not independently verified network receipt times.

## Interpretation Limits

- Conditional checks exclude edits/restorations/deletions and unknown metadata.
  Those flags can be learned AFTER the proposed forecast cutoff. Using the
  filtered subset as a training population would itself introduce hindsight
  selection. The current output is diagnostic ONLY, never an as-of-ready dataset.
- A causal design must recover first-observed versions and select using only
  information available then, or move availability to a documented later snapshot.
  Do not silently remove future-deleted records and label the remainder PIT-clean.
- API responses collected now do not certify exact historical dump versions.
  Missing `_meta` is an uncertainty flag, not proof that the text is corrupted.
- Public access and a stated research purpose do not establish a reviewed license
  to train models or redistribute text. Usage basis remains unresolved.
- Historical LLM memorization and period selection remain development risks.
  Pilot quality does not imply a positive model result.

## Decision

The source is worth further provenance work because observation timestamps are
present, but it is NOT admitted. Next work requires a pinned raw monthly dump,
verification of original text-version semantics, complete chronological coverage
and a documented usage basis. Do not launch a large download or LLM training
on these six samples. After data admission, freeze a separate social-only
predictive protocol that must beat both LLM sentiment and a train-label prior.

Tests: `tools/llm/test_audit_arctic_pilot_v9.py` covers edits, restoration,
missing metadata, unknown notes, late observations, invalid epochs, duplicate IDs,
removed text and chronology. Code-test success does not validate research claims.
