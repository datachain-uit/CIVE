#!/usr/bin/env node
/* Download a bounded, resumable batch of predeclared Internet Archive RSS snapshots. */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const root = path.resolve(__dirname, "..", "..");
const sourceDir = path.join(root, "paper", "input", "references", "source_artifacts", "sec_rss_internet_archive_v14");
const snapshotDir = path.join(sourceDir, "rss_snapshots");
const cdxPath = path.join(sourceDir, "cdx_index.json");
const statusPath = path.join(sourceDir, "download_status.json");
const cdxUrl = "https://web.archive.org/cdx/search/cdx?url=www.sec.gov%2Fnews%2Fpressreleases.rss&output=json&filter=statuscode:200&fl=timestamp,digest,length&collapse=timestamp:8&from=2021&to=2026";
const rssUrl = "https://www.sec.gov/news/pressreleases.rss";
const headers = { "User-Agent": "KLTN-sec-rss-provenance-audit/1.0 (research; contact@example.edu)", "Accept": "application/xml, application/json, text/xml" };

function sha256(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function stableJson(value) {
  return JSON.stringify(value, Object.keys(value).sort(), 2) + "\n";
}

function sleep(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}

async function get(url) {
  let lastError;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const response = await fetch(url, { headers, signal: AbortSignal.timeout(45000) });
      const bytes = Buffer.from(await response.arrayBuffer());
      if (response.status < 500 && response.status !== 429) return { status: response.status, bytes };
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await sleep(1000 * (attempt + 1));
  }
  return { status: 599, bytes: Buffer.from(String(lastError), "utf8") };
}

async function loadRows() {
  if (fs.existsSync(cdxPath)) return JSON.parse(fs.readFileSync(cdxPath, "utf8")).rows;
  const response = await get(cdxUrl);
  if (response.status !== 200) throw new Error(`CDX unavailable: HTTP ${response.status}`);
  const parsed = JSON.parse(response.bytes.toString("utf8"));
  if (!Array.isArray(parsed) || JSON.stringify(parsed[0]) !== JSON.stringify(["timestamp", "digest", "length"])) {
    throw new Error("unexpected CDX schema");
  }
  const rows = parsed.slice(1).map(([archive_capture, digest, length]) => ({ archive_capture, digest, length }));
  const payload = {
    rows,
    provenance: {
      url: cdxUrl,
      http_status: 200,
      bytes: response.bytes.length,
      sha256: sha256(response.bytes),
      records: rows.length,
      fetched_at_utc: new Date().toISOString()
    }
  };
  fs.mkdirSync(sourceDir, { recursive: true });
  fs.writeFileSync(cdxPath, stableJson(payload), "utf8");
  return rows;
}

function replayUrl(capture) {
  return `https://web.archive.org/web/${capture}id_/${rssUrl}`;
}

async function main() {
  const args = new Map(process.argv.slice(2).map(part => part.split("=", 2)));
  const start = Number(args.get("--start") || 0);
  const limit = Number(args.get("--limit") || 12);
  if (!Number.isInteger(start) || !Number.isInteger(limit) || start < 0 || limit < 1) throw new Error("--start and --limit must be non-negative integers");
  const rows = await loadRows();
  const batch = rows.slice(start, start + limit);
  fs.mkdirSync(snapshotDir, { recursive: true });
  const status = fs.existsSync(statusPath) ? JSON.parse(fs.readFileSync(statusPath, "utf8")) : { snapshots: {} };
  for (const row of batch) {
    const target = path.join(snapshotDir, `${row.archive_capture}.xml`);
    if (fs.existsSync(target)) {
      status.snapshots[row.archive_capture] = { state: "existing", bytes: fs.statSync(target).size, sha256: sha256(fs.readFileSync(target)) };
      continue;
    }
    const response = await get(replayUrl(row.archive_capture));
    if (response.status !== 200) {
      status.snapshots[row.archive_capture] = { state: "fetch_failed", http_status: response.status, error_sha256: sha256(response.bytes) };
      continue;
    }
    const temporary = `${target}.tmp`;
    fs.writeFileSync(temporary, response.bytes);
    fs.renameSync(temporary, target);
    status.snapshots[row.archive_capture] = { state: "downloaded", bytes: response.bytes.length, sha256: sha256(response.bytes) };
    await sleep(500);
  }
  status.updated_at_utc = new Date().toISOString();
  fs.writeFileSync(statusPath, stableJson(status), "utf8");
  const completed = Object.values(status.snapshots).filter(item => item.state === "downloaded" || item.state === "existing").length;
  console.log(JSON.stringify({ batch_start: start, batch_size: batch.length, known_snapshots: completed, total_snapshots: rows.length }));
}

main().catch(error => { console.error(error.stack || error.message); process.exit(1); });
