"""No-backfill prospective news collector for HYB-007."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = ROOT / "paper/input/results/hybrid/hyb007_prospective_risk_attenuation"
SOURCE = {"cointelegraph": "https://cointelegraph.com/rss"}
USER_AGENT = "KLTN-HYB007-prospective-collector/1.0 (+research-provenance)"
ALIASES = (
    "bitcoin", "btc", "ethereum", "ether", "eth", "solana", "sol",
    "xrp", "ripple", "bnb", "binance coin", "crypto market", "crypto asset",
    "cryptocurrency", "digital asset", "stablecoin", "crypto exchange",
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def write_json(path: Path, value: object) -> None:
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def canonical_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("absolute HTTP(S) URL required")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", ""))


def parse_time(value: str | None) -> str | None:
    if not value:
        return None
    from email.utils import parsedate_to_datetime
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
    return iso(parsed) if parsed.tzinfo else None


def _child(node: ET.Element, name: str) -> str:
    for child in node:
        if child.tag.rsplit("}", 1)[-1].lower() == name:
            return normalize("".join(child.itertext()))
    return ""


def parse_rss(data: bytes) -> list[dict]:
    root = ET.fromstring(data)
    rows = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() != "item":
            continue
        title = _child(node, "title")
        link = _child(node, "link") or _child(node, "guid")
        categories = [normalize("".join(child.itertext())) for child in node
                      if child.tag.rsplit("}", 1)[-1].lower() == "category"]
        if link:
            rows.append({
                "title": title,
                "link": canonical_url(link),
                "published_at": parse_time(_child(node, "pubdate")),
                "categories": categories,
            })
    return rows


class PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        elif not self.skip and tag in {"p", "h1", "h2", "article", "section", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1
        elif not self.skip and tag in {"p", "h1", "h2", "article", "section"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def page_text(data: bytes) -> str:
    parser = PageText()
    parser.feed(data.decode("utf-8-sig", errors="replace"))
    return normalize(" ".join(parser.parts))


def matched_aliases(text: str) -> list[str]:
    lowered = text.casefold()
    return [alias for alias in ALIASES if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lowered)]


def is_commissioned(row: dict) -> bool:
    category_text = " ".join(row.get("categories", [])).casefold()
    return "/press-releases/" in row["link"].casefold() or "press release" in category_text or "sponsored" in category_text


def fetch(url: str) -> tuple[bytes, dict]:
    started = now_utc()
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/html"})
    with urlopen(request, timeout=45) as response:
        data = response.read(4_000_001)
        if len(data) > 4_000_000:
            raise ValueError("response exceeds 4 MB")
        completed = now_utc()
        allowed = {"content-type", "content-length", "date", "etag", "last-modified", "cache-control"}
        headers = {k: v for k, v in response.headers.items() if k.casefold() in allowed}
        return data, {
            "url": url, "http_status": response.status, "headers": headers,
            "started_at": iso(started), "completed_at": iso(completed),
            "bytes": len(data), "sha256": sha256(data),
        }


class Collector:
    def __init__(self, root: Path, fetcher: Callable[[str], tuple[bytes, dict]] = fetch) -> None:
        self.root = root
        self.fetcher = fetcher
        self.state_path = root / "state.json"
        self.records_path = root / "records.json"
        self.audit_path = root / "latest_sample_audit.json"

    @property
    def script_hash(self) -> str:
        return sha256(Path(__file__).read_bytes())

    def _raw(self, poll_id: str, name: str, data: bytes, info: dict) -> dict:
        path = self.root / "raw" / poll_id / name
        atomic_write(path, data)
        return {**info, "path": str(path.relative_to(ROOT)), "sha256": sha256(data)}

    def initialize(self) -> dict:
        if self.state_path.exists():
            raise ValueError("collector already initialized")
        started = now_utc()
        poll_id = started.strftime("%Y%m%dT%H%M%S%fZ")
        feed, info = self.fetcher(SOURCE["cointelegraph"])
        artifact = self._raw(poll_id, "feed.xml", feed, info)
        urls = sorted({row["link"] for row in parse_rss(feed)})
        state = {
            "schema_version": 1,
            "experiment_id": "HYB-007",
            "status": "PROSPECTIVE_BASELINE_ESTABLISHED_NO_BACKFILL",
            "initialized_at": iso(started),
            "source_registry": SOURCE,
            "aliases": ALIASES,
            "collector_sha256": self.script_hash,
            "baseline_urls": urls,
            "seen_urls": {url: {"status": "baseline_pre_freeze_excluded"} for url in urls},
            "polls": [{"poll_id": poll_id, "kind": "initialize", "feed": artifact, "items": len(urls)}],
        }
        write_json(self.state_path, state)
        write_json(self.records_path, [])
        self._audit(state, poll_id, [], [], [])
        return {"initialized": True, "baseline_urls": len(urls), "admitted": 0}

    def poll(self) -> dict:
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if state["source_registry"] != SOURCE or tuple(state["aliases"]) != ALIASES:
            raise ValueError("frozen source or alias registry changed")
        poll_id = now_utc().strftime("%Y%m%dT%H%M%S%fZ")
        feed, info = self.fetcher(SOURCE["cointelegraph"])
        feed_artifact = self._raw(poll_id, "feed.xml", feed, info)
        records = json.loads(self.records_path.read_text(encoding="utf-8"))
        admitted, rejected, errors = [], [], []
        for row in parse_rss(feed):
            url = row["link"]
            if url in state["seen_urls"]:
                continue
            try:
                html, page_info = self.fetcher(url)
                page_artifact = self._raw(poll_id, f"page_{sha256(url.encode())[:16]}.html", html, page_info)
                text = page_text(html)
                aliases = matched_aliases(row["title"] + " " + text)
                reasons = []
                if not row["published_at"]:
                    reasons.append("published_at_missing_or_ambiguous")
                if not text:
                    reasons.append("page_text_missing")
                if is_commissioned(row):
                    reasons.append("commissioned_or_press_release")
                if not aliases:
                    reasons.append("asset_or_systemic_alias_missing")
                record = {
                    "event_id": sha256(url.encode()),
                    "canonical_url": url,
                    "title": row["title"],
                    "categories": row["categories"],
                    "published_at": row["published_at"],
                    "available_at": page_info["completed_at"],
                    "matched_aliases": aliases,
                    "text": text,
                    "text_sha256": sha256(text.encode()),
                    "raw_feed_sha256": feed_artifact["sha256"],
                    "raw_page_sha256": page_artifact["sha256"],
                    "raw_page_path": page_artifact["path"],
                    "collection_mode": "prospective_post_freeze_no_backfill",
                }
                if reasons:
                    rejected.append({**record, "rejection_reasons": reasons})
                    state["seen_urls"][url] = {"status": "rejected", "reasons": reasons}
                else:
                    admitted.append(record)
                    state["seen_urls"][url] = {"status": "admitted", "event_id": record["event_id"]}
            except Exception as error:
                errors.append({"url": url, "error_type": type(error).__name__, "error": str(error)})
        records.extend(admitted)
        records.sort(key=lambda item: (item["available_at"], item["event_id"]))
        write_json(self.records_path, records)
        state["polls"].append({
            "poll_id": poll_id, "kind": "poll", "feed": feed_artifact,
            "admitted": len(admitted), "rejected": len(rejected), "errors": len(errors),
        })
        write_json(self.state_path, state)
        self._audit(state, poll_id, admitted, rejected, errors)
        return {"initialized": False, "admitted": len(admitted), "rejected": len(rejected), "errors": len(errors)}

    def _audit(self, state: dict, poll_id: str, admitted: list[dict], rejected: list[dict], errors: list[dict]) -> None:
        records = json.loads(self.records_path.read_text(encoding="utf-8"))
        counts = Counter(reason for row in rejected for reason in row.get("rejection_reasons", []))
        audit = {
            "schema_version": 1,
            "experiment_id": "HYB-007",
            "status": "COLLECTING_INSUFFICIENT_EFFECTIVE_SAMPLE",
            "poll_id": poll_id,
            "initialized_at": state["initialized_at"],
            "records_admitted_total": len(records),
            "records_admitted_this_poll": len(admitted),
            "records_rejected_this_poll": len(rejected),
            "rejection_reason_counts": dict(sorted(counts.items())),
            "fetch_errors": errors,
            "required_independent_clusters": 30,
            "independent_clusters": None,
            "reason_clusters_unavailable": "LLM extraction and causal Tech-state join are prohibited until a later outcome-free sample-audit stage.",
            "market_outcomes_accessed": False,
            "model_run": False,
            "backfill_prohibited": True,
            "baseline_urls_excluded": len(state["baseline_urls"]),
            "files": {
                "state.json": sha256(self.state_path.read_bytes()),
                "records.json": sha256(self.records_path.read_bytes()),
                "collector.py": self.script_hash,
            },
        }
        write_json(self.audit_path, audit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("initialize", "poll"))
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    collector = Collector(args.root)
    result = collector.initialize() if args.command == "initialize" else collector.poll()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

