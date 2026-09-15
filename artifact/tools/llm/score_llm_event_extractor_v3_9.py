"""Run v3.9 extraction with normalized assets but no direct-BTC asset coupling."""
from __future__ import annotations

import score_llm_event_extractor_v3_5 as base
import score_llm_event_extractor_v3_8 as previous


_base_validate_item = base.validate_item

api = base.api
model_digest = base.model_digest
sha256 = base.sha256
write_json = base.write_json
canonicalize_btc_asset = previous.canonicalize_btc_asset
dedupe_assets = previous.dedupe_assets
normalize_assets = previous.normalize_assets


def validate_item(item: object, expected: dict, identifier_mode: str = "headline_id") -> dict:
    """Apply every v3.5 check except coupling direct relevance to asset labels."""
    if not isinstance(item, dict) or item.get("btc_relevance") != "direct":
        return _base_validate_item(item, expected, identifier_mode)

    validation_copy = {**item, "btc_relevance": "systemic"}
    validated = _base_validate_item(validation_copy, expected, identifier_mode)
    return {**validated, "btc_relevance": "direct"}


def parse_batch(raw: str, expected: list[dict], identifier_mode: str = "headline_id") -> list[dict]:
    original_validate_item = base.validate_item
    base.validate_item = validate_item
    try:
        return previous.parse_batch(raw, expected, identifier_mode)
    finally:
        base.validate_item = original_validate_item


def main() -> None:
    base.parse_batch = parse_batch
    base.main()


if __name__ == "__main__":
    main()
