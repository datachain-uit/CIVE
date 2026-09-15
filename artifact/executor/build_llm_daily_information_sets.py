"""Create causal daily LLM inputs from the long-horizon headline corpus."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

UTC = timezone.utc


def balanced_selection(records: list[dict], maximum: int) -> list[dict]:
    """Round-robin domains, preserving chronological order within each source."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in sorted(records, key=lambda item: (item["published_at"], item["content_hash"])):
        groups[record["source_domain"]].append(record)
    domains = sorted(groups)
    selected: list[dict] = []
    index = 0
    while len(selected) < maximum:
        added = False
        for domain in domains:
            if index < len(groups[domain]):
                selected.append(groups[domain][index])
                added = True
                if len(selected) == maximum:
                    break
        if not added:
            break
        index += 1
    return sorted(selected, key=lambda item: (item["published_at"], item["content_hash"]))


def build(source: Path, output: Path, maximum: int = 48) -> dict:
    by_date: dict[str, list[dict]] = defaultdict(list)
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            day = datetime.fromisoformat(record["published_at"]).astimezone(UTC).date().isoformat()
            by_date[day].append(record)

    information_sets: list[dict] = []
    for day in sorted(by_date):
        records = by_date[day]
        selected = balanced_selection(records, maximum)
        source_hash = hashlib.sha256(
            "".join(sorted(item["content_hash"] for item in records)).encode("ascii")
        ).hexdigest()
        selected_hash = hashlib.sha256(
            "".join(item["content_hash"] for item in selected).encode("ascii")
        ).hexdigest()
        publication_day = datetime.fromisoformat(day).date()
        available = datetime.combine(publication_day + timedelta(days=1), time.min, UTC)
        text = "\n".join(
            f"- [{item['published_at'][11:16]} UTC | {item['source_domain']} | {item['coin_type']}] {item['text']}"
            for item in selected
        )
        information_sets.append({
            "information_date": day,
            "available_at": available.isoformat(),
            "text": text,
            "article_count": len(records),
            "selected_article_count": len(selected),
            "source_snapshot_hash": source_hash,
            "content_hash": selected_hash,
            "selection_policy": f"domain-round-robin-chronological-max-{maximum}",
            "selected_articles": [
                {key: item[key] for key in ("content_hash", "published_at", "source_domain", "coin_type", "url")}
                for item in selected
            ],
        })

    payload = {
        "schema_version": 1,
        "status": "development-not-frozen",
        "source_corpus": str(source),
        "information_set_policy": "completed UTC calendar day, available at next 00:00 UTC",
        "selection_policy": f"domain-round-robin-chronological-max-{maximum}",
        "summary": {
            "days": len(information_sets),
            "coverage_start": information_sets[0]["information_date"] if information_sets else None,
            "coverage_end": information_sets[-1]["information_date"] if information_sets else None,
            "input_articles": sum(item["article_count"] for item in information_sets),
            "selected_articles": sum(item["selected_article_count"] for item in information_sets),
            "days_capped": sum(item["article_count"] > maximum for item in information_sets),
        },
        "records": information_sets,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum", type=int, default=48)
    args = parser.parse_args()
    payload = build(args.source, args.output, args.maximum)
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
