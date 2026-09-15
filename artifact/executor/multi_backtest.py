"""
multi_backtest.py
=================
Multi-asset, multi-mode backtesting script for the Proof-of-Trade IEEE paper.

Runs the Vibe Mode (technical indicator) strategy across 10 cryptocurrency
pairs over a 2-year period to generate the empirical results reported in
Section VIII of the paper, specifically the controlled comparison table.

Usage
-----
# Vibe Mode — 10 pairs, 2 years, 100 USDT starting capital each
python executor/multi_backtest.py \\
    --mode vibe \\
    --days 730 \\
    --balance 100 \\
    --output results/multi_asset_2y_vibe.json

# Quick smoke-test (3 pairs, 90 days)
python executor/multi_backtest.py \\
    --mode vibe --days 90 \\
    --symbols BTC/USDT,ETH/USDT,XRP/USDT \\
    --balance 100

# Full 10-pair with exchange override
python executor/multi_backtest.py \\
    --mode vibe --days 730 --balance 100 \\
    --exchange binance \\
    --output results/multi_asset_2y_vibe.json

Output JSON schema
------------------
{
  "config": { "days": 730, "mode": "vibe", "fee_rate": 0.0004,
              "slippage_bps": 5.0, "balance": 100.0,
              "exchange": "binance", "generated_at": "..." },
  "summary": {
      "n_symbols": 10,
      "avg_return_pct": ...,  "median_return_pct": ...,
      "avg_sharpe": ...,      "avg_sortino": ...,
      "avg_calmar": ...,      "avg_max_dd_pct": ...,
      "avg_win_rate": ...,    "avg_profit_factor": ...,
      "total_trades": ...,
      "symbols_profitable": ..., "symbols_loss": ...
  },
  "per_symbol": {
      "BTC/USDT": {
          "return_pct": ..., "cagr_pct": ..., "sharpe_ratio": ...,
          "sortino_ratio": ..., "calmar_ratio": ...,
          "max_drawdown_pct": ..., "win_rate": ..., "profit_factor": ...,
          "total_trades": ..., "winning_trades": ..., "losing_trades": ...,
          "var_95_pct": ..., "cvar_95_pct": ..., "avg_rr": ...,
          "starting_balance": ..., "ending_balance": ...
      },
      ...
  }
}
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# ── ensure project root is on sys.path when running as script ──────────────
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_ROOT / '.env')
except Exception:
    pass

try:
    from executor.backtester import (  # noqa: E402
        Backtester,
        VibeTradingSignalGenerator,
        AITradingSignalGenerator,
        HybridTradingSignalGenerator,
        build_exchange,
        normalize_derivative_symbol,
        BacktestResult,
    )
except ImportError:
    from backtester import (  # noqa: E402
        Backtester,
        VibeTradingSignalGenerator,
        AITradingSignalGenerator,
        HybridTradingSignalGenerator,
        build_exchange,
        normalize_derivative_symbol,
        BacktestResult,
    )

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
)
logger = logging.getLogger('multi_backtest')

# ─────────────────────────────────────────────────────────────────────────── #
#  Default 10-pair universe  (Section VII of IEEE paper)                       #
# ─────────────────────────────────────────────────────────────────────────── #
DEFAULT_SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "XRP/USDT",
    "SOL/USDT",
    "DOGE/USDT",
    "BNB/USDT",
    "AVAX/USDT",
    "NEAR/USDT",
    "TRX/USDT",
    "TON/USDT",
]


# ─────────────────────────────────────────────────────────────────────────── #
#  Per-symbol backtest runner                                                  #
# ─────────────────────────────────────────────────────────────────────────── #

def run_single(
    symbol: str,
    days: int,
    balance: float,
    exchange_id: str | None,
    fee_rate: float,
    slippage_bps: float,
    mode: str = 'vibe',
    sentiment_file: str | None = None,
    llm_file: str | None = None,
) -> tuple[str, dict | str]:
    """
    Run a single-symbol backtest. Returns (symbol, result_dict | error_str).
    """
    try:
        exchange = build_exchange(exchange_id)
        norm_symbol = normalize_derivative_symbol(exchange, symbol)
        
        if mode == 'ai':
            if not sentiment_file:
                raise ValueError("--sentiment-file is required for AI mode")
            generator = AITradingSignalGenerator(exchange, sentiment_file, llm_file=llm_file, publisher=None)
        elif mode == 'hybrid':
            if not sentiment_file:
                raise ValueError("--sentiment-file is required for hybrid mode")
            generator = HybridTradingSignalGenerator(exchange, sentiment_file, llm_file=llm_file, publisher=None)
        else:
            generator = VibeTradingSignalGenerator(exchange, publisher=None)
            
        backtester = Backtester(
            exchange=exchange,
            generator=generator,
            starting_balance=balance,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
        )
        logger.info("[%s] Starting backtest: %d days, %.2f USDT", symbol, days, balance)
        t0 = time.monotonic()
        result: BacktestResult = backtester.run(norm_symbol, days=days)
        elapsed = time.monotonic() - t0
        logger.info(
            "[%s] Done in %.1fs | Return=%.2f%% | Sharpe=%.2f | Trades=%d",
            symbol,
            elapsed,
            result.total_return_pct,
            result.sharpe_ratio,
            len(result.trades),
        )
        d = result.to_dict()
        # Lightweight summary (exclude full trade list to keep JSON manageable)
        summary = {k: v for k, v in d.items() if k != 'trades'}
        summary['trade_count'] = len(result.trades)
        return symbol, summary, d.get('trades', [])
    except Exception as exc:
        logger.error("[%s] Backtest failed: %s", symbol, exc)
        return symbol, f"ERROR: {exc}", []
        return symbol, f"ERROR: {exc}"


# ─────────────────────────────────────────────────────────────────────────── #
#  Aggregate statistics                                                        #
# ─────────────────────────────────────────────────────────────────────────── #

def _safe_values(per_symbol: dict, key: str) -> list[float]:
    """Extract numeric values for a given key, skipping error entries."""
    vals: list[float] = []
    for v in per_symbol.values():
        if isinstance(v, dict):
            val = v.get(key)
            if val is not None and isinstance(val, (int, float)):
                vals.append(float(val))
    return vals


def build_summary(per_symbol: dict, days: int) -> dict:
    """Compute aggregate statistics across all symbols."""
    returns = _safe_values(per_symbol, 'total_return_pct')
    sharpes = _safe_values(per_symbol, 'sharpe_ratio')
    sortinos = _safe_values(per_symbol, 'sortino_ratio')
    calmars = _safe_values(per_symbol, 'calmar_ratio')
    maxdds = _safe_values(per_symbol, 'max_drawdown_pct')
    win_rates = _safe_values(per_symbol, 'win_rate')
    pfs = _safe_values(per_symbol, 'profit_factor')
    trades_counts = _safe_values(per_symbol, 'total_trades')
    cagrs = _safe_values(per_symbol, 'cagr_pct')

    def safe_stat(vals: list[float], fn) -> float:
        return round(fn(vals), 4) if vals else 0.0

    profitable = sum(1 for v in per_symbol.values()
                     if isinstance(v, dict) and v.get('total_return_pct', -1) > 0)
    error_count = sum(1 for v in per_symbol.values() if isinstance(v, str))

    return {
        'n_symbols': len(per_symbol),
        'n_symbols_successful': len(per_symbol) - error_count,
        'n_symbols_profitable': profitable,
        'n_symbols_loss': (len(per_symbol) - error_count) - profitable,
        'n_symbols_error': error_count,
        'period_days': days,
        # Return
        'avg_return_pct': safe_stat(returns, statistics.mean),
        'median_return_pct': safe_stat(returns, statistics.median),
        'min_return_pct': safe_stat(returns, min),
        'max_return_pct': safe_stat(returns, max),
        'avg_cagr_pct': safe_stat(cagrs, statistics.mean),
        # Risk-adjusted
        'avg_sharpe': safe_stat(sharpes, statistics.mean),
        'median_sharpe': safe_stat(sharpes, statistics.median),
        'avg_sortino': safe_stat(sortinos, statistics.mean),
        'avg_calmar': safe_stat(calmars, statistics.mean),
        # Drawdown
        'avg_max_dd_pct': safe_stat(maxdds, statistics.mean),
        'max_max_dd_pct': safe_stat(maxdds, max),
        # Trade quality
        'avg_win_rate': safe_stat(win_rates, statistics.mean),
        'avg_profit_factor': safe_stat(pfs, statistics.mean),
        'total_trades': int(sum(trades_counts)),
    }


# ─────────────────────────────────────────────────────────────────────────── #
#  Pretty-print table                                                          #
# ─────────────────────────────────────────────────────────────────────────── #

def print_results_table(per_symbol: dict) -> None:
    """Print a formatted results table suitable for copying into the paper."""
    header = (
        f"{'Symbol':<12} {'Return%':>9} {'CAGR%':>7} {'Sharpe':>7} "
        f"{'Sortino':>8} {'MaxDD%':>7} {'WinRate%':>9} {'PF':>5} {'Trades':>7}"
    )
    print("\n" + "=" * len(header))
    print(header)
    print("-" * len(header))
    for sym, v in sorted(per_symbol.items()):
        if isinstance(v, str):
            print(f"{sym:<12} ERROR: {v}")
            continue
        print(
            f"{sym:<12} "
            f"{v.get('total_return_pct', 0):>9.2f} "
            f"{v.get('cagr_pct', 0):>7.2f} "
            f"{v.get('sharpe_ratio', 0):>7.2f} "
            f"{v.get('sortino_ratio', 0):>8.2f} "
            f"{v.get('max_drawdown_pct', 0):>7.2f} "
            f"{v.get('win_rate', 0):>9.2f} "
            f"{v.get('profit_factor', 0):>5.2f} "
            f"{v.get('total_trades', 0):>7}"
        )
    print("=" * len(header) + "\n")


# ─────────────────────────────────────────────────────────────────────────── #
#  Main                                                                        #
# ─────────────────────────────────────────────────────────────────────────── #

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-asset backtest runner for IEEE Proof-of-Trade paper"
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated list of trading pairs (default: 10-pair universe)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=int(os.getenv("BACKTEST_DAYS", "730")),
        help="Number of calendar days to backtest (default: 730 = 2 years)",
    )
    parser.add_argument(
        "--balance",
        type=float,
        default=float(os.getenv("BACKTEST_BALANCE", "100")),
        help="Starting balance per symbol in USDT (default: 100)",
    )
    parser.add_argument(
        "--mode",
        choices=["vibe", "ai", "hybrid"],
        default="vibe",
        help="Trading mode: 'vibe' (technical), 'ai' (microstructure), or 'hybrid'",
    )
    parser.add_argument(
        "--sentiment-file",
        default=None,
        help="Path to the sentiment JSON file (required if mode=ai)",
    )
    parser.add_argument(
        "--llm-file",
        default=None,
        help="Path to the llm sentiment JSON file",
    )
    parser.add_argument(
        "--exchange",
        default=None,
        help="Exchange ID override (binance, bybit, okx). Reads CCXT_EXCHANGE env if omitted.",
    )
    parser.add_argument(
        "--fee-rate",
        type=float,
        default=float(os.getenv("BACKTEST_FEE_RATE", "0.0004")),
        help="Fee rate per side (default: 0.0004 = 0.04%%)",
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=float(os.getenv("BACKTEST_SLIPPAGE_BPS", "5")),
        help="Adverse slippage in basis points per fill (default: 5 bps)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.getenv("BACKTEST_WORKERS", "3")),
        help="Max parallel workers (default: 3; reduce if rate-limited)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write JSON results (optional; prints to stdout if omitted)",
    )
    parser.add_argument(
        "--no-table",
        action="store_true",
        help="Suppress the summary table output",
    )
    parser.add_argument(
        "--export-trades",
        action="store_true",
        help="Export all trades to a separate JSON file for statistical analysis",
    )
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    exchange_id = args.exchange or os.getenv("CCXT_EXCHANGE", "binance")

    logger.info(
        "Multi-backtest: %d symbols × %d days × %.2f USDT | exchange=%s | workers=%d",
        len(symbols), args.days, args.balance, exchange_id, args.workers,
    )

    per_symbol: dict[str, dict | str] = {}
    all_trades: dict[str, list] = {}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                run_single,
                sym, args.days, args.balance, exchange_id,
                args.fee_rate, args.slippage_bps,
                args.mode, args.sentiment_file, args.llm_file
            ): sym
            for sym in symbols
        }
        for future in as_completed(futures):
            sym, result, trades = future.result()
            per_symbol[sym] = result
            all_trades[sym] = trades

    summary = build_summary(per_symbol, args.days)

    output = {
        "config": {
            "mode": args.mode,
            "days": args.days,
            "balance_per_symbol": args.balance,
            "fee_rate": args.fee_rate,
            "slippage_bps": args.slippage_bps,
            "exchange": exchange_id,
            "symbols": symbols,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "summary": summary,
        "per_symbol": per_symbol,
    }

    if not args.no_table:
        print_results_table(per_symbol)

        # Print aggregate summary
        print("=== AGGREGATE SUMMARY ===")
        for k, v in summary.items():
            print(f"  {k:<30s}: {v}")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        logger.info("Results saved to %s", out_path)
        
        if args.export_trades:
            trades_path = out_path.with_name(out_path.stem + "_trades.json")
            with open(trades_path, "w", encoding="utf-8") as f:
                json.dump(all_trades, f, indent=2)
            logger.info("Trades saved to %s", trades_path)
    else:
        print("\n" + json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
