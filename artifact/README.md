# Reproducible Research Package for LLM-Assisted Crypto Trading

This repository contains the code, data snapshots, frozen machine-readable evidence, experiment ledger, and registered protocols needed to audit or replay an undergraduate research project on whether event-conditioned large language model (LLM) signals add decision value to a technical cryptocurrency perpetual-futures strategy.

The working name **CIVE** means **Controlled Incremental Value Evaluation**. CIVE names the evaluation framework; it is not a claim that a new forecasting algorithm was invented. The framework compares information in controlled stages: a technical baseline, LLM-only diagnostics, and hybrid Tech+LLM decision rules. All conclusions are conditional on the registered data, targets, time windows, costs, and gates.

CIVE is a concise repository-level label for the evaluation method.

## Reproducibility scope

A complete clone contains:

- the research Python snapshot used for the registered evaluations;
- the configurations used by the technical and LLM experiments;
- the CryptoVision v2 source archive and its causal, outcome-free derivative;
- Bybit lifecycle daily, 4-hour, and funding snapshots;
- experiment inputs, intermediate outputs, result JSON files, and manifests;
- a SHA-256 migration manifest covering 1,770 copied files;
- the curated frozen evidence used to support the reported findings;

This package supports three different tasks:

1. **Audit:** verify every migrated file and every sealed LLM-freeze artifact without contacting an external provider.
2. **Replay:** rerun deterministic transformations, technical backtests, statistical checks, tables, and figures from committed snapshots.
3. **Reacquisition:** download a new copy from an upstream API or dataset provider. A reacquired dataset is a new version and may not be byte-identical to the paper snapshot.

Local model weights and virtual environments are not committed. Model identifiers, configurations, output artifacts, and two pinned Python environment files are included. A full LLM inference rerun requires obtaining the recorded model revision separately.

## Repository map

| Path | Contents |
|---|---|
| [configs/](configs/) | Original machine-readable experiment configurations. |
| [data/llm_sources/](data/llm_sources/) | CryptoVision v2 source archive and causal derivative. |
| [executor/](executor/) | Original research and evaluation code snapshot. Live-trading modules are retained because research modules import shared execution semantics; live trading is not required for paper reproduction. |
| [results/](results/) | Complete legacy research-results snapshot, including cached market data and exploratory outputs. |
| [reproduction/auto_trading_snapshot_manifest.csv](reproduction/auto_trading_snapshot_manifest.csv) | Path, byte size, SHA-256, and source modification time for every migrated file. |
| [tools/reproduction/verify_snapshot.py](tools/reproduction/verify_snapshot.py) | Verifies the migrated snapshot against that manifest. |
| [paper/input/results/](paper/input/results/) | Curated experiment ledger, frozen evidence, provenance, LLM studies, and hybrid studies. The retained path preserves compatibility with the registered scripts. |
| [paper/input/references/](paper/input/references/) | Data-source provenance and preserved source-verification artifacts. The retained path preserves compatibility with the registered scripts. |
| [paper/working/protocols/](paper/working/protocols/) | Registered experimental and execution protocols. |
| [paper/working/audits/](paper/working/audits/) | Data-source, model-selection, and evaluation audits. |
| [paper/working/implementation/](paper/working/implementation/) | Implementation notes needed to interpret the registered code. |
| [tools/llm/](tools/llm/) | Portable LLM/hybrid audit, experiment, and regression-test utilities. |

The [results/](results/) directory is an archival snapshot of the full research workspace. It contains exploratory and superseded runs and is not a collection of accepted findings. Start result-level review with [paper/input/results/README.md](paper/input/results/README.md), the experiment ledger, and the frozen manifests.

## Evidence hierarchy

If two files disagree, use this order:

1. locked machine-readable artifacts and their freeze manifests;
2. [So_cai_thi_nghiem_Tech_LLM.xlsx](paper/input/results/experiment_ledger/So_cai_thi_nghiem_Tech_LLM.xlsx);
3. registered protocols, implementation notes, and audits under [paper/working/](paper/working/);
4. downstream narrative summaries.

Development output, inspected validation output, a frozen research candidate, a sealed holdout, and live-trading evidence are different evidence classes. A backtest does not establish live profitability. A data-eligibility failure or malformed LLM response is an operational outcome, not evidence that the model made a valid but inaccurate prediction.

## System requirements

The recorded main environment used Windows and Python 3.12.10. Its package versions are stored in [requirements-reproduction.txt](requirements-reproduction.txt).

