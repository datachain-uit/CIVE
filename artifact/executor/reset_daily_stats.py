from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import redis

try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / '.env')
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Reset executor daily live stats baseline.')
    parser.add_argument('--start-balance', type=float, required=True, help='New daily start balance in USDT.')
    parser.add_argument('--date', default=None, help='VN date YYYY-MM-DD. Default: today in Asia/Ho_Chi_Minh.')
    parser.add_argument('--redis-url', default=os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
    parser.add_argument('--keep-consecutive-losses', action='store_true', help='Keep current consecutive_losses instead of resetting to 0.')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    vn_tz = ZoneInfo('Asia/Ho_Chi_Minh')
    date_str = args.date or datetime.now(vn_tz).strftime('%Y-%m-%d')
    redis_key = f'daily_live_stats:{date_str}'
    fallback_file = Path(__file__).resolve().parent / 'daily_stats_fallback.json'

    client = redis.Redis.from_url(args.redis_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)

    consecutive_losses = '0'
    if args.keep_consecutive_losses:
        try:
            consecutive_losses = str(client.hget(redis_key, 'consecutive_losses') or '0')
        except Exception:
            consecutive_losses = '0'

    mapping = {
        'trades_count': '0',
        'wins_count': '0',
        'losses_count': '0',
        'realized_pnl': '0.0',
        'start_balance': str(args.start_balance),
        'consecutive_losses': consecutive_losses,
    }

    client.hset(redis_key, mapping=mapping)
    client.expire(redis_key, 36 * 3600)

    fallback_payload = {
        'date': date_str,
        'trades_count': 0,
        'wins_count': 0,
        'losses_count': 0,
        'realized_pnl': 0.0,
        'start_balance': args.start_balance,
        'consecutive_losses': int(float(consecutive_losses)),
    }
    temp_file = fallback_file.with_suffix(fallback_file.suffix + '.tmp')
    temp_file.write_text(json.dumps(fallback_payload, indent=2, ensure_ascii=False), encoding='utf-8')
    temp_file.replace(fallback_file)

    print(f'Reset {redis_key}')
    print(f'Fallback file: {fallback_file}')
    print(f'start_balance={args.start_balance:.2f} realized_pnl=0.0 trades=0 consecutive_losses={consecutive_losses}')


if __name__ == '__main__':
    main()
