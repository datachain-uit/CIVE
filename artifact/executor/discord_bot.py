"""discord_bot.py — Discord webhook alerts for AI Quant Agent.

Sends rich embedded messages to a Discord channel for:
  - Trade opened / closed
  - On-chain proof committed (Mantlescan link)
  - Whale alert (large MNT/USDT moves on Mantle)
  - Daily performance report
  - System startup / shutdown

Usage:
  python executor/discord_bot.py --test-webhook
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / '.env')

logger = logging.getLogger('discord_bot')

# ── Colour palette ────────────────────────────────────────────────────────────
COLOR_GREEN   = 0x00D26A   # trade win / long
COLOR_RED     = 0xFF4D4D   # trade loss / short
COLOR_ORANGE  = 0xFF9F1C   # warning / whale alert
COLOR_BLUE    = 0x3A86FF   # info / on-chain proof
COLOR_PURPLE  = 0x9B5DE5   # Mantle / daily report
COLOR_YELLOW  = 0xFFBE0B   # startup
COLOR_GREY    = 0x6C757D   # neutral watch decision

MANTLESCAN_BASE = 'https://explorer.sepolia.mantle.xyz'


def _get_webhook_url() -> str:
    url = os.getenv('DISCORD_WEBHOOK_URL', '')
    if not url:
        raise RuntimeError('DISCORD_WEBHOOK_URL not set in .env')
    return url


def send_embed(
    title: str,
    description: str = '',
    color: int = COLOR_BLUE,
    fields: list[dict[str, Any]] | None = None,
    footer: str = 'Mantle AI Quant Agent',
    timestamp: bool = True,
    webhook_url: str | None = None,
) -> bool:
    """Send a Discord embed message via webhook. Returns True on success."""
    url = webhook_url or _get_webhook_url()

    embed: dict[str, Any] = {
        'title': title,
        'description': description,
        'color': color,
        'footer': {'text': footer},
    }
    if timestamp:
        embed['timestamp'] = datetime.now(timezone.utc).isoformat()
    if fields:
        embed['fields'] = fields

    payload = {'embeds': [embed]}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning('Discord webhook failed: %s', exc)
        return False


# ── Specific alert helpers ────────────────────────────────────────────────────

def alert_trade_opened(
    symbol: str,
    side: str,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    quantity: float,
    leverage: int,
    entry_type: str = 'Market',
    rr_ratio: float = 0.0,
    risk_pct: float = 3.0,
    proof_tx: str | None = None,
) -> bool:
    emoji = '📈' if side.lower() == 'buy' else '📉'
    color = COLOR_GREEN if side.lower() == 'buy' else COLOR_RED
    side_label = 'LONG 🟢' if side.lower() == 'buy' else 'SHORT 🔴'

    fields = [
        {'name': 'Symbol', 'value': symbol, 'inline': True},
        {'name': 'Side', 'value': side_label, 'inline': True},
        {'name': 'Entry', 'value': f'`{entry_price:.4f}` ({entry_type})', 'inline': True},
        {'name': 'Stop Loss', 'value': f'`{sl_price:.4f}`', 'inline': True},
        {'name': 'Take Profit', 'value': f'`{tp_price:.4f}`', 'inline': True},
        {'name': 'R:R', 'value': f'`{rr_ratio:.2f}:1`', 'inline': True},
        {'name': 'Qty', 'value': f'`{quantity:.6f}`', 'inline': True},
        {'name': 'Leverage', 'value': f'`{leverage}x`', 'inline': True},
        {'name': 'Risk', 'value': f'`{risk_pct:.1f}%`', 'inline': True},
    ]
    if proof_tx:
        scan_url = f'{MANTLESCAN_BASE}/tx/{proof_tx}'
        fields.append({'name': '🔗 On-Chain Proof', 'value': f'[View on Mantlescan]({scan_url})', 'inline': False})

    return send_embed(
        title=f'{emoji} TRADE OPENED — {side_label}',
        description=f'New position opened on **{symbol}**',
        color=color,
        fields=fields,
    )


def alert_trade_closed(
    symbol: str,
    side: str,
    entry_price: float,
    exit_price: float,
    pnl_usdt: float,
    pnl_pct: float,
    outcome: str = 'TP',
    proof_tx: str | None = None,
) -> bool:
    won = pnl_usdt >= 0
    emoji = '✅' if won else '❌'
    color = COLOR_GREEN if won else COLOR_RED
    pnl_sign = '+' if pnl_usdt >= 0 else ''

    fields = [
        {'name': 'Symbol', 'value': symbol, 'inline': True},
        {'name': 'Side', 'value': side.upper(), 'inline': True},
        {'name': 'Outcome', 'value': outcome, 'inline': True},
        {'name': 'Entry', 'value': f'`{entry_price:.4f}`', 'inline': True},
        {'name': 'Exit', 'value': f'`{exit_price:.4f}`', 'inline': True},
        {'name': 'PnL', 'value': f'`{pnl_sign}{pnl_usdt:.2f} USDT ({pnl_sign}{pnl_pct:.2f}%)`', 'inline': True},
    ]
    if proof_tx:
        scan_url = f'{MANTLESCAN_BASE}/tx/{proof_tx}'
        fields.append({'name': '🔗 Outcome Proof', 'value': f'[View on Mantlescan]({scan_url})', 'inline': False})

    return send_embed(
        title=f'{emoji} TRADE CLOSED — {outcome}',
        description=f'Position on **{symbol}** has been closed',
        color=color,
        fields=fields,
    )


def alert_onchain_proof(
    signal_hash: str,
    tx_hash: str,
    agent_id: str,
    symbol: str,
    decision: str,
) -> bool:
    scan_url = f'{MANTLESCAN_BASE}/tx/{tx_hash}'
    short_hash = f'{signal_hash[:8]}...{signal_hash[-6:]}'

    return send_embed(
        title='🔗 ON-CHAIN PROOF COMMITTED',
        description=f'Signal hash committed to **Mantle** blockchain',
        color=COLOR_PURPLE,
        fields=[
            {'name': 'Agent', 'value': agent_id, 'inline': True},
            {'name': 'Symbol', 'value': symbol, 'inline': True},
            {'name': 'Decision', 'value': decision, 'inline': True},
            {'name': 'Signal Hash', 'value': f'`{short_hash}`', 'inline': False},
            {'name': 'Transaction', 'value': f'[{tx_hash[:16]}...]({scan_url})', 'inline': False},
        ],
    )


def alert_whale_detected(
    amount_usd: float,
    token: str,
    direction: str,
    from_addr: str,
    to_addr: str,
    onchain_score_before: float,
    onchain_score_after: float,
    bot_action: str = 'Monitoring',
) -> bool:
    bullish = onchain_score_after > onchain_score_before
    color = COLOR_GREEN if bullish else COLOR_ORANGE
    direction_emoji = '🐂' if bullish else '🐻'

    return send_embed(
        title=f'🐋 WHALE ALERT — {token}',
        description=f'Large **{token}** movement detected on Mantle chain',
        color=color,
        fields=[
            {'name': 'Amount', 'value': f'`${amount_usd:,.0f}` {token}', 'inline': True},
            {'name': 'Direction', 'value': direction, 'inline': True},
            {'name': 'Sentiment', 'value': direction_emoji, 'inline': True},
            {'name': 'From', 'value': f'`{from_addr[:12]}...`', 'inline': True},
            {'name': 'To', 'value': f'`{to_addr[:12]}...`', 'inline': True},
            {'name': 'On-Chain Score', 'value': f'`{onchain_score_before:+.1f}` → `{onchain_score_after:+.1f}`', 'inline': True},
            {'name': 'Bot Response', 'value': bot_action, 'inline': False},
        ],
    )


def alert_daily_report(
    date_str: str,
    pnl_today: float,
    pnl_pct: float,
    trades_count: int,
    wins: int,
    losses: int,
    proofs_committed: int,
    gas_spent_mnt: float,
    starting_balance: float,
    ending_balance: float,
) -> bool:
    won = pnl_today >= 0
    color = COLOR_GREEN if won else COLOR_RED
    pnl_sign = '+' if pnl_today >= 0 else ''
    win_rate = (wins / max(trades_count, 1)) * 100

    return send_embed(
        title=f'📊 DAILY REPORT — {date_str}',
        description='End-of-day performance summary for AI Quant Agent',
        color=color,
        fields=[
            {'name': '💰 PnL Today', 'value': f'`{pnl_sign}{pnl_today:.2f} USDT ({pnl_sign}{pnl_pct:.2f}%)`', 'inline': True},
            {'name': '📈 Balance', 'value': f'`{starting_balance:.2f}` → `{ending_balance:.2f} USDT`', 'inline': True},
            {'name': '🎯 Trades', 'value': f'`{trades_count}` ({wins}W / {losses}L  WR={win_rate:.0f}%)', 'inline': True},
            {'name': '🔗 On-Chain Proofs', 'value': f'`{proofs_committed}` committed', 'inline': True},
            {'name': '⛽ Gas Spent', 'value': f'`{gas_spent_mnt:.4f} MNT`', 'inline': True},
            {'name': '🌐 Chain', 'value': 'Mantle Sepolia', 'inline': True},
        ],
        footer='Mantle AI Quant Agent | Daily Summary',
    )


def alert_risk_triggered(reason: str, symbol: str, action: str = 'All positions closed') -> bool:
    return send_embed(
        title='🛑 RISK TRIGGER FIRED',
        description=f'**{reason}**\nAction taken: {action}',
        color=COLOR_RED,
        fields=[
            {'name': 'Symbol', 'value': symbol, 'inline': True},
            {'name': 'Action', 'value': action, 'inline': True},
        ],
    )


def alert_system_startup(mode: str, exchange: str, symbol: str) -> bool:
    return send_embed(
        title='🚀 BOT STARTED',
        description='AI Quant Agent is now active and scanning markets',
        color=COLOR_YELLOW,
        fields=[
            {'name': 'Mode', 'value': mode, 'inline': True},
            {'name': 'Exchange', 'value': exchange, 'inline': True},
            {'name': 'Symbol', 'value': symbol, 'inline': True},
            {'name': 'On-Chain', 'value': 'Mantle Sepolia', 'inline': True},
        ],
    )


# ── CLI test ──────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    parser = argparse.ArgumentParser(description='Discord webhook alert bot for AI Quant Agent')
    parser.add_argument('--test-webhook', action='store_true', help='Send a test message to Discord')
    args = parser.parse_args()

    if args.test_webhook:
        print('Sending test messages to Discord...')

        ok = send_embed(
            title='[OK] Webhook Test - AI Quant Agent',
            description='Discord integration is working correctly!\n\n'
                        '**Mantle AI Quant Agent** is online and ready to send alerts.',
            color=COLOR_PURPLE,
            fields=[
                {'name': 'Chain', 'value': 'Mantle Sepolia (Chain ID: 5003)', 'inline': True},
                {'name': 'Contract', 'value': f'`{os.getenv("AGENT_PROOF_CONTRACT", "Not set")[:20]}...`', 'inline': True},
                {'name': 'Agent ID', 'value': os.getenv('AGENT_ID', 'vibe-agent-xrp'), 'inline': True},
            ],
        )
        print('[OK] Test embed sent!' if ok else '[FAIL] Failed to send test embed')

        time.sleep(1)
        ok2 = alert_trade_opened(
            symbol='XRP/USDT',
            side='buy',
            entry_price=2.3420,
            sl_price=2.2800,
            tp_price=2.4500,
            quantity=42.5,
            leverage=5,
            entry_type='Limit@FVG',
            rr_ratio=1.74,
            risk_pct=3.0,
        )
        print('[OK] Trade alert sent!' if ok2 else '[FAIL] Failed to send trade alert')

        time.sleep(1)
        ok3 = alert_whale_detected(
            amount_usd=1_200_000,
            token='MNT',
            direction='CEX Outflow - Accumulation',
            from_addr='0x1234567890abcdef',
            to_addr='0xabcdef1234567890',
            onchain_score_before=-2.0,
            onchain_score_after=4.5,
            bot_action='Shifted bias BULLISH. Loosening SL by 10%.',
        )
        print('[OK] Whale alert sent!' if ok3 else '[FAIL] Failed to send whale alert')

        time.sleep(1)
        today = datetime.now(timezone.utc).strftime('%b %d, %Y')
        ok4 = alert_daily_report(
            date_str=today,
            pnl_today=124.50,
            pnl_pct=3.2,
            trades_count=3,
            wins=2,
            losses=1,
            proofs_committed=3,
            gas_spent_mnt=0.0023,
            starting_balance=3890.0,
            ending_balance=4014.50,
        )
        print('[OK] Daily report sent!' if ok4 else '[FAIL] Failed to send daily report')


if __name__ == '__main__':
    main()