The separate FinGPT/ChatGLM2 attempt used Python 3.12.10 and [requirements-fingpt-reproduction.txt](requirements-fingpt-reproduction.txt). Its PyTorch build was 2.8.0+cu128; install the matching official CUDA wheel when recreating that environment.

Also install:

- Git;

- enough disk space for committed snapshots and generated output;
- ripgrep, recommended for repository audits.

No API key, exchange account, Redis instance, blockchain wallet, or live-trading service is needed to audit the committed data or replay from committed snapshots. Never commit a real .env file, private key, exchange credential, or webhook URL.

## Quick start

Clone the repository:

~~~bash
git clone https://github.com/datachain-uit/CIVE.git
cd CIVE/artifact
git status --short
~~~

Create the main Python environment.

Windows PowerShell:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-reproduction.txt
~~~

Linux or macOS:

~~~bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-reproduction.txt
~~~

Hardware-specific packages, especially CUDA builds, may require the installation command published by the package vendor.

## Step 1: verify the migrated research snapshot

Run from the repository root:

~~~bash
python tools/reproduction/verify_snapshot.py
~~~

Expected result:

~~~json
{
  "verified": 1770,
  "passed": true,
  "failures": []
}
~~~

The verifier checks path existence, byte size, and SHA-256 for the copied executor, configs, data/llm_sources, and results files plus the two root analysis scripts. It does not trust names or modification dates as proof of identity.

If verification fails, check git status and do not manually recreate an expected artifact. Compare the failing item with [the migration manifest](reproduction/auto_trading_snapshot_manifest.csv).

## Step 2: verify the sealed LLM evidence freeze

The sealed LLM freeze contains 86 artifacts with a recorded total size of 200,374,422 bytes. Verify its manifest seal and all member hashes:

~~~bash
python tools/llm/verify_llm_freeze.py paper/input/results/frozen/llm_direct_direction_v1
~~~

A passing result reports "passed": true. A missing artifact, size mismatch, member-hash mismatch, or manifest-seal mismatch invalidates the local freeze.

For an independent Tech-Control check:

~~~powershell
Get-FileHash results/technical_bybit_lifecycle_1x_candidate_hardened.json -Algorithm SHA256
~~~

Linux or macOS:

~~~bash
sha256sum results/technical_bybit_lifecycle_1x_candidate_hardened.json
~~~

Expected SHA-256:

~~~text
7e8e8653c207e759e6cd3093e78705486fd732ba588362620ffe0ff372c60cf7
~~~

## Data sources

### Market and execution data

