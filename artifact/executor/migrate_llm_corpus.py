"""Migrate legacy date-only crypto news without importing legacy scores."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from llm_causal_pipeline import migrate_legacy_corpus, write_json

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("results/historical_ai_data.json"))
    parser.add_argument("--output", type=Path, default=Path("results/llm_causal_corpus_v1.json"))
    parser.add_argument("--audit", type=Path, default=Path("results/llm_causal_corpus_v1_audit.json"))
    args = parser.parse_args()
    rows = json.loads(args.input.read_text(encoding="utf-8"))
    records, audit = migrate_legacy_corpus(rows, "SahandNZ/cryptonews-articles-with-price-momentum-labels")
    write_json(args.output, records); write_json(args.audit, audit)
    print(json.dumps(audit, indent=2))

if __name__ == "__main__": main()
