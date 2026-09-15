"""
fetch_historical_microstructure.py
===================================
Fetches real historical derivatives microstructure data from Binance Futures API
and computes market_power_score using the IDENTICAL formula as the live system
(backend/app/main.py calculate_sentiment_score + calculate_whale_score).

Data sources:
  Layer 1 - Funding Rate:         /fapi/v1/fundingRate          (available 180+ days)
  Layer 2 - Top Traders L/S:      /futures/data/topLongShortPositionRatio (30 days)
  Layer 2 - Global L/S Ratio:     /futures/data/globalLongShortAccountRatio (30 days)

For days beyond 30 (where L/S API data is unavailable), the whale_score is estimated
using a linear regression fit against funding_rate (strong corr in crypto literature).

Output: results/historical_microstructure.json
  [{
    "symbol": "BTCUSDT",
    "timestamp_ms": 1234567890000,
    "datetime": "2026-01-01T00:00:00Z",
    "funding_rate": 0.01,
    "top_traders_ratio": 1.15,
    "global_ratio": 1.05,
    "sentiment_score": 12.5,
    "whale_score": 40.0,
    "market_power_score": 18.6,
    "data_source": "real"
  }, ...]
"""
from __future__ import annotations

import json
import time
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request
import urllib.parse

# ── ensure project root is on sys.path ──────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

OUTPUT_FILE = _ROOT / 'results' / 'historical_microstructure.json'
BINANCE_FUTURES_BASE = 'https://fapi.binance.com'

# Symbols to fetch (Binance Futures format)
SYMBOLS = ['BTCUSDT', 'XRPUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT',
           'BNBUSDT', 'AVAXUSDT', 'NEARUSDT', 'TRXUSDT']

DAYS = 730  # backtest window


# ─────────────────────────────────────────────────────────────────────────── #
#  Scoring functions — copied verbatim from backend/app/main.py               #
# ─────────────────────────────────────────────────────────────────────────── #

def calculate_sentiment_score(funding_rate: float | None, buy_sell_ratio: float | None = None) -> float:
    """Layer 1: Funding Rate → sentiment_score.
    
    buy_sell_ratio not available historically, so omitted (defaults to neutral).
    funding_rate in bps (basis points).
    """
    if funding_rate is None:
        return 0.0
    # Scale: ±50 bps = ±100 score (same as main.py line 961)
    funding_component = max(-100.0, min(100.0, funding_rate * 2.0))
    return funding_component


def calculate_whale_score(top_traders_ratio: float | None, global_ratio: float | None) -> float:
    """Layer 2: Top Traders L/S + Global L/S → whale_score.
    
    Identical to main.py calculate_whale_score (lines 985-1022).
    """
    whale_score = 0.0

    if top_traders_ratio is not None:
        if top_traders_ratio > 1.3:
            whale_score += 80.0
        elif top_traders_ratio > 1.1:
            whale_score += 40.0
        elif top_traders_ratio < 0.7:
            whale_score -= 80.0
        elif top_traders_ratio < 0.9:
            whale_score -= 40.0

    if global_ratio is not None:
        if global_ratio > 1.1:
            whale_score += 20.0
        elif global_ratio < 0.9:
            whale_score -= 20.0

    return max(-100.0, min(100.0, whale_score))


def compute_market_power_score(sentiment_score: float, whale_score: float) -> float:
    """Final Market Power Score — same formula as main.py line 1141.
    
    Layer 3 (liquidation) = 0.0  (no historical API)
    Layer 4 (news)        = 0.0  (neutral, no historical data)
    
    tech_score = sentiment * 0.35 + whale * 0.35 + liq * 0.30
    """
    liq_score = 0.0   # neutral
    news_contribution = 0.0  # neutral
    tech_score = (sentiment_score * 0.35
                  + whale_score * 0.35
                  + liq_score * 0.30)
    market_power_score = tech_score + news_contribution
    return max(-100.0, min(100.0, market_power_score))


# ─────────────────────────────────────────────────────────────────────────── #
#  Binance API helpers                                                         #
# ─────────────────────────────────────────────────────────────────────────── #

def _get(endpoint: str, params: dict) -> list | dict:
    url = f"{BINANCE_FUTURES_BASE}{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_funding_rates(symbol: str, days: int) -> list[dict]:
    """Fetch all funding rate events for the past `days` days.
    Binance returns up to 1000 records per call; funding is every 8h = 3/day.
    """
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days * 24 * 3600 * 1000
    all_records: list[dict] = []

    # Paginate by fetching in 1000-record batches
    current_start = start_ms
    while current_start < end_ms:
        try:
            data = _get('/fapi/v1/fundingRate', {
                'symbol': symbol,
                'startTime': current_start,
                'endTime': end_ms,
                'limit': 1000,
            })
        except Exception as e:
            print(f"  [WARN] fundingRate fetch error for {symbol}: {e}")
            break

        if not data:
            break

        all_records.extend(data)

        # Advance past the last record
        last_ts = int(data[-1]['fundingTime'])
        current_start = last_ts + 1

        if len(data) < 1000:
            break  # No more records

        time.sleep(0.1)  # Rate limit courtesy

    print(f"  [{symbol}] Fetched {len(all_records)} funding rate records")
    return all_records


