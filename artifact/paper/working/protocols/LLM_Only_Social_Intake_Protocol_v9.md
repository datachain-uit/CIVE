# LLM-only social v9: intake

Latest v9.2 decision: external authorization and historical-version evidence are
required. Arctic collection entry point is suspended before network access.
See `LLM_Only_Social_Access_Request_v9_2.md`. No application was sent or permission
asserted. The older next-step suggestions below do not authorize more downloading.

Update: bounded Arctic Shift pilot completed. See
`LLM_Only_Arctic_Pilot_v9_1_Findings.md` and
`paper/input/results/llm/v9/arctic_raw_pilot_v9_1/audit.json`.
Pilot is audited but NOT admitted; do not reuse diagnostic exclusions based on
future edits/deletions as causal sample selection. No predictive experiment ran.

Status: DATA_NOT_ADMITTED, not a frozen predictive protocol. No inference, market
labels, backtest or sealed holdout accessed. Earlier development outcomes are known.

Decision evidence: `paper/input/results/llm/v9/social_source_audit_v9.json`.
Source snapshots with URLs/revisions/hashes are under
`paper/input/references/source_artifacts/social_corpus_v9/`.

## Findings

- Corsi/Campagnano merged Reddit: upstream score/comment-total selection and local
  timestamps without timezone. Reject as PIT input; dropping columns cannot undo
  selection. This does not establish that every original paper result is wrong.
- Joi123 tweets: bounded prefix only; strict UTF-8 fails. Real-time collection is
  an uploader description, not per-record receipts. License is not confirmed.
  Quarantine; do not infer full coverage or guess encoding/usage authorization.
- Arctic Shift: documentation includes retrieved_on and second-retrieval metadata.
  Next raw-pilot candidate, not admitted. Restored content cannot be backdated.

## Admission

Document usage basis and provenance. Preserve UTC creation, observation, ID and text
version. Reject naive timestamps, late observations, ambiguous restored/edited text.
No hindsight score/upvote/comment-count selection. Deduplicate IDs with as-of
versions before temporal splits. Source selection must precede outcomes.

Raw data stays in quarantine. Only admitted text reaches model inputs: no market,
technical, on-chain, engagement, author, provider labels or provider reasoning.
IDs/timestamps are audit/scheduling metadata, not predictive features. Prices only
provide labels/evaluation after a separate predictive freeze. Do not redistribute
social text or usernames without a reviewed usage basis.

Audit full pilot coverage and missingness, never extrapolate from a prefix. Check
historical LLM pretraining contamination separately; hiding dates cannot prove its
absence. record_reasons is a schema guard: its evidence booleans require review,
not automatic proof of provenance. Unit tests do not establish predictive value.

## Next Gate

Bounded Arctic Shift raw pilot on development, usage and text-version audit first.
After admission, freeze one target, window, latency, folds/purge, model and tests
before joining prices. Require improvement over BOTH LLM sentiment and train-label
prior. No repeated horizon sweeps, thresholds or backtests on the old news corpus.

[THIEU] Admitted corpus and predictive predeclaration. No v9 model result or
profitability claim. Old frozen artifacts remain unchanged.