| Source | Project use | Upstream location | Committed location |
|---|---|---|---|
| Bybit V5 Market API | Linear USDT perpetual lifecycle, daily and 4-hour candles, funding history, open interest, premium index, and risk-limit metadata | [API](https://api.bybit.com/v5/market) and [documentation](https://bybit-exchange.github.io/docs/v5/market/) | [daily](results/bybit_lifecycle_daily/), [4-hour](results/bybit_lifecycle_4h/), [funding](results/bybit_lifecycle_funding/), and related cache directories |
| Binance Public Data | BTCUSDT spot 4-hour candles for source-coverage feasibility | [data.binance.vision](https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h/) | audits and source artifacts under [paper/input/references/source_artifacts/](paper/input/references/source_artifacts/) |
| Binance Futures API | Historical microstructure and cross-venue diagnostics | [fapi.binance.com](https://fapi.binance.com) | [historical_microstructure.json](results/historical_microstructure.json) and related caches |
| OKX public market API | Cross-venue diagnostics | [OKX Market Data API](https://www.okx.com/api/v5/market/) | relevant result JSON and provenance records |

The committed Bybit snapshots, not a current API response, are the inputs for reproducing the reported Tech-Control result. Exchange history, instrument status, and API behavior can change.

### Text and event data

| Source | Project use | Upstream location | Committed evidence |
|---|---|---|---|
| CryptoVision v2 | Outcome-free crypto-news titles and timestamps | [Mendeley Data v2](https://data.mendeley.com/datasets/3c3xtxtfb6/2), DOI 10.17632/3c3xtxtfb6.2, CC BY 4.0 | [source ZIP](data/llm_sources/cryptovision_v2.zip) and [causal derivative](data/llm_sources/cryptovision_v2_causal.jsonl.gz) |
| Bitcoin News Data | Version-pinned corpus and reuse screening | [mouadja02/bitcoin-news-data](https://github.com/mouadja02/bitcoin-news-data) | [source audit](paper/input/references/source_artifacts/bitcoin_news_mouadja02_v12_1/) and terms audit |
| CoinDesk full-text corpus | Full-text market-impact feasibility | [Hugging Face dataset](https://huggingface.co/datasets/maryamfakhari/crypto-news-coindesk-2020-2025) | v5 protocol/audit artifacts |
| Federal Reserve | FOMC and policy-release corpora | [federalreserve.gov](https://www.federalreserve.gov/) | v10/v11 result and source artifacts |
| SEC | Archived press-release RSS | [SEC RSS](https://www.sec.gov/news/pressreleases.rss) and Internet Archive captures | v14 result and source artifacts |
| CFTC | Archived general and enforcement RSS | [general](https://www.cftc.gov/RSS/RSSGP/rssgp.xml), [enforcement](https://www.cftc.gov/RSS/RSSENF/rssenf.xml), and Internet Archive captures | v15 result and source artifacts |
| ECB | Archived press-release RSS | [ECB RSS](https://www.ecb.europa.eu/rss/press.html) and Internet Archive captures | v16 result and source artifacts |
| Federal Register | Official crypto-related documents | [API documentation](https://www.federalregister.gov/developers/documentation/api/v1) | v12.5 result and source artifacts |
| Reddit/Arctic Shift | Social-data feasibility screening | [Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift) | v9 source-access audits; screening is not an accepted predictive result |

For reference preservation, [paper/input/references/source_artifacts/manifest.csv](paper/input/references/source_artifacts/manifest.csv) records local paths, URLs, retrieval metadata, checksums, and sizes. Read [its README](paper/input/references/source_artifacts/README.md) before refreshing any source.

## Rebuild the causal CryptoVision corpus

The committed ZIP contains one CSV. The builder imports only URL, Title, Date Time, and Coin Type; it excludes labels and market-outcome columns to prevent target leakage.

~~~bash
python executor/build_long_horizon_llm_corpus.py \
  --source data/llm_sources/cryptovision_v2.zip \
  --output runtime/reproduction/cryptovision_v2_causal.jsonl.gz \
  --manifest runtime/reproduction/cryptovision_v2_causal.manifest.json
~~~

On PowerShell, place the command on one line or replace each trailing backslash with a PowerShell backtick. The regenerated JSONL must contain 117,444 records and its uncompressed SHA-256 must be `52ab166b3a9a2dbd439be680ff823fbced430194ecc3760992fd47dbb24c144c`. The compressed `.gz` hash can differ because the gzip header records a creation timestamp; compare the decompressed byte stream, not the container hash. The generated manifest also has a new generation timestamp and is not expected to be byte-identical.

The builder converts timestamps to UTC, enforces an allowed-domain list, rejects invalid records, deduplicates by normalized-title SHA-256 and normalized URL, records all counts, and never imports sentiment or price-movement labels.

## Replay the frozen Tech-Control configuration

The authoritative configuration is [configs/technical_control_v1.json](configs/technical_control_v1.json). The reported candidate uses Bybit linear USDT perpetuals, completed daily candles, 4-hour execution bars, one long position selected by 20-day momentum, 1x gross leverage, 3 ATR fixed stop, 4 ATR trailing stop, 180-day folds, historical funding, and open_funding_intrabar_v2 execution semantics.

Replay from committed snapshots and write output to ignored runtime storage:

~~~bash
python executor/technical_bybit_lifecycle_execution.py \
  --manifest results/bybit_lifecycle_universe.json \
  --daily-cache-dir results/bybit_lifecycle_daily \
  --four-h-cache-dir results/bybit_lifecycle_4h \
  --funding-cache-dir results/bybit_lifecycle_funding \
  --workers 6 \
  --top-n 1 \
  --rank-days 20 \
  --balance 10000 \
  --gross-leverage 1 \
  --fee-bps 6 \
  --slippage-bps 3 \
  --spread-bps 2 \
  --impact-bps 1 \
  --stop-atr 3 \
  --trail-atr 4 \
  --fold-days 180 \
  --output runtime/reproduction/technical_control.json \
  --experiment-manifest runtime/reproduction/technical_control.manifest.json
~~~

Compare the replay structurally and numerically with [the frozen legacy result](results/technical_bybit_lifecycle_1x_candidate_hardened.json). The historical manifest records six workers. Reduce worker count only after confirming output ordering and calculations remain deterministic.

Do not rebuild the point-in-time universe from today's API when reproducing the paper. The acquisition entry point below creates a newly dated dataset:

~~~bash
python executor/technical_bybit_lifecycle_universe.py --help
~~~

## LLM and hybrid experiment routing

There is no safe single command for every LLM and hybrid experiment. Each experiment has its own registered data gate, representation or prompt, model configuration, outcome contract, and stop rule.

Use this order:

1. locate the experiment ID in the experiment ledger;
2. read the matching protocol under [paper/working/protocols/](paper/working/protocols/);
3. locate the exact input and SHA-256 in its manifest or provenance record;
4. read the matching config in [configs/](configs/) and script in [executor/](executor/) or [tools/llm/](tools/llm/);
5. confirm the evidence class;
6. write new output under runtime/reproduction, never over frozen evidence;
7. compare schema, row count, chronological boundaries, metrics, and hashes;
8. update the experiment ledger only after the registered gates pass.

Pipeline:

~~~text
public source
  -> immutable raw snapshot and retrieval metadata
  -> canonical UTC-aligned event/market table
  -> availability, sample-size, schema, and leakage gates
  -> chronological development/validation/holdout split
  -> technical or related baseline
  -> event-conditioned/LLM model
  -> hybrid decision rule
  -> result artifact, manifest, and ledger entry
  -> verified result package
~~~

Never shuffle time-series rows. Publication time, data availability, bar closure, and fill time must follow the matching as-of protocol. If the original study's data and design are not reproduced exactly, call the study a transfer test, not a replication.

### Local models

Model weights were excluded because they occupied approximately 16 GB. Virtual environments, caches, and secrets were also excluded.

For an inference replay, obtain the exact model identifier/revision from the matching config or artifact and record the model and tokenizer revision, prompt/schema version, quantization and decoding settings, library versions, device/CUDA version, seed, input snapshot, and every failed response.

Ollama-compatible scripts expect a local endpoint at http://127.0.0.1:11434. Model download and server startup are not part of the audit workflow. A malformed output is an operational failure and must not be manually repaired into a valid prediction.

## Regression tests

~~~bash
python -m unittest discover -s executor -p "test_*.py"
python -m unittest discover -s tools/llm -p "test_*.py"
~~~

Some integration tests may require an optional library, model, or network resource. Report these separately from deterministic unit-test failures.

## Data-integrity rules

- Never replace a committed snapshot silently with a new download.
- Record URL, UTC retrieval time, byte size, SHA-256, schema, and row count for every new external snapshot.
- Treat [paper/input/results/frozen/](paper/input/results/frozen/) as append-only evidence.
- Keep replay output in runtime/reproduction until it passes registered checks.
- Do not infer a result from a directory or file name.
- Keep development, validation, frozen-candidate, sealed-holdout, and live evidence separate.
- Do not report a numerical finding unless it is traceable to a locked artifact or experiment-ledger row.
- Never use a manuscript, screenshot, or chat transcript as the source of a number.

## Migration provenance and exclusions

The research snapshot was copied from the former local workspace without deleting or modifying the source. Included: 1,770 files, approximately 228.38 MB at migration time.

Intentionally excluded:

- .env and all credentials;
- models (approximately 16 GB);
- the two virtual environments (approximately 8.8 GB combined);
- frontend dependencies and caches;
- temporary logs, Python caches, and scratch output;
- dashboard, blockchain, and live-deployment assets not required for paper verification.

Snapshot identity is defined by [the SHA-256 manifest](reproduction/auto_trading_snapshot_manifest.csv), not by the former absolute path.

## Known limitations

- Full LLM inference requires external model downloads.
- CUDA and quantized inference can be hardware-sensitive.
- Upstream APIs and public datasets can change after retrieval.
- The full root results snapshot includes exploratory and superseded work.
- Some historical manifests preserve the old workstation path as provenance. Current replay inputs are the repository-relative copies.
- A permanent Zenodo DOI and verified release tag have not yet been recorded.

These limitations do not prevent checksum-based inspection of the reported data and frozen evidence. They do limit bit-for-bit regeneration of nondeterministic LLM output on different hardware.

## Data and code availability

The repository provides research code, data snapshots needed for the reported evaluations, frozen evidence, provenance, registered protocols, and the experiment ledger. External materials remain subject to their original licenses and terms.

Add a Zenodo or anonymous-review URL only after the deposit exists and has been verified against a specific Git commit. Do not invent a DOI.

## Citation

Until a verified archival DOI exists, cite the paper and record the exact commit:

~~~bash
git rev-parse HEAD
~~~

## Responsible use

This is research software, not financial advice and not a production trading system. Reported backtests depend on the registered sample, execution semantics, costs, funding data, and selection process. They do not guarantee future performance or establish approval for live deployment.
