"""Audit a pinned GitHub/LFS Bitcoin-news dataset before any corpus or outcome work."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
OWNER = "mouadja02"
REPO = "bitcoin-news-data"
API = f"https://api.github.com/repos/{OWNER}/{REPO}"
OUT = ROOT / "paper/input/results/llm/v12_1"
REFS = ROOT / "paper/input/references/source_artifacts/bitcoin_news_mouadja02_v12_1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def fetch(url: str) -> tuple[bytes, dict]:
    started = datetime.now(timezone.utc)
    request = Request(url, headers={"User-Agent": "KLTN-v12.1-source-audit/1.0", "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=45) as response:
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("Audit response exceeds 2 MB")
    return data, {"url": url, "http_status": response.status, "bytes": len(data), "sha256": sha256(data),
                  "fetched_at": started.isoformat()}


def lfs_pointer(data: bytes) -> dict | None:
    lines = data.decode("utf-8", errors="replace").splitlines()
    if not lines or lines[0].strip() != "version https://git-lfs.github.com/spec/v1":
        return None
    values = dict(line.split(" ", 1) for line in lines[1:] if " " in line)
    oid = values.get("oid", "")
    size = values.get("size", "")
    if not oid.startswith("sha256:") or not size.isdecimal():
        raise ValueError("Malformed Git LFS pointer")
    return {"sha256": oid.removeprefix("sha256:"), "bytes": int(size)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT / "bitcoin_news_source_audit_v12_1.json")
    args = parser.parse_args()
    if args.output.exists() or REFS.exists():
        raise SystemExit("Audit destination exists; preserve evidence and version a rerun.")
    sources = []

    def get(url: str, name: str) -> bytes:
        data, info = fetch(url)
        path = REFS / name
        save(path, data)
        sources.append({**info, "path": str(path.relative_to(ROOT))})
        return data

    commit = json.loads(get(API + "/commits/main", "commit_main.json"))
    revision = commit["sha"]
    tree = json.loads(get(API + f"/git/trees/{revision}?recursive=1", "tree.json"))
    readme = get(f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{revision}/README.md", "README.md")
    license_text = get(f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{revision}/LICENSE", "LICENSE")
    paths = {item["path"]: item for item in tree.get("tree", [])}
    parquet = paths.get("bitcoin-news.parquet")
    tsv = paths.get("bitcoin-news.tsv")
    if not parquet or not tsv:
        raise ValueError("Expected Parquet and TSV files are absent at pinned revision")
    pointer = get(f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{revision}/bitcoin-news.parquet", "bitcoin-news.parquet.lfs-pointer")
    lfs = lfs_pointer(pointer)
    report = {
        "status": "CONDITIONAL_CANDIDATE_NEEDS_FULL_SNAPSHOT_AND_SCHEMA_AUDIT",
        "scope": "source identity, pinned revision, license and Git LFS pointer only",
        "candidate": {"owner": OWNER, "repository": REPO, "revision": revision,
                      "commit_date": commit.get("commit", {}).get("author", {}).get("date"),
                      "dataset_files": {"parquet": parquet, "tsv": tsv}, "parquet_lfs": lfs},
        "license": {"detected_mit": "MIT License" in license_text.decode("utf-8", errors="replace"),
                    "source_terms_note": "README requires respecting original publishers' terms."},
        "reproducibility": {"reviewer_checkout": f"git clone https://github.com/{OWNER}/{REPO}.git && git checkout {revision} && git lfs pull",
                              "immutable_revision_pinned": True,
                              "full_snapshot_local": False,
                              "full_snapshot_sha256_verified": False,
                              "schema_audited": False},
        "provenance_limitations": [
            "Repository README says the dataset is continuously updated; only the pinned commit is in scope.",
            "Historical publication timestamps are dataset fields, not independent proof of strict point-in-time availability.",
            "Underlying publisher/API terms require review before model admission.",
            "No market outcome, model input, LLM inference or predictive metric was accessed in this audit."],
        "next_gate": ["Download exact Git LFS object at pinned revision.", "Verify full-file SHA-256 against the LFS pointer.",
                      "Audit schema, timestamp timezone/precision, duplicates and leakage fields.",
                      "Write a reviewer package and freeze an outcome-blind corpus contract before any market join."],
        "sources": sources,
        "readme_sha256": sha256(readme),
        "market_data_accessed": False,
        "model_run": False,
    }
    save(args.output, (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"status": report["status"], "revision": revision, "lfs": lfs}, ensure_ascii=False))


if __name__ == "__main__":
    main()