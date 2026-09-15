"""Record a reproducible source-terms exclusion audit for the v12.1 candidate."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
REFS = ROOT / "paper/input/references/source_artifacts/bitcoin_news_mouadja02_terms_v12_1"
OUT = ROOT / "paper/input/results/llm/v12_1/bitcoin_news_terms_audit_v12_1.json"
SOURCES = {
    "guardian_open_platform_terms.html": "https://www.theguardian.com/open-platform/terms-and-conditions",
    "finnhub_terms.html": "https://finnhub.io/terms-of-service",
    "alphavantage_terms.pdf": "https://www.alphavantage.co/terms_of_service/",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> tuple[bytes, dict]:
    request = Request(url, headers={"User-Agent": "KLTN-v12.1-terms-audit/1.0"})
    started = datetime.now(timezone.utc).isoformat()
    with urlopen(request, timeout=45) as response:
        data = response.read(5_000_001)
        if len(data) > 5_000_000:
            raise ValueError("Terms response exceeds 5 MB")
        return data, {
            "url": url, "http_status": response.status, "bytes": len(data),
            "sha256": sha256(data), "fetched_at": started,
            "content_type": response.headers.get_content_type(),
        }


def main() -> None:
    if OUT.exists() or REFS.exists():
        raise SystemExit("Audit destination exists; preserve evidence and version a rerun.")
    REFS.mkdir(parents=True)
    saved = []
    for name, url in SOURCES.items():
        data, info = fetch(url)
        (REFS / name).write_bytes(data)
        saved.append({**info, "path": str((REFS / name).relative_to(ROOT))})
    guardian = (REFS / "guardian_open_platform_terms.html").read_text(encoding="utf-8", errors="replace").lower()
    finnhub = (REFS / "finnhub_terms.html").read_text(encoding="utf-8", errors="replace").lower()
    if "machine learning" not in guardian or "text and data" not in guardian:
        raise ValueError("Guardian ML/TDM restriction not found in saved terms")
    if "not redistribute or share access" not in finnhub or "derived results" not in finnhub:
        raise ValueError("Finnhub redistribution restriction not found in saved terms")
    report = {
        "status": "REJECTED_FOR_LLM_ADMISSION_SOURCE_TERMS",
        "candidate": "mouadja02/bitcoin-news-data at 29a72033d4e5d4f446e1971a185fcb8300048fe5",
        "scope": "current official terms audit; not legal advice and not a historical-terms reconstruction",
        "findings": [
            {
                "source_component": "The Guardian Open Platform content",
                "verdict": "BLOCK",
                "basis": "Current terms expressly prohibit use, copying, collection, mining or extraction for machine-learning/LLM/AI purposes and text/data aggregation, analysis or mining.",
                "resolution_needed": "Written rights clearance that specifically covers the intended corpus and LLM use.",
            },
            {
                "source_component": "Finnhub data and derived results",
                "verdict": "BLOCK",
                "basis": "Current terms prohibit redistribution or sharing access to data or derived results without written approval, and require compliance with third-party copyright.",
                "resolution_needed": "Written Finnhub approval plus evidence for each underlying publisher right.",
            },
            {
                "source_component": "Alpha Vantage platform content",
                "verdict": "UNRESOLVED",
                "basis": "Current terms describe a revocable, non-sublicensable, non-transferable license and distinguish personal non-commercial use from use needing written agreement.",
                "resolution_needed": "Written confirmation covering the precise research corpus, storage and LLM use.",
            },
        ],
        "decision": {
            "eligible_for_model_input": False,
            "eligible_for_outcome_blind_corpus": False,
            "market_data_accessed": False,
            "model_run": False,
            "next_step": "Do not seek a workaround from this dataset. Audit a different versioned source with explicit LLM/TDM-compatible rights.",
        },
        "sources": saved,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "sources": len(saved)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
