import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from audit_fulltext_corpus_v5 import canonical_url, normalize_text, parse_timestamp, WORD_RE


FOUR_HOURS_MS = 4 * 60 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def next_4h_open_ms(timestamp: datetime) -> int:
    value = int(timestamp.timestamp() * 1000)
    return ((value // FOUR_HOURS_MS) + 1) * FOUR_HOURS_MS


def btc_relevance(row: dict, title: str, body: str) -> int:
    categories = {item.strip().upper() for item in (row.get("categories") or "").split("|")}
    if "BTC" in categories:
        return 2
    text = f" {title.lower()} {body.lower()} "
    return 1 if " bitcoin" in text or " btc" in text else 0


def select_source_diverse(items: list[dict], limit: int) -> list[dict]:
    ordered = sorted(items, key=lambda x: (-x["btc_relevance"], x["published_at"], x["article_id"]))
    selected = []
    selected_ids = set()
    seen_sources = set()
    for item in ordered:
        if item["source"] in seen_sources:
            continue
        selected.append(item)
        selected_ids.add(item["article_id"])
        seen_sources.add(item["source"])
        if len(selected) == limit:
            return selected
    for item in ordered:
        if item["article_id"] in selected_ids:
            continue
        selected.append(item)
        if len(selected) == limit:
            break
    return selected


def market_features(rows_by_time: dict[int, list], decision_ms: int) -> dict[str, float] | None:
    offsets = {"return_4h": 1, "return_24h": 6, "return_72h": 18, "return_168h": 42}
    current = rows_by_time.get(decision_ms)
    if current is None:
        return None
    current_open = float(current[1])
    features = {}
    for name, bars in offsets.items():
        previous = rows_by_time.get(decision_ms - bars * FOUR_HOURS_MS)
        if previous is None:
            return None
        features[name] = current_open / float(previous[1]) - 1.0
    open_returns = []
    for step in range(42, 0, -1):
        before = rows_by_time.get(decision_ms - step * FOUR_HOURS_MS)
        after = rows_by_time.get(decision_ms - (step - 1) * FOUR_HOURS_MS)
        if before is None or after is None:
            return None
        open_returns.append(math.log(float(after[1]) / float(before[1])))
    features["realized_volatility_24h"] = math.sqrt(sum(value * value for value in open_returns[-6:]))
    features["realized_volatility_168h"] = math.sqrt(sum(value * value for value in open_returns))
    volumes = []
    for step in range(180, 0, -1):
        row = rows_by_time.get(decision_ms - step * FOUR_HOURS_MS)
        if row is None:
            return None
        volumes.append(float(row[5]))
    mean = float(np.mean(volumes))
    std = float(np.std(volumes))
    features["completed_volume_zscore_30d"] = (volumes[-1] - mean) / std if std > 0 else 0.0
    return features


def build(corpus_path: Path, bars_path: Path, panel_path: Path, audit_path: Path,
          minimum_words: int = 50, max_articles: int = 8) -> tuple[dict, dict]:
    csv.field_size_limit(2**31 - 1)
    bars = json.loads(bars_path.read_text(encoding="utf-8"))
    rows_by_time = {int(row[0]): row for row in bars}
    groups: dict[int, list[dict]] = defaultdict(list)
    seen_urls = set()
    rejected_short = 0
    rejected_duplicate = 0
    with corpus_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            title = normalize_text(row.get("title", ""))
            body = normalize_text(row.get("body", ""))
            if len(WORD_RE.findall(body)) < minimum_words:
                rejected_short += 1
                continue
            url = canonical_url(row.get("url", ""))
            identity = url or normalize_text(row.get("guid", "")) or normalize_text(row.get("id", ""))
            if not identity or identity in seen_urls:
                rejected_duplicate += 1
                continue
            seen_urls.add(identity)
            try:
                published = parse_timestamp(row.get("published_on", ""))
            except (TypeError, ValueError):
                continue
            decision_ms = next_4h_open_ms(published)
            source = normalize_text(row.get("source", "")).lower() or "unknown"
            groups[decision_ms].append({
                "article_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                "published_at": published.isoformat(),
                "source": source,
                "url_hash": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                "text_hash": hashlib.sha256(f"{title}\n{body}".encode("utf-8")).hexdigest(),
                "btc_relevance": btc_relevance(row, title, body),
                "text": f"{title}. {body}",
            })

    records = []
    missing_market = 0
    selected_articles = 0
    selected_sources = set()
    for decision_ms in sorted(groups):
        features = market_features(rows_by_time, decision_ms)
        exit_row = rows_by_time.get(decision_ms + DAY_MS)
        entry_row = rows_by_time.get(decision_ms)
        if features is None or entry_row is None or exit_row is None:
            missing_market += 1
            continue
        selected = select_source_diverse(groups[decision_ms], max_articles)
        selected_articles += len(selected)
        selected_sources.update(item["source"] for item in selected)
        records.append({
            "decision_at": datetime.fromtimestamp(decision_ms / 1000, timezone.utc).isoformat(),
            "market_features": features,
            "target_h24_return": float(exit_row[1]) / float(entry_row[1]) - 1.0,
            "articles": selected,
        })

    panel = {
        "schema_version": "llm-fulltext-market-impact-panel-v5",
        "status": "development-panel-not-model-result",
        "sources": {
            "corpus": {"path": str(corpus_path.resolve()), "sha256": sha256(corpus_path)},
            "btc_4h": {"path": str(bars_path.resolve()), "sha256": sha256(bars_path)},
        },
        "policy": {
            "minimum_body_words": minimum_words,
            "max_articles_per_bucket": max_articles,
            "bucket": "publication strictly before the next UTC 4h open",
            "selection": "BTC relevance descending, source-diverse first, then publication time and article_id",
            "target": "Bybit BTCUSDT open[t+24h] / open[t] - 1",
            "market_features": "causal values available at decision open; volume uses completed bars only",
        },
        "records": records,
    }
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    panel_path.write_text(json.dumps(panel, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    audit = {
        "schema_version": "llm-fulltext-market-impact-panel-audit-v5",
        "panel": {"path": str(panel_path.resolve()), "sha256": sha256(panel_path)},
        "counts": {
            "eligible_unique_articles": len(seen_urls),
            "selected_articles": selected_articles,
            "selected_sources": len(selected_sources),
            "labeled_four_hour_buckets": len(records),
            "rejected_short_body_rows": rejected_short,
            "rejected_duplicate_identities": rejected_duplicate,
            "buckets_without_complete_market_data": missing_market,
        },
        "coverage": {
            "start": records[0]["decision_at"] if records else None,
            "end": records[-1]["decision_at"] if records else None,
        },
        "market_feature_names": list(records[0]["market_features"]) if records else [],
        "target_summary_for_data_audit_only": {
            "finite": all(np.isfinite(item["target_h24_return"]) for item in records),
            "nonconstant": len({item["target_h24_return"] for item in records}) > 1,
        },
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return panel, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--panel-output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--minimum-words", type=int, default=50)
    parser.add_argument("--max-articles", type=int, default=8)
    args = parser.parse_args()
    _, audit = build(args.corpus, args.bars, args.panel_output, args.audit_output,
                     args.minimum_words, args.max_articles)
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
