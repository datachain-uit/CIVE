"""Create an outcome-blind source audit for the pinned DLT-Tweets dataset metadata."""
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLONE = ROOT / "runtime/external/dlt_tweets_source_v12_3"
OUT = ROOT / "paper/input/results/llm/v12_3/dlt_tweets_source_audit_v12_3.json"
REFS = ROOT / "paper/input/references/source_artifacts/dlt_tweets_v12_3"

def run(*args):
    return subprocess.check_output(args, text=True, encoding="utf-8")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def main():
    if OUT.exists() or REFS.exists():
        raise SystemExit("Destination exists; preserve evidence and version reruns.")
    revision = run("git", "-C", str(CLONE), "rev-parse", "HEAD").strip()
    tree = run("git", "-C", str(CLONE), "ls-tree", "-r", "--long", "HEAD").encode()
    readme = run("git", "-C", str(CLONE), "show", "HEAD:README.md").encode()
    attrs = run("git", "-C", str(CLONE), "show", "HEAD:.gitattributes").encode()
    REFS.mkdir(parents=True)
    for name, data in {"tree.txt": tree, "README.md": readme, ".gitattributes": attrs}.items():
        (REFS / name).write_bytes(data)
    paths = [line.rsplit(maxsplit=1)[-1] for line in tree.decode().splitlines()]
    shards = [path for path in paths if path.startswith("data/") and path.endswith(".parquet")]
    report = {
        "status": "CONDITIONAL_CANDIDATE_NEEDS_PIT_PROVENANCE_AND_SCHEMA_GATE",
        "candidate": {"repository": "ExponentialScience/DLT-Tweets", "revision": revision,
          "declared_license": "CC-BY-NC-4.0", "parquet_shards": len(shards), "shard_paths": shards},
        "declared_schema": ["timestamp", "tweet", "language", "total_tokens", "sentiment_class",
          "sentiment_label", "sentiment_score", "confidence_level", "year"],
        "source_audit": {
          "outcome_fields_declared": False, "market_data_accessed": False, "model_run": False,
          "raw_artifacts": {name: digest(data) for name, data in {"tree.txt": tree, "README.md": readme, ".gitattributes": attrs}.items()}},
        "admission": {"eligible_for_model_input": False,
          "blocking_reasons": ["Timestamp is a string and timezone/precision have not been verified.",
            "Dataset card's historical-TOS statement needs independent provenance evidence.",
            "Precomputed sentiment fields must be excluded unless separately predeclared and audited."]},
        "next_gate": ["Download only one pinned shard for schema/timestamp audit.", "Audit provenance evidence and determine an explicitly permitted research-use policy.", "Freeze text-only field contract before any outcome join."]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "revision": revision, "shards": len(shards)}))
if __name__ == "__main__":
    main()
