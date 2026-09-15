"""
Backtest Report — Vibe Strategy (Executor Logic)
=================================================
Chạy backtest 90 ngày với logic executor hiện tại (VibeTradingSignalGenerator)
Báo cáo chi tiết: tổng quan, từng ngày, từng tháng, số lệnh, PnL.

Dùng: python executor/backtest_report.py [--symbol BTC/USDT] [--days 90] [--balance 10000]
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Tự động nạp .env ─────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / '.env')
except Exception:
    pass

# ── Import từ backtester.py hiện có ─────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtester import (
    Backtester,
    BacktestResult,
    TradeResult,
    VibeTradingSignalGenerator,
    build_exchange,
    fetch_ohlcv_with_retry,
    normalize_derivative_symbol,
    to_candles,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: ANSI colors (tắt khi redirect sang file)
# ═══════════════════════════════════════════════════════════════════════════════
USE_COLOR = sys.stdout.isatty()

def c(text: str, code: str) -> str:
    if not USE_COLOR:
        return text
    return f'\033[{code}m{text}\033[0m'

def green(t: str) -> str: return c(t, '92')
def red(t: str) -> str:   return c(t, '91')
def yellow(t: str) -> str: return c(t, '93')
def cyan(t: str) -> str:  return c(t, '96')
def bold(t: str) -> str:  return c(t, '1')
def dim(t: str) -> str:   return c(t, '2')


# ═══════════════════════════════════════════════════════════════════════════════
# Phân tích kết quả backtest
# ═══════════════════════════════════════════════════════════════════════════════

def ts_to_dt(timestamp_s: int) -> datetime:
    """Unix timestamp (giây) → datetime UTC."""
    return datetime.fromtimestamp(timestamp_s, tz=timezone.utc)


def group_by_day(trades: list[TradeResult]) -> dict[str, list[TradeResult]]:
    groups: dict[str, list[TradeResult]] = defaultdict(list)
    for t in trades:
        dt = ts_to_dt(t.timestamp)
        key = dt.strftime('%Y-%m-%d')
        groups[key].append(t)
    return dict(sorted(groups.items()))


def group_by_month(trades: list[TradeResult]) -> dict[str, list[TradeResult]]:
    groups: dict[str, list[TradeResult]] = defaultdict(list)
    for t in trades:
        dt = ts_to_dt(t.timestamp)
        key = dt.strftime('%Y-%m')
        groups[key].append(t)
    return dict(sorted(groups.items()))


def pnl_color(val: float) -> str:
    s = f'{val:+.2f}'
    return green(s) if val >= 0 else red(s)


def pct_color(val: float) -> str:
    s = f'{val:+.2f}%'
    return green(s) if val >= 0 else red(s)


def win_rate_str(trades: list[TradeResult]) -> str:
    if not trades:
        return '—'
    wins = sum(1 for t in trades if t.pnl > 0)
    rate = wins / len(trades) * 100
    txt = f'{wins}/{len(trades)} ({rate:.0f}%)'
    return green(txt) if rate >= 50 else red(txt)


def trade_row(t: TradeResult, running_balance: float) -> str:
    dt = ts_to_dt(t.timestamp).strftime('%m-%d %H:%M')
    side_str = green('BUY ') if t.side == 'buy' else red('SELL')
    reason_map = {'STOP_LOSS': red('SL'), 'TAKE_PROFIT': green('TP'), 'TIME_EXIT': yellow('TIME')}
    exit_str = reason_map.get(t.exit_reason, t.exit_reason)
    return (
        f"  {dim(dt)}  {side_str}  "
        f"entry={t.entry_price:>10.2f}  exit={t.exit_price:>10.2f}  "
        f"qty={t.quantity:.5f}  pnl={pnl_color(t.pnl):>10}  "
        f"exit={exit_str}  bal={running_balance:>10.2f}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Báo cáo chính
# ═══════════════════════════════════════════════════════════════════════════════

def format_range(result: BacktestResult) -> str:
    if result.analysis_start_timestamp is None or result.analysis_end_timestamp is None:
        return 'n/a'
    start = ts_to_dt(result.analysis_start_timestamp).strftime('%Y-%m-%d %H:%M UTC')
    end = ts_to_dt(result.analysis_end_timestamp).strftime('%Y-%m-%d %H:%M UTC')
    return f'{start} -> {end}'


def print_separator(char: str = '─', width: int = 100) -> None:
    print(dim(char * width))


def print_header(title: str, width: int = 100) -> None:
    pad = (width - len(title) - 2) // 2
    print()
    print(bold(cyan('═' * width)))
    print(bold(cyan('║' + ' ' * pad + title + ' ' * (width - pad - len(title) - 2) + '║')))
    print(bold(cyan('═' * width)))


def print_section(title: str) -> None:
    print()
    print(bold(f'┌─ {title} {"─" * (90 - len(title))}'))


def format_report(result: BacktestResult, symbol: str, days: int, starting_balance: float) -> None:
    trades = result.trades
    total_pnl = sum(t.pnl for t in trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    avg_win = gross_profit / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    rr_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')

    # ── Tổng quan ────────────────────────────────────────────────────────────
    print_header(f'BACKTEST REPORT — {symbol} — {days} NGÀY')

    print_section('TỔNG QUAN')
    rows = [
        ('Symbol',             symbol),
        ('Số ngày backtest',   f'{days} ngày'),
        ('Khoảng nến test',    format_range(result)),
        ('Vốn ban đầu',        f'{starting_balance:,.2f} USDT'),
        ('Vốn cuối kỳ',        f'{result.ending_balance:,.2f} USDT'),
        ('Tổng lợi nhuận',     f'{pnl_color(total_pnl)} USDT  ({pct_color(result.total_return_pct)})'),
        ('Tổng lệnh',          f'{len(trades)} lệnh'),
        ('  └ Thắng',          f'{len(wins)} lệnh  ({result.win_rate:.1f}%)'),
        ('  └ Thua',           f'{len(losses)} lệnh'),
        ('Signals generated',  f'{result.signals_generated}  (bỏ qua: {result.skipped_signals})'),
        ('Profit Factor',      f'{profit_factor:.2f}'),
        ('R:R trung bình',     f'{rr_ratio:.2f}'),
        ('Lãi TB/lệnh thắng',  f'{avg_win:.2f} USDT'),
        ('Lỗ TB/lệnh thua',    f'{avg_loss:.2f} USDT'),
        ('Max Drawdown',       f'{red(f"-{result.max_drawdown_pct:.2f}%")}'),
    ]
    for label, value in rows:
        print(f'  {bold(label):<28} {value}')

    # ── Báo cáo THEO THÁNG ────────────────────────────────────────────────────
    print_section('BÁO CÁO THEO THÁNG')
    monthly = group_by_month(trades)

    header = f"  {'Tháng':<10} {'Lệnh':>6} {'Thắng':>7} {'Thua':>6} {'Win%':>7} {'PnL (USDT)':>14} {'SL hit':>8} {'TP hit':>8}"
    print(bold(header))
    print_separator()

    # running balance for monthly
    running_bal = starting_balance
    for month, month_trades in monthly.items():
        m_pnl   = sum(t.pnl for t in month_trades)
        m_wins  = sum(1 for t in month_trades if t.pnl > 0)
        m_loss  = len(month_trades) - m_wins
        m_winr  = m_wins / len(month_trades) * 100 if month_trades else 0
        m_sl    = sum(1 for t in month_trades if t.exit_reason == 'STOP_LOSS')
        m_tp    = sum(1 for t in month_trades if t.exit_reason == 'TAKE_PROFIT')
        running_bal += m_pnl

        pnl_str  = pnl_color(m_pnl)
        winr_str = (green if m_winr >= 50 else red)(f'{m_winr:.0f}%')

        print(
            f"  {month:<10} "
            f"{len(month_trades):>6}  "
            f"{m_wins:>6}  "
            f"{m_loss:>5}  "
            f"{winr_str:>14}  "
            f"{pnl_str:>20}  "
            f"{m_sl:>6}  "
            f"{m_tp:>6}"
        )

    print_separator()

    # ── Báo cáo THEO NGÀY ────────────────────────────────────────────────────
    print_section('BÁO CÁO THEO NGÀY')
    daily = group_by_day(trades)

    header_d = f"  {'Ngày':<12} {'Lệnh':>5} {'Thắng':>6} {'Thua':>5} {'Win%':>7} {'PnL (USDT)':>14}"
    print(bold(header_d))
    print_separator()

    for day, day_trades in daily.items():
        d_pnl   = sum(t.pnl for t in day_trades)
        d_wins  = sum(1 for t in day_trades if t.pnl > 0)
        d_loss  = len(day_trades) - d_wins
        d_winr  = d_wins / len(day_trades) * 100 if day_trades else 0

        pnl_str  = pnl_color(d_pnl)
        winr_str = (green if d_winr >= 50 else (yellow if d_winr > 0 else red))(f'{d_winr:.0f}%')

        print(
            f"  {day:<12} "
            f"{len(day_trades):>5}  "
            f"{d_wins:>6}  "
            f"{d_loss:>5}  "
            f"{winr_str:>14}  "
            f"{pnl_str:>20}"
        )

    print_separator()

    # ── Chi tiết từng lệnh ────────────────────────────────────────────────────
    print_section('CHI TIẾT TỪNG LỆNH')
    print(bold(
        f"  {'Thời gian':<13} {'Chiều':<5} {'Entry':>12} {'Exit':>12} "
        f"{'Qty':>10} {'PnL':>12} {'Kết thúc':<6} {'Balance':>12}"
    ))
    print_separator()

    running = starting_balance
    for t in trades:
        running += t.pnl
        print(trade_row(t, running))

    print_separator()

    # ── Phân tích exit reason ────────────────────────────────────────────────
    print_section('PHÂN TÍCH THEO LOẠI KẾT THÚC')
    reasons: dict[str, list[TradeResult]] = defaultdict(list)
    for t in trades:
        reasons[t.exit_reason].append(t)

    for reason, rtrades in sorted(reasons.items()):
        r_pnl = sum(t.pnl for t in rtrades)
        r_wins = sum(1 for t in rtrades if t.pnl > 0)
        print(
            f"  {bold(reason):<18} "
            f"lệnh={len(rtrades):>4}  "
            f"thắng={r_wins:>3}  "
            f"PnL={pnl_color(r_pnl):>12}"
        )

    # ── Chuỗi thắng/thua liên tiếp ─────────────────────────────────────────
    print_section('CHUỖI THẮNG/THUA LIÊN TIẾP')
    max_win_streak = max_loss_streak = 0
    cur_win = cur_loss = 0
    for t in trades:
        if t.pnl > 0:
            cur_win += 1
            cur_loss = 0
        else:
            cur_loss += 1
            cur_win = 0
        max_win_streak = max(max_win_streak, cur_win)
        max_loss_streak = max(max_loss_streak, cur_loss)

    print(f'  {bold("Chuỗi thắng tối đa:"):<28} {green(str(max_win_streak))} lệnh liên tiếp')
    print(f'  {bold("Chuỗi thua tối đa:"):<28}  {red(str(max_loss_streak))} lệnh liên tiếp')

    # ── Equity curve mini chart ───────────────────────────────────────────────
    print_section('ĐƯỜNG EQUITY (mini chart)')
    curve = result.equity_curve
    if len(curve) > 1:
        width = 80
        sample_step = max(1, len(curve) // width)
        sampled = curve[::sample_step]
        mn, mx = min(sampled), max(sampled)
        height = 8
        normalized = [int((v - mn) / (mx - mn) * (height - 1)) if mx > mn else 0 for v in sampled]
        canvas = [[' '] * len(normalized) for _ in range(height)]
        for col, level in enumerate(normalized):
            canvas[height - 1 - level][col] = '█'

        print(f'  {cyan(f"Max: {mx:,.2f}")}  {red(f"Min: {mn:,.2f}")}')
        for row in canvas:
            print('  ' + dim('│') + ''.join(
                green(ch) if ch == '█' else ch for ch in row
            ))
        print('  ' + dim('└' + '─' * len(normalized)))

    # ── Footer ───────────────────────────────────────────────────────────────
    print()
    print(bold(cyan('═' * 100)))
    roi = result.total_return_pct
    color_fn = green if roi >= 0 else red
    print(bold(color_fn(
        f'  KẾT QUẢ: Vốn {starting_balance:,.0f} → {result.ending_balance:,.0f} USDT  '
        f'({roi:+.2f}%)  |  {len(trades)} lệnh  |  Win-rate {result.win_rate:.1f}%  |  '
        f'Max DD {result.max_drawdown_pct:.1f}%'
    )))
    print(bold(cyan('═' * 100)))
    print()


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description='Detailed 90-day backtest report for Vibe Strategy')
    parser.add_argument('--symbol',  default=os.getenv('BACKTEST_SYMBOL', 'BTC/USDT'))
    parser.add_argument('--days',    type=int,   default=int(os.getenv('BACKTEST_DAYS', '90')))
    parser.add_argument('--balance', type=float, default=float(os.getenv('BACKTEST_BALANCE', '10000')))
    parser.add_argument('--fee',     type=float, default=0.0004, help='Taker fee rate (default 0.04%%)')
    parser.add_argument('--slippage-bps', type=float, default=None, help='Adverse slippage in basis points per fill (default: BACKTEST_SLIPPAGE_BPS or 5)')
    parser.add_argument('--fill-mode', choices=['signal_close', 'next_open'], default=None, help='Execution timing; signal_close matches the live market-order path')
    parser.add_argument('--exchange', default=None, help='Exchange ID override (binance, okx, etc.)')
    args = parser.parse_args()

    exchange_id = args.exchange or os.getenv('CCXT_EXCHANGE', 'binance')
    exchange  = build_exchange(exchange_id)

    symbol = normalize_derivative_symbol(exchange, args.symbol)

    print(bold(cyan(f'\n  Đang tải dữ liệu {symbol} từ {exchange.id.upper()} ({args.days} ngày)...\n')))

    generator = VibeTradingSignalGenerator(exchange, publisher=None)
    backtester = Backtester(exchange, generator, starting_balance=args.balance, fee_rate=args.fee, slippage_bps=args.slippage_bps, fill_mode=args.fill_mode)

    print(bold(cyan('  Đang chạy backtest...\n')))
    result = backtester.run(symbol, days=args.days)

    format_report(result, symbol, args.days, args.balance)


if __name__ == '__main__':
    main()
