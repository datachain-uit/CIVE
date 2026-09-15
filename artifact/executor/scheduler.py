from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backtester import run_daily_strategist
from pathlib import Path

# Load .env for scheduler runtime
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / '.env')
except Exception:
    pass


logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
)
logger = logging.getLogger('scheduler')


def _resolve_schedule() -> tuple[int, int, str]:
    if os.getenv('DAILY_STRATEGIST_UTC', 'true').lower() in {'1', 'true', 'yes'}:
        hour = int(os.getenv('DAILY_STRATEGIST_HOUR', '0'))
        minute = int(os.getenv('DAILY_STRATEGIST_MINUTE', '1'))
        return hour, minute, 'UTC'

    hour = int(os.getenv('DAILY_STRATEGIST_HOUR', '8'))
    minute = int(os.getenv('DAILY_STRATEGIST_MINUTE', '0'))
    return hour, minute, 'local'


def run_daily_job() -> dict[str, Any]:
    symbol = os.getenv('DAILY_STRATEGIST_SYMBOL', os.getenv('BACKTEST_SYMBOL', 'BTC/USDT'))
    days = int(os.getenv('DAILY_STRATEGIST_DAYS', '14'))
    balance = float(os.getenv('DAILY_STRATEGIST_BALANCE', os.getenv('BACKTEST_BALANCE', '10000')))
    outlook = run_daily_strategist(symbol=symbol, days=days, balance=balance)
    logger.info('Daily strategist stored outlook for %s: %s', symbol, outlook.get('market_regime'))
    return outlook


def build_scheduler() -> BackgroundScheduler:
    hour, minute, timezone_label = _resolve_schedule()
    scheduler = BackgroundScheduler(timezone=timezone.utc if timezone_label == 'UTC' else None)
    scheduler.add_job(
        run_daily_job,
        CronTrigger(hour=hour, minute=minute, timezone=timezone.utc if timezone_label == 'UTC' else None),
        id='daily_strategist',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    return scheduler


def main() -> None:
    parser = argparse.ArgumentParser(description='Vibe-Trading daily strategist scheduler')
    parser.add_argument('--run-once', action='store_true', help='Run the daily strategist immediately and exit')
    args = parser.parse_args()

    if args.run_once:
        outlook = run_daily_job()
        print(json.dumps(outlook, indent=2, default=str))
        return

    scheduler = build_scheduler()
    scheduler.start()
    logger.info('Daily strategist scheduler started')

    def _shutdown(*_: Any) -> None:
        logger.info('Shutting down scheduler')
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _shutdown()


if __name__ == '__main__':
    main()
