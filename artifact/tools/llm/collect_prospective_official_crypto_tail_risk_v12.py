"""Prospective, no-backfill collector for the v12 official crypto tail-risk corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = ROOT / "paper/input/results/llm/v12/prospective_official_crypto_tail_risk"
USER_AGENT = "KLTN-v12-prospective-collector/1.0 (+research-provenance)"
SOURCES = {
    "sec_press_releases": "https://www.sec.gov/news/pressreleases.rss",
    "cftc_general_press_releases": "https://www.cftc.gov/RSS/RSSGP/rssgp.xml",
    "cftc_enforcement_press_releases": "https://www.cftc.gov/RSS/RSSENF/rssenf.xml",
}
CRYPTO_ALLOWLIST = (
    "crypto asset", "crypto-asset", "cryptocurrency", "digital asset", "digital-asset",
    "virtual currency", "bitcoin", "ether", "stablecoin", "blockchain", "token",
    "decentralized finance", "defi", "exchange token", "custody of crypto",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def save_json(path: Path, payload: object) -> None:
    save(path, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def canonical_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be absolute HTTP(S)")
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def matched_terms(text: str) -> list[str]:
    lowered = normalized_text(text).lower()
    return [term for term in CRYPTO_ALLOWLIST if term.lower() in lowered]


def parse_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        from email.utils import parsedate_to_datetime
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return None
    return iso(parsed)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(node: ET.Element, names: set[str]) -> str:
    for child in node:
        if local_name(child.tag) in names:
            text = normalized_text("".join(child.itertext()))
            if text:
                return text
    return ""


def parse_feed(data: bytes) -> list[dict]:
    """Parse RSS or Atom items without trusting the feed as historical evidence."""
    root = ET.fromstring(data)
    rows: list[dict] = []
    for item in root.iter():
        if local_name(item.tag) not in {"item", "entry"}:
            continue
        title = child_text(item, {"title"})
        published = child_text(item, {"pubdate", "published", "updated", "date"})
        link = ""
        for child in item:
            if local_name(child.tag) != "link":
                continue
            candidate = child.attrib.get("href", "") or normalized_text("".join(child.itertext()))
            rel = child.attrib.get("rel", "alternate")
            if candidate and rel in {"alternate", ""}:
                link = candidate
                break
        if not link:
            link = child_text(item, {"link", "guid", "id"})
        if link:
            rows.append({"title": title, "link": link, "published_at": parse_timestamp(published)})
    return rows


class TextExtractor(HTMLParser):
    BLOCKS = {"p", "div", "article", "section", "li", "h1", "h2", "h3", "h4", "br"}
    SKIP = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if not self.skip_depth and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self.in_title = False
        if not self.skip_depth and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        self.parts.append(data)
        if self.in_title:
            self.title_parts.append(data)


def extract_release_text(data: bytes) -> tuple[str, str]:
    parser = TextExtractor()
    parser.feed(data.decode("utf-8-sig", errors="replace"))
    text = normalized_text(" ".join(parser.parts))
    title = normalized_text(" ".join(parser.title_parts))
    return title, text


def provenance_headers(headers) -> dict[str, str]:
    allowed = {"content-type", "content-length", "date", "etag", "last-modified", "cache-control", "content-range"}
    return {key: ("<redacted>" if key.lower() == "set-cookie" else value)
            for key, value in headers.items() if key.lower() in allowed or key.lower() == "set-cookie"}


def http_fetch(url: str) -> tuple[bytes, dict]:
    started = utc_now()
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, text/html"})
    with urlopen(request, timeout=45) as response:
        data = response.read(4_000_001)
        if len(data) > 4_000_000:
            raise ValueError("Response exceeds 4 MB collection limit")
        completed = utc_now()
        return data, {
            "url": url,
            "http_status": response.status,
            "headers": provenance_headers(response.headers),
            "started_at": iso(started),
            "completed_at": iso(completed),
            "bytes": len(data),
            "sha256": digest(data),
        }


@dataclass(frozen=True)
class PollResult:
    initialized: bool
    admitted: int
    rejected: int
    fetch_errors: int
    output_root: Path


class Collector:
    def __init__(self, root: Path, fetcher: Callable[[str], tuple[bytes, dict]] = http_fetch) -> None:
        self.root = root
        self.fetcher = fetcher
        self.state_path = root / "state.json"
        self.records_path = root / "records.json"
        self.audit_path = root / "latest_audit.json"

    @property
    def script_hash(self) -> str:
        return digest(Path(__file__).read_bytes())

    def _state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write_raw(self, poll_id: str, source: str, name: str, data: bytes, info: dict) -> dict:
        path = self.root / "raw" / "polls" / poll_id / source / name
        save(path, data)
        return {**info, "path": str(path.relative_to(ROOT)), "sha256": digest(data)}

    def initialize(self) -> PollResult:
        if self.state_path.exists():
            raise ValueError("Collector already initialized; use poll instead")
        started = utc_now()
        poll_id = started.strftime("%Y%m%dT%H%M%S%fZ")
        baselines: dict[str, list[str]] = {}
        feed_artifacts = []
        failures = []
        for source, url in SOURCES.items():
            try:
                data, info = self.fetcher(url)
                artifact = self._write_raw(poll_id, source, "feed.xml", data, info)
                urls = sorted({canonical_url(row["link"]) for row in parse_feed(data) if row.get("link")})
                baselines[source] = urls
                feed_artifacts.append({"source": source, "items": len(urls), "artifact": artifact})
            except Exception as error:
                failures.append({"source": source, "error_type": type(error).__name__, "error": str(error)})
        if failures:
            raise RuntimeError("Initialization incomplete; no state written: " + json.dumps(failures))
        state = {
            "schema_version": 1,
            "status": "PROSPECTIVE_BASELINE_ESTABLISHED_NO_BACKFILL",
            "initialized_at": iso(started),
            "sources": SOURCES,
            "crypto_allowlist": CRYPTO_ALLOWLIST,
            "collector_script_sha256": self.script_hash,
            "baseline_urls": baselines,
            "seen_urls": {url: {"source": source, "status": "baseline_pre_start_excluded"}
                          for source, urls in baselines.items() for url in urls},
            "polls": [{"poll_id": poll_id, "kind": "initialize", "feed_artifacts": feed_artifacts}],
        }
        save_json(self.state_path, state)
        save_json(self.records_path, [])
        self._audit(state, poll_id, [], [], [])
        return PollResult(True, 0, 0, 0, self.root)

    def poll(self) -> PollResult:
        if not self.state_path.exists():
            raise ValueError("Collector not initialized; run initialize first")
        state = self._state()
        if state.get("sources") != SOURCES or tuple(state.get("crypto_allowlist", [])) != CRYPTO_ALLOWLIST:
            raise ValueError("Source registry or allowlist differs from frozen v12 state")
        started = utc_now()
        poll_id = started.strftime("%Y%m%dT%H%M%S%fZ")
        records = json.loads(self.records_path.read_text(encoding="utf-8"))
        admitted, rejected, errors, feed_artifacts = [], [], [], []
        for source, url in SOURCES.items():
            try:
                feed, info = self.fetcher(url)
                feed_artifacts.append({"source": source, "artifact": self._write_raw(poll_id, source, "feed.xml", feed, info)})
                items = parse_feed(feed)
            except Exception as error:
                errors.append({"source": source, "stage": "feed", "error_type": type(error).__name__, "error": str(error)})
                continue
            for item in items:
                try:
                    url_key = canonical_url(item["link"])
                except (KeyError, ValueError) as error:
                    rejected.append({"source": source, "reason": "invalid_feed_url", "detail": str(error)})
                    continue
                if url_key in state["seen_urls"]:
                    continue
                try:
                    page, page_info = self.fetcher(url_key)
                    release_artifact = self._write_raw(poll_id, source, f"release_{digest(url_key.encode())[:16]}.html", page, page_info)
                    page_title, text = extract_release_text(page)
                    terms = matched_terms(item.get("title", "") + "\n" + text)
                    reasons = []
                    if not item.get("published_at"):
                        reasons.append("published_at_missing_or_ambiguous")
                    if not text:
                        reasons.append("release_text_missing")
                    if not terms:
                        reasons.append("not_crypto_specific")
                    event_id = digest(url_key.encode())
                    record = {
                        "event_id": event_id,
                        "source": source,
                        "canonical_url": url_key,
                        "feed_title": item.get("title", ""),
                        "release_title": page_title,
                        "published_at": item.get("published_at"),
                        "available_at": page_info["completed_at"],
                        "crypto_matches": terms,
                        "raw_feed_sha256": feed_artifacts[-1]["artifact"]["sha256"],
                        "raw_release_sha256": release_artifact["sha256"],
                        "raw_release_path": release_artifact["path"],
                        "text": text,
                        "text_sha256": digest(text.encode("utf-8")),
                        "collection_mode": "prospective_post_baseline",
                    }
                    state["seen_urls"][url_key] = {"source": source, "status": "admitted" if not reasons else "rejected", "event_id": event_id}
                    if reasons:
                        rejected.append({**record, "rejection_reasons": reasons})
                    else:
                        admitted.append(record)
                except Exception as error:
                    errors.append({"source": source, "url": url_key, "stage": "release", "error_type": type(error).__name__, "error": str(error)})
        records.extend(admitted)
        records.sort(key=lambda row: (row["available_at"], row["event_id"]))
        save_json(self.records_path, records)
        state["polls"].append({"poll_id": poll_id, "kind": "poll", "started_at": iso(started), "feed_artifacts": feed_artifacts,
                               "admitted": len(admitted), "rejected": len(rejected), "errors": len(errors)})
        save_json(self.state_path, state)
        self._audit(state, poll_id, admitted, rejected, errors)
        return PollResult(False, len(admitted), len(rejected), len(errors), self.root)

    def _audit(self, state: dict, poll_id: str, admitted: list[dict], rejected: list[dict], errors: list[dict]) -> None:
        all_records = json.loads(self.records_path.read_text(encoding="utf-8"))
        reasons = Counter(reason for row in rejected for reason in row.get("rejection_reasons", [row.get("reason", "unknown")]))
        audit = {
            "schema_version": 1,
            "status": "PROSPECTIVE_COLLECTION_ONLY_NO_MODEL_OR_OUTCOMES",
            "protocol": "LLM_Only_Prospective_Official_Crypto_Tail_Risk_Protocol_v12.md",
            "poll_id": poll_id,
            "initialized_at": state["initialized_at"],
            "collector_script_sha256": self.script_hash,
            "source_registry": SOURCES,
            "crypto_allowlist": CRYPTO_ALLOWLIST,
            "records_admitted_total": len(all_records),
            "records_admitted_this_poll": len(admitted),
            "records_rejected_this_poll": len(rejected),
            "rejection_reason_counts": dict(sorted(reasons.items())),
            "fetch_errors_this_poll": errors,
            "market_data_accessed": False,
            "model_run": False,
            "backfill_prohibited": True,
            "baseline_urls_excluded": sum(len(urls) for urls in state["baseline_urls"].values()),
            "files": {"state.json": digest(self.state_path.read_bytes()), "records.json": digest(self.records_path.read_bytes())},
        }
        save_json(self.audit_path, audit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("initialize", "poll"))
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    collector = Collector(args.root)
    result = collector.initialize() if args.command == "initialize" else collector.poll()
    print(json.dumps({"initialized": result.initialized, "admitted": result.admitted, "rejected": result.rejected,
                      "fetch_errors": result.fetch_errors, "output_root": str(result.output_root)}))


if __name__ == "__main__":
    main()