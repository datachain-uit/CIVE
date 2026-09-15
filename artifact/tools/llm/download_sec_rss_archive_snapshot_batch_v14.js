#!/usr/bin/env node
/* Download one bounded, resumable batch of predeclared Internet Archive RSS snapshots. */

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..", "..");
const sourceDir = path.join(root, "paper", "input", "references", "source_artifacts", "sec_rss_internet_archive_v14");
const snapshotDir = path.join(sourceDir, "rss_snapshots");
const cdxPath = path.join(sourceDir, "cdx_index.json");
const rssUrl = "https://www.sec.gov/news/pressreleases.rss";
const headers = { "User-Agent": "KLTN-sec-rss-provenance-audit/1.0 (research; contact@example.edu)", "Accept": "application/xml, application/json, text/xml" };

function sleep(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}

async function get(url) {
  let lastError;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const response = await fetch(url, { headers, signal: AbortSignal.timeout(45000) });
      const bytes = Buffer.from(await response.arrayBuffer());
      if (response.status === 200) return { status: 200, bytes };
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await sleep(1000 * (attempt + 1));
  }
  return { status: 599, bytes: Buffer.from(String(lastError), "utf8") };
}

async function main() {
  const values = Object.fromEntries(process.argv.slice(2).map(value => value.split("=", 2)));
  const start = Number(values["--start"] || 0);
  const limit = Number(values["--limit"] || 10);
  if (!Number.isInteger(start) || !Number.isInteger(limit) || start < 0 || limit < 1) throw new Error("--start and --limit must be valid integers");
  if (!fs.existsSync(cdxPath)) throw new Error("missing pinned CDX index; do not construct a batch without it");
  const rows = JSON.parse(fs.readFileSync(cdxPath, "utf8")).rows;
  if (!Array.isArray(rows)) throw new Error("pinned CDX index has no rows array");
  fs.mkdirSync(snapshotDir, { recursive: true });
  const results = [];
  for (const row of rows.slice(start, start + limit)) {
    const target = path.join(snapshotDir, `${row.archive_capture}.xml`);
    if (fs.existsSync(target)) {
      results.push({ archive_capture: row.archive_capture, state: "existing" });
      continue;
    }
    const response = await get(`https://web.archive.org/web/${row.archive_capture}id_/${rssUrl}`);
    if (response.status !== 200) {
      results.push({ archive_capture: row.archive_capture, state: "fetch_failed", http_status: response.status });
      continue;
    }
    const temporary = `${target}.tmp`;
    fs.writeFileSync(temporary, response.bytes);
    fs.renameSync(temporary, target);
    results.push({ archive_capture: row.archive_capture, state: "downloaded", bytes: response.bytes.length });
    await sleep(500);
  }
  console.log(JSON.stringify({ start, requested: Math.min(limit, Math.max(0, rows.length - start)), total: rows.length, results }));
}

main().catch(error => { console.error(error.stack || error.message); process.exit(1); });
