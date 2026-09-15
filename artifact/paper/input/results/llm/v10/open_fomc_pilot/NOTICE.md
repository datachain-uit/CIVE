# Reproducible FOMC text pilot

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