def fetch_ls_ratio(symbol: str, period: str = '4h', limit: int = 500) -> list[dict]:
    """Fetch Top Traders Long/Short Position Ratio.
    
    Binance only keeps ~30 days of this data.
    period options: '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d'
    """
    try:
        data = _get('/futures/data/topLongShortPositionRatio', {
            'symbol': symbol,
            'period': period,
            'limit': limit,
        })
        print(f"  [{symbol}] Fetched {len(data)} L/S ratio records")
        return data
    except Exception as e:
        print(f"  [WARN] L/S ratio fetch error for {symbol}: {e}")
        return []


def fetch_global_ls_ratio(symbol: str, period: str = '4h', limit: int = 500) -> list[dict]:
    """Fetch Global Long/Short Account Ratio."""
    try:
        data = _get('/futures/data/globalLongShortAccountRatio', {
            'symbol': symbol,
            'period': period,
            'limit': limit,
        })
        print(f"  [{symbol}] Fetched {len(data)} global L/S records")
        return data
    except Exception as e:
        print(f"  [WARN] Global L/S fetch error for {symbol}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────── #
#  Core builder                                                                #
# ─────────────────────────────────────────────────────────────────────────── #

def build_microstructure(symbol: str, days: int) -> list[dict]:
    """Build full microstructure timeline for one symbol."""
    print(f"\n[{symbol}] Building microstructure data...")

    # --- Fetch raw data ---
    funding_records = fetch_funding_rates(symbol, days)
    ls_records = fetch_ls_ratio(symbol, period='4h', limit=500)
    global_ls_records = fetch_global_ls_ratio(symbol, period='4h', limit=500)

    # --- Index L/S data by timestamp for fast lookup ---
    ls_by_ts: dict[int, float] = {}
    for r in ls_records:
        ts = int(r['timestamp'])
        ls_by_ts[ts] = float(r['longShortRatio'])

    global_ls_by_ts: dict[int, float] = {}
    for r in global_ls_records:
        ts = int(r['timestamp'])
        global_ls_by_ts[ts] = float(r['longShortRatio'])

    # --- Build sorted timestamp list for L/S lookup (nearest) ---
    ls_timestamps = sorted(ls_by_ts.keys())
    global_ls_timestamps = sorted(global_ls_by_ts.keys())

    def nearest_ls(target_ts: int, ts_list: list[int], data: dict) -> float | None:
        """Return value of nearest timestamp <= target_ts."""
        for ts in reversed(ts_list):
            if ts <= target_ts:
                return data[ts]
        return None

    # --- Process each funding rate record as a data point ---
    records: list[dict] = []
    for fr in funding_records:
        ts_ms = int(fr['fundingTime'])
        # Binance fundingRate is already a decimal (e.g. 0.0001 = 1 bps)
        # Convert to bps: multiply by 10000
        funding_bps = float(fr['fundingRate']) * 10_000

        # Get nearest L/S ratios
        top_traders_ratio = nearest_ls(ts_ms, ls_timestamps, ls_by_ts)
        global_ratio = nearest_ls(ts_ms, global_ls_timestamps, global_ls_by_ts)

        # Do not replace missing historical positioning with a funding-derived
        # proxy. A research backtest must record an unavailable observation.
        if top_traders_ratio is None or global_ratio is None:
            continue

        # Compute scores using live-system formulas
        sentiment_score = calculate_sentiment_score(funding_bps)
        whale_score = calculate_whale_score(top_traders_ratio, global_ratio)
        market_power_score = compute_market_power_score(sentiment_score, whale_score)

        records.append({
            'symbol': symbol,
            'timestamp_ms': ts_ms,
            'datetime': datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(),
            'funding_rate_bps': round(funding_bps, 4),
            'top_traders_ratio': round(top_traders_ratio, 4),
            'global_ratio': round(global_ratio, 4),
            'sentiment_score': round(sentiment_score, 2),
            'whale_score': round(whale_score, 2),
            'market_power_score': round(market_power_score, 2),
            'data_source': 'real',
        })

    # Sort by time
    records.sort(key=lambda x: x['timestamp_ms'])
    real_count = sum(1 for r in records if r['data_source'] == 'real')
    synthetic_count = len(records) - real_count
    print(f"  [{symbol}] Total records: {len(records)} "
          f"(real L/S: {real_count}, synthetic L/S: {synthetic_count})")
    return records


# ─────────────────────────────────────────────────────────────────────────── #
#  Main                                                                        #
# ─────────────────────────────────────────────────────────────────────────── #

def main() -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    all_data: dict[str, list[dict]] = {}

    for symbol in SYMBOLS:
        try:
            records = build_microstructure(symbol, DAYS)
            all_data[symbol] = records
        except Exception as e:
            print(f"[ERROR] {symbol}: {e}")
            all_data[symbol] = []

        time.sleep(0.5)  # Be polite to Binance API

    # Write output
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print(f"\n[DONE] Saved to {OUTPUT_FILE}")

    # Print summary stats
    for sym, recs in all_data.items():
        if recs:
            scores = [r['market_power_score'] for r in recs]
            real = sum(1 for r in recs if r['data_source'] == 'real')
            print(f"  {sym}: {len(recs)} records | "
                  f"score range [{min(scores):.1f}, {max(scores):.1f}] | "
                  f"avg={sum(scores)/len(scores):.1f} | "
                  f"real L/S: {real}/{len(recs)}")


if __name__ == '__main__':
    main()
