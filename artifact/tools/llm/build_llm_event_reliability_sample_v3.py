"""Create a deterministic stratified sample for event-extractor reliability testing."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rank(seed: int, headline_id: str) -> str:
    return hashlib.sha256(f"{seed}:{headline_id}".encode("ascii")).hexdigest()


def build(source_path: Path, output_path: Path, seed: int = 20260823,
          per_stratum: int = 3) -> dict:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    strata: dict[tuple[int, str, str], list[dict]] = defaultdict(list)
    for record in source["records"]:
        year = int(record["information_date"][:4])
        asset_group = "bitcoin" if record["coin_type"] == "Bitcoin" else "non_bitcoin"
        strata[(year, record["source_domain"], asset_group)].append(record)

    selected = []
    counts = {}
    for key in sorted(strata):
        candidates = sorted(strata[key], key=lambda item: rank(seed, item["headline_id"]))
        if len(candidates) < per_stratum:
            raise ValueError(f"stratum {key} has only {len(candidates)} records")
        chosen = candidates[:per_stratum]
        selected.extend(chosen)
        counts["|".join(map(str, key))] = len(chosen)
    selected.sort(key=lambda item: (item["information_date"], item["published_at"], item["headline_id"]))
    expected = len(strata) * per_stratum
    if len(selected) != expected or len({item["headline_id"] for item in selected}) != expected:
        raise ValueError("sample count or uniqueness check failed")

    payload = {
        "schema_version": 1,
        "experiment_id": "llm-event-extractor-v3-stage1-reliability-sample",
        "status": "frozen-before-event-extractor-inference",
        "selection": {
            "seed": seed,
            "rank": "sha256(seed:headline_id)",
            "strata": ["information year", "source domain", "Bitcoin vs non-Bitcoin coin_type"],
            "per_stratum": per_stratum,
            "outcomes_consulted": False,
        },
        "source": {"path": str(source_path), "sha256": sha256(source_path)},
        "summary": {
            "strata": len(strata),
            "records": len(selected),
            "unique_headline_ids": len({item["headline_id"] for item in selected}),
            "stratum_counts": counts,
        },
        "records": selected,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--per-stratum", type=int, default=3)
    args = parser.parse_args()
    result = build(args.source, args.output, args.seed, args.per_stratum)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
