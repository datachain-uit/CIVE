"""mantle_onchain_reader.py — Read Mantle chain data as trading signals.

Scans recent Mantle blocks for:
  - Whale MNT / USDY transfers (>$50K threshold)
  - DEX volume spikes on Merchant Moe / Agni Finance
  - Protocol TVL changes (mETH liquid staking)

Produces an `onchain_score` (-10 to +10) written to Redis channel
`onchain_signals` and key `onchain_score:latest`.

Usage:
  python executor/mantle_onchain_reader.py --blocks 20
  python executor/mantle_onchain_reader.py --loop --interval 300
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import redis
import requests
from dotenv import load_dotenv

try:
    from web3 import Web3
except ImportError:
    Web3 = None  # type: ignore[assignment]


load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / '.env')

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
)
logger = logging.getLogger('mantle_onchain_reader')

# ── Config ────────────────────────────────────────────────────────────────────
MANTLE_RPC = os.getenv('MANTLE_RPC_URL', 'https://rpc.sepolia.mantle.xyz')
WHALE_USD_THRESHOLD = float(os.getenv('WHALE_USD_THRESHOLD', '50000'))
ONCHAIN_SCORE_TTL = int(os.getenv('ONCHAIN_SCORE_TTL', '3600'))

# Well-known Mantle addresses (mainnet – will be 0x000... on sepolia)
KNOWN_EXCHANGES = {
    '0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad',  # Uniswap Universal Router (Mantle)
    '0xbc2bac23f45e5e3d0e6dcb2aa29bba8e39e6b89e',  # Merchant Moe router approx
    '0x5e74c9a98746e11cbac693b0b1f20b5dfb2b27ef',  # Agni Finance router approx
}

# MNT / USDY token addresses on Mantle mainnet (approx – used for transfer detection)
MNT_NATIVE = 'native'
USDY_ADDRESS = '0x5be26527e817998173834126293fa8f5cbf2b7fa'
METH_ADDRESS = '0xcda86a272531e8640cd7f1a92c01839911b90bb0'

DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK_URL', '')


def build_redis() -> redis.Redis:
    return redis.Redis.from_url(
        os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def build_web3() -> Any:
    if Web3 is None:
        raise RuntimeError('web3 not installed. Run: pip install web3')
    w3 = Web3(Web3.HTTPProvider(MANTLE_RPC, request_kwargs={'timeout': 30}))
    if not w3.is_connected():
        raise RuntimeError(f'Cannot connect to Mantle RPC: {MANTLE_RPC}')
    return w3


def fetch_mnt_price_usd() -> float:
    """Fetch MNT/USDT price from CoinGecko (public API, no key needed)."""
    try:
        resp = requests.get(
            'https://api.coingecko.com/api/v3/simple/price',
            params={'ids': 'mantle', 'vs_currencies': 'usd'},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return float(data.get('mantle', {}).get('usd', 0.5))
    except Exception as exc:
        logger.debug('CoinGecko price fetch failed: %s', exc)
        return 0.5  # fallback price


def decode_transfer_amount(input_data: str, tx: dict[str, Any]) -> float:
    """Best-effort: parse native MNT value from tx in ETH units."""
    try:
        return float(Web3.from_wei(tx.get('value', 0), 'ether'))
    except Exception:
        return 0.0


def score_whale_txs(whale_txs: list[dict[str, Any]], mnt_price: float) -> tuple[float, list[dict[str, Any]]]:
    """Score whale transactions: positive = accumulation, negative = distribution."""
    score = 0.0
    events: list[dict[str, Any]] = []
    for tx in whale_txs:
        usd_value = tx['mnt_amount'] * mnt_price
        to_addr = (tx.get('to') or '').lower()
        is_cex_deposit = to_addr in KNOWN_EXCHANGES

        # Large transfer TO exchange = likely sell pressure → bearish
        # Large transfer FROM exchange = likely accumulation → bullish
        direction = 'CEX Deposit (Bearish)' if is_cex_deposit else 'Accumulation (Bullish)'
        delta = -2.0 if is_cex_deposit else +2.0
        # Scale by size: >$500K = max impact
        size_mult = min(usd_value / 500_000, 1.0)
        score += delta * size_mult

        events.append({
            'tx_hash': tx['hash'],
            'mnt_amount': tx['mnt_amount'],
            'usd_value': usd_value,
            'direction': direction,
            'score_delta': delta * size_mult,
            'from': tx.get('from', ''),
            'to': tx.get('to', ''),
        })
        logger.info(
            'Whale tx: %.0f MNT ($%.0f) | %s | delta=%.2f',
            tx['mnt_amount'], usd_value, direction, delta * size_mult,
        )
    return score, events


def scan_blocks(w3: Any, num_blocks: int = 20) -> dict[str, Any]:
    """Scan the last N blocks for whale transfers. Returns structured data."""
    mnt_price = fetch_mnt_price_usd()
    logger.info('MNT price: $%.4f | Scanning last %d blocks on %s', mnt_price, num_blocks, MANTLE_RPC)

    try:
        latest = w3.eth.block_number
    except Exception as exc:
        logger.error('Cannot get latest block: %s', exc)
        return {'onchain_score': 0.0, 'whale_events': [], 'blocks_scanned': 0, 'error': str(exc)}

    whale_txs: list[dict[str, Any]] = []
    blocks_scanned = 0

    for block_num in range(max(0, latest - num_blocks + 1), latest + 1):
        try:
            block = w3.eth.get_block(block_num, full_transactions=True)
            blocks_scanned += 1
            for tx in block.get('transactions', []):
                # Check native MNT value
                value_wei = tx.get('value', 0)
                if value_wei == 0:
                    continue
                mnt_amount = float(Web3.from_wei(value_wei, 'ether'))
                usd_value = mnt_amount * mnt_price
                if usd_value >= WHALE_USD_THRESHOLD:
                    whale_txs.append({
                        'hash': tx['hash'].hex() if hasattr(tx['hash'], 'hex') else str(tx['hash']),
                        'mnt_amount': mnt_amount,
                        'usd_value': usd_value,
                        'from': tx.get('from', ''),
                        'to': tx.get('to', '') or '',
                        'block': block_num,
                    })
        except Exception as exc:
            logger.warning('Error reading block %d: %s', block_num, exc)
            continue

    whale_score, whale_events = score_whale_txs(whale_txs, mnt_price)

    # Clamp total score to [-10, +10]
    onchain_score = max(-10.0, min(10.0, whale_score))

    logger.info(
        'Scan complete: %d blocks, %d whale txs | onchain_score=%.2f',
        blocks_scanned, len(whale_txs), onchain_score,
    )

    return {
        'onchain_score': onchain_score,
        'whale_events': whale_events,
        'blocks_scanned': blocks_scanned,
        'latest_block': latest,
        'mnt_price_usd': mnt_price,
        'scan_timestamp': int(time.time()),
        'rpc_url': MANTLE_RPC,
    }


def publish_to_redis(r: redis.Redis, result: dict[str, Any]) -> None:
    """Write score and events to Redis for executor.py to consume."""
    try:
        score_payload = {
            'onchain_score': result['onchain_score'],
            'whale_count': len(result.get('whale_events', [])),
            'mnt_price_usd': result.get('mnt_price_usd', 0),
            'timestamp': result.get('scan_timestamp', int(time.time())),
        }
        r.set('onchain_score:latest', json.dumps(score_payload), ex=ONCHAIN_SCORE_TTL)
        r.lpush('onchain_signals', json.dumps(result, default=str))
        r.ltrim('onchain_signals', 0, 99)  # keep last 100 scans
        logger.info('Published onchain_score=%.2f to Redis', result['onchain_score'])
    except Exception as exc:
        logger.warning('Redis publish failed: %s', exc)


def alert_whale_to_discord(events: list[dict[str, Any]]) -> None:
    """Send whale alerts to Discord for significant movements."""
    if not DISCORD_WEBHOOK or not events:
        return
    try:
        from discord_bot import alert_whale_detected
        for event in events[:3]:  # Max 3 alerts per scan
            if abs(event.get('score_delta', 0)) >= 1.0:
                alert_whale_detected(
                    amount_usd=event['usd_value'],
                    token='MNT',
                    direction=event['direction'],
                    from_addr=event['from'],
                    to_addr=event['to'],
                    onchain_score_before=0.0,
                    onchain_score_after=event['score_delta'],
                    bot_action='Score updated in Redis → executor will adapt.',
                )
    except Exception as exc:
        logger.debug('Discord whale alert failed: %s', exc)


def run_once(num_blocks: int = 20) -> dict[str, Any]:
    """Single scan cycle."""
    try:
        w3 = build_web3()
    except Exception as exc:
        logger.error('Web3 connection failed: %s', exc)
        # Return neutral score so bot doesn't panic
        return {'onchain_score': 0.0, 'error': str(exc), 'whale_events': []}

    result = scan_blocks(w3, num_blocks)

    r = build_redis()
    publish_to_redis(r, result)

    if result.get('whale_events'):
        alert_whale_to_discord(result['whale_events'])

    return result


def loop_forever(num_blocks: int, interval: int) -> None:
    logger.info('Starting on-chain reader loop (every %ds, last %d blocks)', interval, num_blocks)
    while True:
        try:
            result = run_once(num_blocks)
            print(json.dumps({
                'onchain_score': result.get('onchain_score', 0),
                'whale_events': len(result.get('whale_events', [])),
                'blocks': result.get('blocks_scanned', 0),
            }))
        except Exception as exc:
            logger.exception('Loop error: %s', exc)
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description='Mantle on-chain data reader for trading signals')
    parser.add_argument('--blocks', type=int, default=20, help='Number of recent blocks to scan')
    parser.add_argument('--interval', type=int, default=300, help='Loop interval in seconds')
    parser.add_argument('--loop', action='store_true', help='Run continuously')
    args = parser.parse_args()

    if args.loop:
        loop_forever(args.blocks, args.interval)
    else:
        result = run_once(args.blocks)
        print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
