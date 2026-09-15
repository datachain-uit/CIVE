"""Audit the completed v16 extraction and enforce its outcome-blind data gate."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_corpus_v16/corpus.json"
PREDECLARED = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_predictive_v16/predeclared.json"
EXTRACTION = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_predictive_v16/extraction/extraction.json"
PROGRESS = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_predictive_v16/extraction/extraction_progress.json"
OUTPUT = ROOT / "paper/input/results/llm/v16/ecb_rss_archive_predictive_v16/extraction_gate.json"

RELEVANCE = ("direct", "systemic", "indirect", "none")
EVENT_TYPES = (
    "macro_liquidity", "regulation", "etf_institutional_flow", "exchange_security",
    "liquidation_leverage", "network_protocol", "fraud_legal", "adoption_business",
    "market_commentary", "other",
)
ELIGIBLE_RELEVANCE = frozenset(("direct", "systemic"))
ELIGIBLE_EVENT_TYPES = frozenset(EVENT_TYPES[:8])
DIRECTIONS = frozenset(("positive", "negative", "mixed", "unclear"))
HORIZONS = frozenset(("4h", "12h", "24h", "72h", "unknown"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp lacks UTC offset: {value}")
    return parsed


def validate_record(source: dict, extracted: dict) -> None:
    record_id = source["record_id"]
    if extracted.get("record_id") != record_id or extracted.get("headline_id") != record_id:
        raise ValueError(f"record identity mismatch: {record_id}")
    if extracted.get("archive_capture_at") != source["archive_capture_at"]:
        raise ValueError(f"information time mismatch: {record_id}")
    parse_timestamp(extracted["archive_capture_at"])
    if extracted.get("status") != "success" or extracted.get("error") is not None:
        raise ValueError(f"unsuccessful extraction record: {record_id}")
    if extracted.get("btc_relevance") not in RELEVANCE:
        raise ValueError(f"invalid relevance: {record_id}")
    if extracted.get("event_type") not in EVENT_TYPES:
        raise ValueError(f"invalid event type: {record_id}")
    if extracted.get("direction") not in DIRECTIONS:
        raise ValueError(f"invalid direction: {record_id}")
    if extracted.get("expected_horizon") not in HORIZONS:
        raise ValueError(f"invalid horizon: {record_id}")
    for field in ("severity", "reported_surprise", "confidence"):
        value = extracted.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"invalid {field}: {record_id}")
    evidence = extracted.get("evidence_span")
    if not isinstance(evidence, str) or not evidence or evidence not in source["text"]:
        raise ValueError(f"evidence is not a source-text substring: {record_id}")
    assets = extracted.get("affected_assets")
    if not isinstance(assets, list) or len(assets) > 12 or len(assets) != len(set(assets)):
        raise ValueError(f"invalid affected assets: {record_id}")


def audit(corpus_payload: dict, extraction_payload: dict, predeclared: dict) -> dict:
    corpus = corpus_payload["records"]
    extraction = extraction_payload["records"]
    expected = int(predeclared["data_gate"]["minimum_eligible_information_sets"])
    checks = {
        "corpus_identity_matches_predeclaration": (
            corpus_payload.get("corpus_id") == predeclared["corpus"]["id"]
            and predeclared["corpus"]["information_time"] == "archive_capture_at"
        ),
        "extraction_declares_complete": extraction_payload.get("status") == "EXTRACTION_COMPLETE_OUTCOME_JOIN_PROHIBITED",
        "record_count_matches": len(corpus) == len(extraction) == extraction_payload["summary"]["success"],
        "zero_extraction_errors": extraction_payload["summary"]["errors"] == 0,
        "outcomes_remain_unconsulted": extraction_payload.get("outcomes_consulted") is False,
        "backtest_remains_unconsulted": extraction_payload.get("trading_backtest_consulted") is False,
    }
    if not all(checks.values()):
        raise ValueError(f"extraction preconditions failed: {checks}")
    if [row["record_id"] for row in corpus] != [row["record_id"] for row in extraction]:
        raise ValueError("extraction count is correct but order differs from corpus")
    for source, extracted in zip(corpus, extraction):
        validate_record(source, extracted)

    eligible = [
        row for row in extraction
        if row["btc_relevance"] in ELIGIBLE_RELEVANCE and row["event_type"] in ELIGIBLE_EVENT_TYPES
    ]
    eligible_information_times = sorted({row["archive_capture_at"] for row in eligible}, key=parse_timestamp)
    all_information_times = {row["archive_capture_at"] for row in extraction}
    data_gate_passed = len(eligible_information_times) >= expected
    checks["all_records_schema_and_evidence_valid"] = True
    checks["count_and_order_match_corpus"] = True
    checks["minimum_eligible_information_sets_met"] = data_gate_passed
    status = (
        "DATA_GATE_PASS_TARGET_JOIN_AUTHORIZED"
        if data_gate_passed
        else "DATA_GATE_FAIL_STOP_BEFORE_TARGET_JOIN"
    )
    return {
        "schema_version": "ecb-rss-archive-extraction-data-gate-v16",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": predeclared["experiment_id"],
        "status": status,
        "passed": data_gate_passed,
        "extraction_gate_passed": True,
        "target_join_authorized": data_gate_passed,
        "outcomes_consulted": False,
        "trading_backtest_consulted": False,
        "eligibility_contract": {
            "btc_relevance": sorted(ELIGIBLE_RELEVANCE),
            "event_type": sorted(ELIGIBLE_EVENT_TYPES),
            "manual_filtering": False,
        },
        "counts": {
            "corpus_records": len(corpus),
            "extraction_success": len(extraction),
            "extraction_errors": 0,
            "total_information_sets": len(all_information_times),
            "eligible_records": len(eligible),
            "eligible_information_sets": len(eligible_information_times),
            "minimum_eligible_information_sets": expected,
            "shortfall_information_sets": max(0, expected - len(eligible_information_times)),
        },
        "eligible_information_time_range": {
            "first": eligible_information_times[0] if eligible_information_times else None,
            "last": eligible_information_times[-1] if eligible_information_times else None,
        },
        "category_counts": {
            "btc_relevance": dict(sorted(Counter(row["btc_relevance"] for row in extraction).items())),
            "event_type": dict(sorted(Counter(row["event_type"] for row in extraction).items())),
        },
        "checks": checks,
        "stop_rule": (
            "Data-gate failure freezes this negative artifact and prohibits target join, predictive "
            "evaluation, threshold selection, action mapping, backtest, Tech+LLM, and sealed holdout."
        ),
    }


def main() -> None:
    corpus_payload = json.loads(CORPUS.read_text(encoding="utf-8"))
    extraction_payload = json.loads(EXTRACTION.read_text(encoding="utf-8"))
    predeclared = json.loads(PREDECLARED.read_text(encoding="utf-8"))
    progress = json.loads(PROGRESS.read_text(encoding="utf-8"))
    if sha256(CORPUS) != predeclared["corpus"]["corpus_sha256"]:
        raise ValueError("corpus hash differs from frozen predeclaration")
    if sha256(EXTRACTION) == "":
        raise ValueError("unreachable empty extraction hash")
    result = audit(corpus_payload, extraction_payload, predeclared)
    if progress.get("records") != len(extraction_payload["records"]) or progress.get("errors") != 0:
        raise ValueError("progress artifact does not match completed extraction")
    result["audited_at"] = progress["updated_at"]
    result["inputs"] = {
        "predeclared": {"path": str(PREDECLARED.relative_to(ROOT)), "sha256": sha256(PREDECLARED)},
        "corpus": {"path": str(CORPUS.relative_to(ROOT)), "sha256": sha256(CORPUS)},
        "extraction": {"path": str(EXTRACTION.relative_to(ROOT)), "sha256": sha256(EXTRACTION)},
        "progress": {"path": str(PROGRESS.relative_to(ROOT)), "sha256": sha256(PROGRESS)},
        "auditor": {"path": str(Path(__file__).resolve().relative_to(ROOT)), "sha256": sha256(Path(__file__))},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

