"""Run v3.8 extraction with closed BTC aliases and deterministic asset dedupe."""
from __future__ import annotations

import json

import score_llm_event_extractor_v3_5 as base


_base_parse_batch = base.parse_batch


BTC_ASSET_ALIASES = {
    "btc": "BTC",
    "bitcoin": "Bitcoin",
    "bitcoin (btc)": "Bitcoin",
    "btc (bitcoin)": "BTC",
    "bitcoin/btc": "Bitcoin",
    "btc/bitcoin": "BTC",
    "wrapped btc": "BTC",
    "wbtc": "BTC",
    "wrapped bitcoin": "Bitcoin",
    "wrapped bitcoin (wbtc)": "Bitcoin",
    "wbtc (wrapped bitcoin)": "BTC",
    "wrapped bitcoin/wbtc": "Bitcoin",
    "wbtc/wrapped bitcoin": "BTC",
}

api = base.api
model_digest = base.model_digest
sha256 = base.sha256
write_json = base.write_json


def canonicalize_btc_asset(value: object) -> object:
    if not isinstance(value, str):
        return value
    normalized = " ".join(value.split()).casefold()
    return BTC_ASSET_ALIASES.get(normalized, value)


def dedupe_assets(values: list[object]) -> list[object]:
    deduped: list[object] = []
    seen: set[object] = set()
    for value in values:
        marker = value if isinstance(value, str) else (type(value).__name__, repr(value))
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(value)
    return deduped


def normalize_assets(values: list[object]) -> list[object]:
    return dedupe_assets([canonicalize_btc_asset(value) for value in values])


def parse_batch(raw: str, expected: list[dict], identifier_mode: str = "headline_id") -> list[dict]:
    payload = json.loads(raw)
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        for item in payload["results"]:
            if isinstance(item, dict) and isinstance(item.get("affected_assets"), list):
                item["affected_assets"] = normalize_assets(item["affected_assets"])
    normalized_raw = json.dumps(payload, ensure_ascii=False)
    return _base_parse_batch(normalized_raw, expected, identifier_mode)


def main() -> None:
    base.parse_batch = parse_batch
    base.main()


if __name__ == "__main__":
    main()
