"""Build article-level, outcome-free inputs for the LLM v3 event extractor."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


HEADLINE_LINE = re.compile(
    r"^- \[(?P<hour>\d{2}):(?P<minute>\d{2}) UTC \| (?P<domain>[^|]+) \| (?P<coin>[^\]]+)\] (?P<title>.+)$"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def parse_headline_lines(text: str) -> list[dict[str, str]]:
    parsed = []
    for line in text.splitlines():
        match = HEADLINE_LINE.fullmatch(line.strip())
        if not match:
            raise ValueError(f"invalid headline line: {line!r}")
        parsed.append(match.groupdict())
    return parsed


def build(source_path: Path, target_panel_path: Path, output_path: Path) -> dict:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    target_panel = json.loads(target_panel_path.read_text(encoding="utf-8"))
    eligible_dates = {item["information_date"] for item in target_panel["records"]}
    records = []
    domains: Counter[str] = Counter()
    coin_types: Counter[str] = Counter()
    for day in source["records"]:
        if day["information_date"] not in eligible_dates:
            continue
        lines = parse_headline_lines(day["text"])
        metadata = day["selected_articles"]
        if len(lines) != len(metadata) or len(lines) != day["selected_article_count"]:
            raise ValueError(f"headline/metadata count mismatch on {day['information_date']}")
        for position, (line, article) in enumerate(zip(lines, metadata)):
            published = datetime.fromisoformat(article["published_at"]).astimezone(timezone.utc)
            if line["domain"].strip() != article["source_domain"]:
                raise ValueError(f"domain mismatch for {article['content_hash']}")
            if line["coin"].strip() != article["coin_type"]:
                raise ValueError(f"coin type mismatch for {article['content_hash']}")
            if (published.hour, published.minute) != (int(line["hour"]), int(line["minute"])):
                raise ValueError(f"publication time mismatch for {article['content_hash']}")
            immutable = {
                "headline_id": article["content_hash"],
                "information_date": day["information_date"],
                "available_at": day["available_at"],
                "published_at": article["published_at"],
                "source_domain": article["source_domain"],
                "coin_type": article["coin_type"],
                "url": article["url"],
                "headline": line["title"],
                "position_in_day": position,
            }
            records.append({**immutable, "input_hash": canonical_hash(immutable)})
            domains[article["source_domain"]] += 1
            coin_types[article["coin_type"]] += 1

    payload = {
        "schema_version": 1,
        "experiment_id": "llm-event-risk-v3-extraction-inputs-development",
        "status": "development-input-audit-before-extractor-inference",
        "contract": {
            "unit": "one selected headline per record",
            "outcome_fields_present": False,
            "market_fields_present": False,
            "filtering": "none before extraction; btc_relevance is an extractor output",
            "immutable_fields": [
                "headline_id", "information_date", "available_at", "published_at",
                "source_domain", "coin_type", "url", "headline", "position_in_day"
            ],
        },
        "sources": {
            "daily_information_sets": {"path": str(source_path), "sha256": sha256(source_path)},
            "target_panel_for_date_intersection": {
                "path": str(target_panel_path), "sha256": sha256(target_panel_path)
            },
        },
        "summary": {
            "eligible_days": len(eligible_dates),
            "records": len(records),
            "unique_headline_ids": len({item["headline_id"] for item in records}),
            "coverage_start": records[0]["information_date"] if records else None,
            "coverage_end": records[-1]["information_date"] if records else None,
            "source_domain_counts": dict(sorted(domains.items())),
            "coin_type_counts": dict(sorted(coin_types.items())),
        },
        "records": records,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target-panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args.source, args.target_panel, args.output)
    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
