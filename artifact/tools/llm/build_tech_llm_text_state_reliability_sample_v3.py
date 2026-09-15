"""Build a deterministic outcome-blind reliability sample for HYB-003 text state."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


KEYWORDS = {
    "liquidation": ("liquidat", "short squeeze", "margin call"),
    "security": ("hack", "exploit", "stolen", "breach", "attack"),
    "solvency": ("bankrupt", "insolven", "withdrawal", "creditor", "reserve"),
    "regulatory": ("sec ", "lawsuit", "court", "ban", "regulat", "legal"),
    "protocol": ("outage", "network", "fork", "validator", "bridge"),
    "flow": ("buy", "sell", "inflow", "outflow", "unlock", "deposit"),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def group(headline: str) -> str:
    text = headline.casefold()
    for name, terms in KEYWORDS.items():
        if any(term in text for term in terms):
            return name
    return "other"


def rank(record: dict) -> str:
    return hashlib.sha256(record["context_id"].encode()).hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=root / "paper/input/results/hybrid/tech_llm_conditional_state_fusion_v3_text_inputs.json")
    parser.add_argument("--output", type=Path, default=root / "paper/input/results/hybrid/tech_llm_text_state_reliability_sample_v3_frozen.json")
    parser.add_argument("--records", type=int, default=96)
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    buckets = defaultdict(list)
    enriched = []
    for row in source["records"]:
        item = {**row, "lexical_stratum": f"{row['symbol']}::{group(row['headline'])}"}
        enriched.append(item)
        buckets[item["lexical_stratum"]].append(item)
    selected = []
    seen = set()
    for name in sorted(buckets):
        item = min(buckets[name], key=rank)
        selected.append(item)
        seen.add(item["context_id"])
    for item in sorted(enriched, key=rank):
        if len(selected) >= args.records:
            break
        if item["context_id"] not in seen:
            selected.append(item)
            seen.add(item["context_id"])
    if len(selected) != args.records:
        raise ValueError(f"requested {args.records} records, found {len(selected)}")
    selected.sort(key=lambda row: (row["decision_time_iso"], row["context_id"]))
    payload = {
        "schema_version": "tech-llm-text-state-reliability-sample-v3",
        "status": "frozen-before-text-state-inference",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "selection_used_market_outcomes": False,
        "selection_rule": "One minimum-hash record per nonempty held-symbol x lexical-keyword stratum, then minimum-hash fill to 96.",
        "source": {"path": str(args.input.resolve()), "sha256": sha(args.input), "records": len(source["records"])},
        "records": selected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({"output": str(args.output), "records": len(selected), "strata": len(buckets), "sha256": sha(args.output)}, indent=2))


if __name__ == "__main__":
    main()
