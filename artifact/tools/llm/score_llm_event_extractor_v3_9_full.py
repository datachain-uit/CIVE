"""Checkpointed full extraction using the frozen v3.9 postprocessor."""
from __future__ import annotations

import score_llm_event_extractor_v3_5_full as base
from score_llm_event_extractor_v3_9 import parse_batch


def main() -> None:
    base.parse_batch = parse_batch
    base.main()


if __name__ == "__main__":
    main()
