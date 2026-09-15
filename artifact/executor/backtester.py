from __future__ import annotations

import argparse
import json
import logging
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import ccxt
import redis
from pathlib import Path

# Load .env automatically for scripts
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / '.env')
except Exception:
    pass


logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
)
logger = logging.getLogger('backtester')


@dataclass(slots=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class RegimeSnapshot:
    regime: str
    reason: str
    adx: float
    atr_pct: float
    trend_side: str | None = None


@dataclass(slots=True)
class TradeResult:
    timestamp: int
    exit_timestamp: int
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    stop_loss_price: float
    take_profit_price: float
    quantity: float
    pnl: float
    exit_reason: str


@dataclass(slots=True)
class BacktestResult:
    starting_balance: float
    ending_balance: float
    trades: list[TradeResult]
    equity_curve: list[float]
    equity_timestamps: list[int]
    signals_generated: int
    skipped_signals: int
    analysis_start_timestamp: int | None = None
    analysis_end_timestamp: int | None = None
    period_days: int | None = None

    @property
    def total_return_pct(self) -> float:
        if self.starting_balance <= 0:
            return 0.0
        return (self.ending_balance / self.starting_balance - 1.0) * 100.0

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for trade in self.trades if trade.pnl > 0)
        return wins / len(self.trades) * 100.0

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(trade.pnl for trade in self.trades if trade.pnl > 0)
        gross_loss = abs(sum(trade.pnl for trade in self.trades if trade.pnl < 0))
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    @property
    def max_drawdown_pct(self) -> float:
        peak = self.equity_curve[0] if self.equity_curve else self.starting_balance
        max_drawdown = 0.0
        for equity in self.equity_curve:
            peak = max(peak, equity)
            if peak > 0:
                drawdown = (peak - equity) / peak
                max_drawdown = max(max_drawdown, drawdown)
        return max_drawdown * 100.0

    def _period_returns(self) -> list[float]:
        """Returns between consecutive marked-to-market equity observations."""
        if len(self.equity_curve) < 2:
            return []
        return [
            later / earlier - 1.0
            for earlier, later in zip(self.equity_curve, self.equity_curve[1:])
            if earlier > 0
        ]

    @property
    def cagr(self) -> float:
        """Compound Annual Growth Rate (%). Requires period_days."""
        days = self.period_days
        if not days or days <= 0 or self.starting_balance <= 0 or self.ending_balance <= 0:
            return 0.0
        years = days / 365.0
        return ((self.ending_balance / self.starting_balance) ** (1.0 / years) - 1.0) * 100.0

    @property
    def sharpe_ratio(self) -> float:
        """Annualised Sharpe Ratio from marked-to-market 4-hour returns (Rf = 0)."""
        rets = self._period_returns()
        if len(rets) < 2:
            return 0.0
        import statistics
        mu = statistics.mean(rets)
        sigma = statistics.stdev(rets)
        # 4-hour bars: 6 * 365 observations/year for continuously traded crypto.
        return (mu / sigma) * ((6 * 365) ** 0.5) if sigma > 0 else 0.0

    @property
    def sortino_ratio(self) -> float:
        """Annualised Sortino Ratio (downside deviation only)."""
        rets = self._period_returns()
        if len(rets) < 2:
            return 0.0
        import statistics
        mu = statistics.mean(rets)
        neg = [r for r in rets if r < 0]
        if not neg:
            return float('inf') if mu > 0 else 0.0
        down_dev = (sum(r ** 2 for r in neg) / len(neg)) ** 0.5
        return (mu / down_dev) * ((6 * 365) ** 0.5) if down_dev > 0 else 0.0

    @property
    def calmar_ratio(self) -> float:
        """Calmar Ratio = CAGR / Max Drawdown."""
        mdd = self.max_drawdown_pct
        if mdd <= 0:
            return float('inf') if self.cagr > 0 else 0.0
        return self.cagr / mdd

    @property
    def var_95(self) -> float:
        """Value at Risk at 95% confidence level (% of notional, negative = loss)."""
        rets = sorted(self._period_returns())
        if not rets:
            return 0.0
        idx = max(0, int(len(rets) * 0.05) - 1)
        return rets[idx] * 100.0

    @property
    def cvar_95(self) -> float:
        """Conditional VaR / Expected Shortfall at 95% confidence."""
        rets = sorted(self._period_returns())
        if not rets:
            return 0.0
        cutoff = max(1, int(len(rets) * 0.05))
        tail = rets[:cutoff]
        return (sum(tail) / len(tail)) * 100.0

    @property
    def avg_rr(self) -> float:
        """Average Reward-to-Risk ratio across all closed trades."""
        ratios: list[float] = []
        for t in self.trades:
            risk = abs(t.entry_price - t.stop_loss_price)
            reward = abs(t.take_profit_price - t.entry_price)
            if risk > 0:
                ratios.append(reward / risk)
        return sum(ratios) / len(ratios) if ratios else 0.0

    @property
    def avg_win(self) -> float:
        wins = [t.pnl for t in self.trades if t.pnl > 0]
        return sum(wins) / len(wins) if wins else 0.0

    @property
    def avg_loss(self) -> float:
        losses = [t.pnl for t in self.trades if t.pnl < 0]
        return sum(losses) / len(losses) if losses else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            'starting_balance': round(self.starting_balance, 4),
            'ending_balance': round(self.ending_balance, 4),
            'total_return_pct': round(self.total_return_pct, 4),
            'cagr_pct': round(self.cagr, 4),
            'win_rate': round(self.win_rate, 4),
            'profit_factor': round(self.profit_factor, 4),
            'max_drawdown_pct': round(self.max_drawdown_pct, 4),
            'sharpe_ratio': round(self.sharpe_ratio, 4),
            'sortino_ratio': round(self.sortino_ratio, 4),
            'calmar_ratio': round(self.calmar_ratio, 4),
            'var_95_pct': round(self.var_95, 4),
            'cvar_95_pct': round(self.cvar_95, 4),
            'avg_rr': round(self.avg_rr, 4),
            'avg_win_usdt': round(self.avg_win, 6),
            'avg_loss_usdt': round(self.avg_loss, 6),
            'total_trades': len(self.trades),
            'winning_trades': sum(1 for t in self.trades if t.pnl > 0),
            'losing_trades': sum(1 for t in self.trades if t.pnl <= 0),
            'signals_generated': self.signals_generated,
            'skipped_signals': self.skipped_signals,
            'period_days': self.period_days,
            'equity_timestamps': self.equity_timestamps,
            'equity_curve': self.equity_curve,
            'trades': [asdict(trade) for trade in self.trades],
        }


def build_exchange(exchange_id: str | None = None) -> ccxt.Exchange:
    if exchange_id is None:
        exchange_id = os.getenv('MARKET_DATA_EXCHANGE_PLATFORM', os.getenv('CCXT_EXCHANGE', 'binance')).strip().lower()
    else:
        exchange_id = exchange_id.strip().lower()

    if not hasattr(ccxt, exchange_id):
        raise ValueError(f'unsupported exchange: {exchange_id}')

    exchange_class = getattr(ccxt, exchange_id)

    cfg: dict[str, Any] = {
        'enableRateLimit': True,
    }

    if exchange_id == 'okx':
        cfg['options'] = {'defaultType': 'swap'}
        # Backtests only need public market data. Do not attach OKX private keys
        # by default, otherwise demo keys against live public URLs can make
        # ccxt.load_markets() call private endpoints and fail with 50101.
        use_private_keys = os.getenv('BACKTEST_USE_PRIVATE_KEYS', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}
        api_key = os.getenv('OKX_API_KEY') if use_private_keys else None
        secret = (os.getenv('OKX_SECRET_KEY') or os.getenv('OKX_SECRET')) if use_private_keys else None
        passphrase = os.getenv('OKX_PASSPHRASE') if use_private_keys else None
        if use_private_keys and api_key and secret and passphrase:
            cfg.update({
                'apiKey': api_key,
                'secret': secret,
                'password': passphrase,
            })
    elif exchange_id == 'binance':
        cfg['options'] = {
            'defaultType': os.getenv('BINANCE_MARKET_TYPE', 'future'),
        }
    elif exchange_id == 'bybit':
        cfg['options'] = {
            'defaultType': os.getenv('BYBIT_MARKET_TYPE', 'swap'),
            'defaultSubType': os.getenv('BYBIT_MARKET_SUBTYPE', 'linear'),
        }

    exchange = exchange_class(cfg)

    if exchange_id == 'binance':
        if os.getenv('MARKET_DATA_IS_DEMO', os.getenv('BINANCE_SANDBOX', 'false')).lower() in {'1', 'true', 'yes'}:
            try:
                exchange.set_sandbox_mode(True)
            except Exception:
                pass
    elif exchange_id == 'okx':
        is_demo = os.getenv('BACKTEST_IS_DEMO', os.getenv('MARKET_DATA_IS_DEMO', 'false')).lower() in {'1', 'true', 'yes', 'on'}
        if is_demo:
            try:
                exchange.set_sandbox_mode(True)
            except Exception:
                pass
    elif exchange_id == 'bybit':
        is_demo = os.getenv('BACKTEST_IS_DEMO', os.getenv('MARKET_DATA_IS_DEMO', 'false')).lower() in {'1', 'true', 'yes', 'on'}
        if is_demo:
            try:
                exchange.set_sandbox_mode(True)
            except Exception:
                pass

    return exchange


def build_redis() -> redis.Redis:
    return redis.Redis.from_url(
        os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def normalize_derivative_symbol(exchange: ccxt.Exchange, symbol: str) -> str:
    if exchange.id in {'okx', 'bybit'} and '/' in symbol and ':' not in symbol:
        return f"{symbol}:{symbol.split('/')[-1]}"
    return symbol


def _fetch_ohlcv_single_with_retry(exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int, since: int | None = None) -> list[list[float]]:
    for attempt in range(3):
        try:
            return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit, since=since)
        except (ccxt.NetworkError, ccxt.RateLimitExceeded) as exc:
            logger.warning('OHLCV fetch failed for %s %s (attempt %s): %s', symbol, timeframe, attempt + 1, exc)
            if attempt == 2:
                raise
    raise RuntimeError('unreachable')


def fetch_ohlcv_with_retry(exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int, since: int | None = None) -> list[list[float]]:
    try:
        timeframe_duration_s = exchange.parse_timeframe(timeframe)
        timeframe_duration_ms = timeframe_duration_s * 1000
    except Exception:
        return _fetch_ohlcv_single_with_retry(exchange, symbol, timeframe, limit, since)

    if since is None:
        now_ms = exchange.milliseconds()
        since = now_ms - (limit * timeframe_duration_ms)

    all_candles: list[list[float]] = []
    current_since = since
    chunk_limit = 1000

    while len(all_candles) < limit:
        remaining = limit - len(all_candles)
        current_chunk_limit = min(remaining, chunk_limit)

        logger.info(
            "Fetching OHLCV chunk for %s %s: since=%s (%s), limit=%s, fetched=%s/%s",
            symbol,
            timeframe,
            current_since,
            datetime.fromtimestamp(current_since / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S') if current_since else 'None',
            current_chunk_limit,
            len(all_candles),
            limit,
        )

        chunk = _fetch_ohlcv_single_with_retry(exchange, symbol, timeframe, limit=current_chunk_limit, since=current_since)
        if not chunk:
            logger.info("Fetched empty chunk or reached end of historical data.")
            break

        all_candles.extend(chunk)

        last_candle_time = int(chunk[-1][0])
        next_since = last_candle_time + timeframe_duration_ms
        if next_since <= current_since:
            logger.warning("Timestamp did not advance (current_since=%s, next_since=%s). Breaking to avoid infinite loop.", current_since, next_since)
            break
        current_since = next_since

    return all_candles[-limit:]



def to_candles(raw: Sequence[Sequence[float]]) -> list[Candle]:
    candles: list[Candle] = []
    for row in raw:
        candles.append(
            Candle(
                timestamp=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
        )
    return candles


def closes(candles: Sequence[Candle]) -> list[float]:
    return [candle.close for candle in candles]


def highs(candles: Sequence[Candle]) -> list[float]:
    return [candle.high for candle in candles]


def lows(candles: Sequence[Candle]) -> list[float]:
    return [candle.low for candle in candles]


def ema(values: Sequence[float], period: int) -> float:
    if len(values) < period:
        raise ValueError('not enough values for ema')
    multiplier = 2 / (period + 1)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = (value - result) * multiplier + result
    return result


def rsi(values: Sequence[float], period: int = 14) -> float:
    if len(values) <= period:
        raise ValueError('not enough values for rsi')
    gains = 0.0
    losses = 0.0
    for index in range(1, period + 1):
        change = values[index] - values[index - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    for index in range(period + 1, len(values)):
        change = values[index] - values[index - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def true_range(high_values: Sequence[float], low_values: Sequence[float], close_values: Sequence[float]) -> list[float]:
    ranges = [high_values[0] - low_values[0]]
    for index in range(1, len(close_values)):
        current_high = high_values[index]
        current_low = low_values[index]
        previous_close = close_values[index - 1]
        ranges.append(max(current_high - current_low, abs(current_high - previous_close), abs(current_low - previous_close)))
    return ranges


def atr(candles: Sequence[Candle], period: int = 14) -> float:
    if len(candles) <= period:
        raise ValueError('not enough candles for atr')
    tr_values = true_range(highs(candles), lows(candles), closes(candles))
    return sum(tr_values[-period:]) / period


def adx(candles: Sequence[Candle], period: int = 14) -> float:
    if len(candles) <= period * 2:
        raise ValueError('not enough candles for adx')

    highs_values = highs(candles)
    lows_values = lows(candles)
    close_values = closes(candles)
    tr_values = true_range(highs_values, lows_values, close_values)

    plus_dm: list[float] = [0.0]
    minus_dm: list[float] = [0.0]
    for index in range(1, len(candles)):
        up_move = highs_values[index] - highs_values[index - 1]
        down_move = lows_values[index - 1] - lows_values[index]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)

    atr_values: list[float] = []
    plus_di_values: list[float] = []
    minus_di_values: list[float] = []
    dx_values: list[float] = []

    atr_smooth = sum(tr_values[1 : period + 1])
    plus_dm_smooth = sum(plus_dm[1 : period + 1])
    minus_dm_smooth = sum(minus_dm[1 : period + 1])

    for index in range(period + 1, len(candles)):
        atr_smooth = atr_smooth - (atr_smooth / period) + tr_values[index]
        plus_dm_smooth = plus_dm_smooth - (plus_dm_smooth / period) + plus_dm[index]
        minus_dm_smooth = minus_dm_smooth - (minus_dm_smooth / period) + minus_dm[index]

        current_atr = atr_smooth / period
        atr_values.append(current_atr)
        if current_atr == 0:
            continue

        plus_di = 100 * (plus_dm_smooth / period) / current_atr
        minus_di = 100 * (minus_dm_smooth / period) / current_atr
        plus_di_values.append(plus_di)
        minus_di_values.append(minus_di)

        denominator = plus_di + minus_di
        if denominator == 0:
            continue
        dx_values.append(100 * abs(plus_di - minus_di) / denominator)

    if len(dx_values) < period:
        raise ValueError('not enough dx values for adx')

    return sum(dx_values[-period:]) / period


def macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float]:
    if len(values) <= slow + signal:
        raise ValueError('not enough values for macd')

    fast_ema = []
    slow_ema = []
    for index in range(slow, len(values) + 1):
        fast_ema.append(ema(values[:index], fast))
        slow_ema.append(ema(values[:index], slow))
    macd_values = [fast_value - slow_value for fast_value, slow_value in zip(fast_ema, slow_ema)]
    signal_line = ema(macd_values, signal)
    histogram = macd_values[-1] - signal_line
    return macd_values[-1], signal_line, histogram


def time_to_dt(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc)


class RedisSignalPublisher:
    def __init__(self, client: redis.Redis, channel: str = 'trading_signals', history_key: str = 'recent_signals') -> None:
        self.client = client
        self.channel = channel
        self.history_key = history_key

    def publish(self, signal: dict[str, Any]) -> None:
        payload = json.dumps(signal, separators=(',', ':'), default=str)
        self.client.publish(self.channel, payload)


class RedisStateStore:
    def __init__(self, client: redis.Redis, daily_vibe_key: str = 'daily_market_vibe') -> None:
        self.client = client
        self.daily_vibe_key = daily_vibe_key

    def save_daily_vibe(self, payload: dict[str, Any]) -> None:
        serialized = json.dumps(payload, separators=(',', ':'), default=str)
        self.client.set(self.daily_vibe_key, serialized)

    def load_daily_vibe(self) -> dict[str, Any] | None:
        raw_value = self.client.get(self.daily_vibe_key)
        if not raw_value:
            return None
        return json.loads(raw_value)


class VibeTradingSignalGenerator:
    def __init__(self, exchange: ccxt.Exchange, publisher: RedisSignalPublisher | None = None) -> None:
        self.exchange = exchange
        self.publisher = publisher
        self.risk_per_trade = float(os.getenv('VIBE_RISK_PER_TRADE', '0.01'))
        self.trend_adx_threshold = float(os.getenv('VIBE_TREND_ADX', '25'))
        self.chop_adx_threshold = float(os.getenv('VIBE_CHOP_ADX', '18'))
        self.high_atr_pct = float(os.getenv('VIBE_HIGH_ATR_PCT', '0.05'))
        self.trailing_trigger = float(os.getenv('VIBE_TRAILING_TRIGGER', '0.5'))
        self.leverage = int(os.getenv('VIBE_DEFAULT_LEVERAGE', '5'))

    def generate(self, symbol: str, candles_1d: Sequence[Candle], candles_4h: Sequence[Candle], balance: float) -> dict[str, Any]:
        daily_snapshot = self._snapshot(candles_1d)
        intraday_snapshot = self._snapshot(candles_4h)
        latest_close = candles_4h[-1].close

        if self._too_choppy(daily_snapshot, intraday_snapshot):
            return self._wait_signal(symbol, candles_4h[-1].timestamp, 'Market is too noisy or the fluctuation range is too large', daily_snapshot, intraday_snapshot)

        direction = self._select_direction(candles_1d, candles_4h, daily_snapshot, intraday_snapshot)
        if direction is None:
            return self._wait_signal(symbol, candles_4h[-1].timestamp, 'No consensus between trend and momentum', daily_snapshot, intraday_snapshot)

        stop_loss_price, take_profit_price = self._build_levels(direction, candles_4h)
        quantity = self._calculate_quantity(balance, latest_close, stop_loss_price)

        signal = {
            'timestamp': int(candles_4h[-1].timestamp / 1000),
            'symbol': symbol,
            'side': direction,
            'leverage': self.leverage,
            'entry_price': latest_close,
            'stop_loss_price': stop_loss_price,
            'take_profit_price': take_profit_price,
            'quantity': quantity,
            'action': 'TRADE',
            'regime': intraday_snapshot.regime,
            'reason': f'{daily_snapshot.regime} / {intraday_snapshot.regime} confluence',
            'risk_per_trade': self.risk_per_trade,
            'pyramid_step_price': atr(candles_4h) * float(os.getenv('VIBE_PYRAMID_STEP_ATR', '1.0')),
        }
        if self.publisher:
            self.publisher.publish(signal)
        return signal

    def build_daily_outlook(self, symbol: str, candles_1d: Sequence[Candle], candles_4h: Sequence[Candle], balance: float) -> dict[str, Any]:
        signal = self.generate(symbol, candles_1d, candles_4h, balance)
        daily_snapshot = self._snapshot(candles_1d)
        intraday_snapshot = self._snapshot(candles_4h)
        outlook = {
            'timestamp': signal['timestamp'],
            'symbol': symbol,
            'market_regime': self._derive_market_regime(daily_snapshot, intraday_snapshot, signal),
            'daily_plan': self._build_daily_plan(signal, daily_snapshot, intraday_snapshot),
            'reasoning': signal.get('reason'),
            'signal': signal,
        }
        return outlook

    def _snapshot(self, candles: Sequence[Candle]) -> RegimeSnapshot:
        closes_values = closes(candles)
        atr_value = atr(candles)
        atr_pct = atr_value / closes_values[-1]
        adx_value = adx(candles)
        fast_ema = ema(closes_values, 20)
        slow_ema = ema(closes_values, 50)
        rsi_value = rsi(closes_values)
        macd_line, signal_line, histogram = macd(closes_values)

        if atr_pct >= self.high_atr_pct:
            return RegimeSnapshot('HIGH_VOLATILITY', 'ATR is too elevated', adx_value, atr_pct)

        if adx_value >= self.trend_adx_threshold and abs(fast_ema - slow_ema) / closes_values[-1] > 0.002:
            trend_side = 'buy' if fast_ema > slow_ema and macd_line >= signal_line and rsi_value >= 50 else 'sell' if fast_ema < slow_ema and macd_line <= signal_line and rsi_value <= 50 else None
            regime = 'TRENDING' if trend_side else 'SIDEWAYS'
            reason = 'Trend filters aligned' if trend_side else 'Trend strength present but momentum is mixed'
            return RegimeSnapshot(regime, reason, adx_value, atr_pct, trend_side=trend_side)

        if adx_value <= self.chop_adx_threshold:
            return RegimeSnapshot('SIDEWAYS', 'Low ADX range regime', adx_value, atr_pct)

        if histogram > 0 and rsi_value > 55:
            return RegimeSnapshot('TRENDING', 'Momentum is bullish', adx_value, atr_pct, trend_side='buy')
        if histogram < 0 and rsi_value < 45:
            return RegimeSnapshot('TRENDING', 'Momentum is bearish', adx_value, atr_pct, trend_side='sell')

        return RegimeSnapshot('SIDEWAYS', 'No decisive trend edge', adx_value, atr_pct)

    def _too_choppy(self, daily_snapshot: RegimeSnapshot, intraday_snapshot: RegimeSnapshot) -> bool:
        return (
            daily_snapshot.regime == 'HIGH_VOLATILITY'
            or intraday_snapshot.regime == 'HIGH_VOLATILITY'
            or intraday_snapshot.adx <= self.chop_adx_threshold and intraday_snapshot.atr_pct >= self.high_atr_pct * 0.35
        )

    def _derive_market_regime(self, daily_snapshot: RegimeSnapshot, intraday_snapshot: RegimeSnapshot, signal: dict[str, Any]) -> str:
        if signal.get('action') == 'WAIT':
            return 'WAIT'
        return 'SIDEWAYS'

    def _build_daily_plan(self, signal: dict[str, Any], daily_snapshot: RegimeSnapshot, intraday_snapshot: RegimeSnapshot) -> dict[str, Any]:
        if signal.get('action') == 'WAIT':
            return {
                'action': 'WAIT',
                'style': 'capital preservation',
                'entry': None,
                'stop_loss': None,
                'take_profit': None,
                'reason': signal.get('reason') or 'No trade today',
            }

        side = signal['side']
        risk_reward = self._risk_reward_ratio(signal)
        return {
            'action': 'TRADE',
            'style': 'trend-following' if daily_snapshot.regime == 'TRENDING' else 'range-scalp',
            'entry': signal.get('entry_price'),
            'side': side,
            'stop_loss': signal['stop_loss_price'],
            'take_profit': signal['take_profit_price'],
            'quantity': signal['quantity'],
            'risk_reward_ratio': risk_reward,
            'daily_regime': daily_snapshot.regime,
            'intraday_regime': intraday_snapshot.regime,
        }

    def _risk_reward_ratio(self, signal: dict[str, Any]) -> float | None:
        try:
            stop_loss = float(signal['stop_loss_price'])
            take_profit = float(signal['take_profit_price'])
        except (TypeError, ValueError, KeyError):
            return None

        entry_price = signal.get('entry_price')
        if entry_price is not None:
            try:
                entry_value = float(entry_price)
            except (TypeError, ValueError):
                entry_value = None
        else:
            entry_value = None

        if entry_value is None:
            return None

        risk = abs(entry_value - stop_loss)
        reward = abs(take_profit - entry_value)
        if risk <= 0:
            return None
        return round(reward / risk, 2)

    def _select_direction(self, daily_candles: Sequence[Candle], intraday_candles: Sequence[Candle], daily_snapshot: RegimeSnapshot, intraday_snapshot: RegimeSnapshot) -> str | None:
        # Research profile: implementable version of the crypto evidence in
        # Hudson--Urquhart (breakout rules) and Hsieh et al. (persistent UP-UP
        # state).  It is intentionally opt-in until it passes walk-forward
        # tests.  A fresh breakout avoids opening the same direction on every
        # 4H bar merely because EMA/MACD/RSI still agree.
        if os.getenv('VIBE_TECH_PROFILE', 'confluence').lower() == 'regime_breakout':
            lookback = max(10, int(os.getenv('VIBE_BREAKOUT_LOOKBACK', '20')))
            if len(daily_candles) < 16 or len(intraday_candles) < lookback + 1:
                return None
            daily_close = closes(daily_candles)
            intraday_close = closes(intraday_candles)
            up_up = daily_close[-1] >= daily_close[-8] and daily_close[-8] >= daily_close[-15]
            down_down = daily_close[-1] <= daily_close[-8] and daily_close[-8] <= daily_close[-15]
            daily_fast = ema(daily_close, 20)
            daily_slow = ema(daily_close, 50)
            daily_macd, daily_signal, _ = macd(daily_close)
            prior_high = max(intraday_close[-lookback - 1:-1])
            prior_low = min(intraday_close[-lookback - 1:-1])
            long_breakout = intraday_close[-1] > prior_high
            short_breakout = intraday_close[-1] < prior_low
            if up_up and daily_fast > daily_slow and daily_macd >= daily_signal and long_breakout:
                return 'buy'
            if (os.getenv('VIBE_REGIME_BREAKOUT_ALLOW_SHORT', 'false').lower() in {'1', 'true', 'yes'}
                    and down_down and daily_fast < daily_slow and daily_macd <= daily_signal and short_breakout):
                return 'sell'
            return None

        if os.getenv('VIBE_TECH_PROFILE', 'confluence').lower() == 'regime_momentum':
            # Hsieh et al. study weekly UP/DOWN states, while Han et al. warn
            # that apparent crypto momentum can disappear after liquidation
            # risk.  Re-evaluate only at the end of a UTC day: this is a daily
            # trend allocation, not six duplicated 4H entries.
            if len(daily_candles) < 16 or int(intraday_candles[-1].timestamp) % 86_400_000 != 72_000_000:
                return None
            daily_close = closes(daily_candles)
            up_up = daily_close[-1] >= daily_close[-8] and daily_close[-8] >= daily_close[-15]
            fast = ema(daily_close, 20)
            slow = ema(daily_close, 50)
            macd_line, macd_signal, _ = macd(daily_close)
            if up_up and fast > slow and macd_line >= macd_signal:
                return 'buy'
            return None

        if os.getenv('VIBE_TECH_PROFILE', 'confluence').lower() == 'trend_pullback':
            # F03/F04-style trend-following entry: buy a recovered 4H pullback
            # only while the daily trend remains positive.  It is deliberately
            # long-only; the short side is a separate hypothesis.
            if len(daily_candles) < 60 or len(intraday_candles) < 51:
                return None
            daily_close = closes(daily_candles)
            intraday_close = closes(intraday_candles)
            daily_fast = ema(daily_close, 20)
            daily_slow = ema(daily_close, 50)
            daily_macd, daily_signal, _ = macd(daily_close)
            intraday_fast_now = ema(intraday_close, 20)
            intraday_fast_prev = ema(intraday_close[:-1], 20)
            pullback_recovery = intraday_close[-2] <= intraday_fast_prev and intraday_close[-1] > intraday_fast_now
            if daily_fast > daily_slow and daily_macd >= daily_signal and pullback_recovery:
                return 'buy'
            return None

        closes_1d = closes(daily_candles)
        closes_4h = closes(intraday_candles)
        daily_rsi = rsi(closes_1d)
        intraday_rsi = rsi(closes_4h)
        daily_macd_line, daily_signal, _ = macd(closes_1d)
        intraday_macd_line, intraday_signal, _ = macd(closes_4h)

        bullish = (
            daily_snapshot.trend_side == 'buy'
            or (daily_macd_line >= daily_signal and daily_rsi >= 52)
        ) and (
            intraday_snapshot.trend_side == 'buy'
            or (intraday_macd_line >= intraday_signal and intraday_rsi >= 52)
        )
        bearish = (
            daily_snapshot.trend_side == 'sell'
            or (daily_macd_line <= daily_signal and daily_rsi <= 48)
        ) and (
            intraday_snapshot.trend_side == 'sell'
            or (intraday_macd_line <= intraday_signal and intraday_rsi <= 48)
        )

        if bullish and not bearish:
            return 'buy'
        if bearish and not bullish:
            return 'sell'
        return None

    def _build_levels(self, side: str, candles: Sequence[Candle]) -> tuple[float, float]:
        last_close = candles[-1].close
        atr_value = atr(candles)
        
        sl_multiplier = float(os.getenv('VIBE_ATR_SL_MULTIPLIER', '1.5'))
        tp_multiplier = float(os.getenv('VIBE_ATR_TP_MULTIPLIER', '3.0'))

        raw_sl_distance = atr_value * sl_multiplier
        raw_tp_distance = atr_value * tp_multiplier

        tp_max_pct = float(os.getenv('VIBE_ATR_TP_MAX_PCT', '0.05'))
        sl_max_pct = float(os.getenv('VIBE_ATR_SL_MAX_PCT', '0.03'))

        sl_distance = min(raw_sl_distance, last_close * sl_max_pct)
        tp_distance = min(raw_tp_distance, last_close * tp_max_pct)

        if side == 'buy':
            stop_loss_price = last_close - sl_distance
            take_profit_price = last_close + tp_distance
        else:
            stop_loss_price = last_close + sl_distance
            take_profit_price = last_close - tp_distance

        return round(stop_loss_price, 4), round(take_profit_price, 4)

    def _calculate_quantity(self, balance: float, entry_price: float, stop_loss_price: float) -> float:
        risk_amount = balance * self.risk_per_trade
        stop_distance = abs(entry_price - stop_loss_price)
        if stop_distance <= 0:
            return 0.0
        return round(risk_amount / stop_distance, 6)

    def _wait_signal(self, symbol: str, timestamp: int, reason: str, daily_snapshot: RegimeSnapshot, intraday_snapshot: RegimeSnapshot) -> dict[str, Any]:
        reasoning = self._compose_wait_reason(reason, daily_snapshot, intraday_snapshot)
        signal = {
            'timestamp': int(timestamp / 1000),
            'symbol': symbol,
            'side': 'buy',
            'leverage': self.leverage,
            'stop_loss_price': None,
            'take_profit_price': None,
            'quantity': 0.0,
            'action': 'WAIT',
            'status': 'REST_DAY' if 'volatility' in reason.lower() else 'WAIT',
            'reason': reasoning,
            'daily_regime': daily_snapshot.regime,
            'intraday_regime': intraday_snapshot.regime,
        }
        if self.publisher:
            self.publisher.publish(signal)
        return signal

    def _compose_wait_reason(self, reason: str, daily_snapshot: RegimeSnapshot, intraday_snapshot: RegimeSnapshot) -> str:
        if daily_snapshot.regime == 'HIGH_VOLATILITY' or intraday_snapshot.regime == 'HIGH_VOLATILITY':
            return 'Volatility is too strong, ATR is high and stop loss sweep risk is large, prioritizing staying out to preserve capital.'
        if daily_snapshot.regime == 'SIDEWAYS' and intraday_snapshot.regime == 'SIDEWAYS':
            return 'Market is tight and lacks a clear direction, waiting for confirmation breakout before placing order.'
        return reason


class AITradingSignalGenerator(VibeTradingSignalGenerator):
    """
    Subclass that uses Market Microstructure AI Sentiment instead of technical setup.
    """
    def __init__(self, exchange: ccxt.Exchange, sentiment_file: str, llm_file: str = None, publisher: RedisSignalPublisher | None = None) -> None:
        super().__init__(exchange, publisher)
        self.sentiment_dict = self._load_sentiment(sentiment_file)
        self.llm_events = self._load_llm_sentiment(llm_file) if llm_file else []
        
    def _load_llm_sentiment(self, filepath: str) -> list[tuple[int, float]]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            events: list[tuple[int, float]] = []
            for item in data:
                d = item.get('date')
                if d and 'sentiment_score' in item:
                    parsed = datetime.fromisoformat(str(d).replace('Z', '+00:00'))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    events.append((int(parsed.timestamp() * 1000), float(item['sentiment_score'])))
            return sorted(events)
        except Exception as e:
            logger.error(f"Failed to load LLM sentiment file: {e}")
            return []

    def _get_llm_score(self, target_timestamp: int) -> float | None:
        """Mean of news scores observed in the preceding 24h, never future news."""
        recent = [score for ts, score in self.llm_events if target_timestamp - 86_400_000 < ts <= target_timestamp]
        return sum(recent) / len(recent) if recent else None

    def _load_sentiment(self, filepath: str) -> dict[str, list[dict]]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # data is now a dict: { "BTCUSDT": [ {timestamp_ms, ...}, ... ] }
            return data
        except Exception as e:
            logger.error(f"Failed to load sentiment file: {e}")
            return {}

    def _get_microstructure_record(self, symbol: str, target_timestamp: int) -> dict | None:
        # Convert BTC/USDT to BTCUSDT to match the keys in our JSON
        binance_symbol = symbol.replace("/", "")
        records = self.sentiment_dict.get(binance_symbol, [])
        # Find the most recent record before or equal to target_timestamp
        for row in reversed(records):
            if row['timestamp_ms'] <= target_timestamp:
                return row
        return None

    def generate(self, symbol: str, candles_1d: Sequence[Candle], candles_4h: Sequence[Candle], balance: float) -> dict[str, Any]:
        daily_snapshot = self._snapshot(candles_1d)
        intraday_snapshot = self._snapshot(candles_4h)
        latest_close = candles_4h[-1].close
        latest_ts = candles_4h[-1].timestamp
        
        # 1. Regime Filter Synchronization
        if daily_snapshot.regime == 'HIGH_VOLATILITY' or intraday_snapshot.regime == 'HIGH_VOLATILITY':
            return self._wait_signal(symbol, latest_ts, "Volatility is too strong", daily_snapshot, intraday_snapshot)
        if daily_snapshot.regime == 'SIDEWAYS' and intraday_snapshot.regime == 'SIDEWAYS':
            return self._wait_signal(symbol, latest_ts, "Market is sideways", daily_snapshot, intraday_snapshot)

        record = self._get_microstructure_record(symbol, latest_ts)
        if not record:
            return self._wait_signal(symbol, latest_ts, "No AI data available", daily_snapshot, intraday_snapshot)

        market_power_score = record.get('market_power_score', 0.0)
        
        llm_score = self._get_llm_score(latest_ts)
        if llm_score is not None:
            market_power_score += llm_score

        direction = None
        reason = "Waiting for extreme AI market power score"
        
        # AI Mode logic: Trend-following on strong scores (matches live system)
        threshold = 15.0
        if market_power_score > threshold:
            direction = 'buy'
            reason = f'AI Strong Bullish Score ({market_power_score:.1f})'
        elif market_power_score < -threshold:
            direction = 'sell'
            reason = f'AI Strong Bearish Score ({market_power_score:.1f})'

        if direction is None:
            return self._wait_signal(symbol, latest_ts, reason, daily_snapshot, intraday_snapshot)

        # SMC Execution logic: build SL/TP based on ATR and recent structure
        stop_loss_price, take_profit_price = self._build_levels(direction, candles_4h)
        quantity = self._calculate_quantity(balance, latest_close, stop_loss_price)

        signal = {
            'timestamp': int(latest_ts / 1000),
            'symbol': symbol,
            'side': direction,
            'leverage': self.leverage,
            'entry_price': latest_close,
            'stop_loss_price': stop_loss_price,
            'take_profit_price': take_profit_price,
            'quantity': quantity,
            'action': 'TRADE',
            'regime': intraday_snapshot.regime,
            'reason': reason,
            'risk_per_trade': self.risk_per_trade,
            'market_power_score': market_power_score
        }
        if self.publisher:
            self.publisher.publish(signal)
        return signal

class HybridTradingSignalGenerator(AITradingSignalGenerator):
    """
    Hybrid Mode: Uses Vibe (Technical) for signal generation, but uses AI (Microstructure) as a Rule Guard.
    Only allows trades when the AI score confirms the technical direction (VETO system).
    """
    def generate(self, symbol: str, candles_1d: Sequence[Candle], candles_4h: Sequence[Candle], balance: float) -> dict[str, Any]:
        # 1. Get base signal from Vibe (Technical SMC + Regime Filters)
        # We explicitly call VibeTradingSignalGenerator.generate to bypass AITradingSignalGenerator's override
        base_signal = VibeTradingSignalGenerator.generate(self, symbol, candles_1d, candles_4h, balance)
        
        # If Tech already decided to WAIT, just pass it through
        if base_signal.get('action') != 'TRADE':
            return base_signal
            
        # 2. Get AI Score
        latest_ts = candles_4h[-1].timestamp
        daily_snapshot = self._snapshot(candles_1d)
        intraday_snapshot = self._snapshot(candles_4h)
        record = self._get_microstructure_record(symbol, latest_ts)
        # A controlled multi-source experiment must not silently replace missing
        # positioning with a funding-derived synthetic proxy.
        if record is None or record.get('data_source') != 'real':
            return self._wait_signal(symbol, latest_ts, 'AI Guard unavailable: no observed microstructure', daily_snapshot, intraday_snapshot)
        llm_score = self._get_llm_score(latest_ts)
        if llm_score is None:
            return self._wait_signal(symbol, latest_ts, 'AI Guard unavailable: no point-in-time news', daily_snapshot, intraday_snapshot)
        market_power_score = float(record.get('market_power_score', 0.0)) + llm_score

        # 3. AI Gate Logic (Guardrail / Veto System)
        threshold = 15.0
        tech_direction = base_signal.get('side')
        
        if tech_direction == 'buy' and market_power_score < -threshold:
            return self._wait_signal(symbol, latest_ts, f"AI Guard: Veto Buy (Strong Bearish AI: {market_power_score:.1f})", daily_snapshot, intraday_snapshot)
                
        elif tech_direction == 'sell' and market_power_score > threshold:
            return self._wait_signal(symbol, latest_ts, f"AI Guard: Veto Sell (Strong Bullish AI: {market_power_score:.1f})", daily_snapshot, intraday_snapshot)

        # 4. Allowed by AI, update reason and return
        base_signal['reason'] = f"Hybrid {tech_direction.title()}: SMC Valid + AI Clear ({market_power_score:.1f})"
        base_signal['market_power_score'] = market_power_score
        
        if self.publisher:
            self.publisher.publish(base_signal)
            
        return base_signal

class Backtester:
    def __init__(
        self,
        exchange: ccxt.Exchange,
        generator: VibeTradingSignalGenerator,
        starting_balance: float = 10_000.0,
        fee_rate: float = 0.0004,
        slippage_bps: float | None = None,
        fill_mode: str | None = None,
    ) -> None:
        self.exchange = exchange
        self.generator = generator
        self.starting_balance = starting_balance
        self.fee_rate = fee_rate
        env_slippage_bps = float(os.getenv('BACKTEST_SLIPPAGE_BPS', '5'))
        self.slippage_bps = env_slippage_bps if slippage_bps is None else slippage_bps
        self.slippage_rate = max(self.slippage_bps, 0.0) / 10_000.0
        self.fill_mode = (fill_mode or os.getenv('BACKTEST_FILL_MODE', 'signal_close')).strip().lower()
        if self.fill_mode not in {'signal_close', 'next_open'}:
            raise ValueError("fill_mode must be 'signal_close' or 'next_open'")

    @staticmethod
    def _drop_incomplete_tail(candles: Sequence[Candle], timeframe_ms: int) -> list[Candle]:
        if not candles:
            return []
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if candles[-1].timestamp + timeframe_ms > now_ms:
            return list(candles[:-1])
        return list(candles)

    def _apply_slippage(self, price: float, side: str, phase: str) -> float:
        if self.slippage_rate <= 0:
            return price
        if phase == 'entry':
            return price * (1 + self.slippage_rate) if side == 'buy' else price * (1 - self.slippage_rate)
        return price * (1 - self.slippage_rate) if side == 'buy' else price * (1 + self.slippage_rate)

    def run(self, symbol: str, days: int = 90) -> BacktestResult:
        hourly_4h = fetch_ohlcv_with_retry(self.exchange, symbol, '4h', limit=max(days * 6, 250))
        daily_1d = fetch_ohlcv_with_retry(self.exchange, symbol, '1d', limit=max(days + 60, 120))

        candles_4h = self._drop_incomplete_tail(to_candles(hourly_4h), 4 * 60 * 60 * 1000)
        candles_1d = self._drop_incomplete_tail(to_candles(daily_1d), 24 * 60 * 60 * 1000)
        analysis_end_ms = candles_4h[-1].timestamp if candles_4h else None
        analysis_start_ms = analysis_end_ms - (days * 86_400_000) if analysis_end_ms is not None and days > 0 else None
        cash = self.starting_balance
        equity_curve = [cash]
        equity_timestamps = [analysis_start_ms or (candles_4h[0].timestamp if candles_4h else 0)]
        trades: list[TradeResult] = []
        signals_generated = 0
        skipped_signals = 0
        consecutive_losses = 0
        positions: list[dict[str, Any]] = []
        pending_signal: dict[str, Any] | None = None
        max_pyramid_layers = max(1, int(os.getenv('MAX_PYRAMID_LAYERS', os.getenv('MAX_PYRAMID_CONTRACTS', '4'))))

        def open_position(signal: dict[str, Any], timestamp: int, raw_entry: float) -> None:
            """Open one pyramid layer using cash and stop-risk available now."""
            nonlocal cash, skipped_signals
            side = signal['side']
            entry_price = self._apply_slippage(raw_entry, side, 'entry')
            stop_loss = float(signal['stop_loss_price'])
            take_profit = float(signal['take_profit_price'])
            effective_balance = min(cash, max_compound_balance)
            quantity = self.generator._calculate_quantity(effective_balance, entry_price, stop_loss)
            entry_fee = quantity * entry_price * self.fee_rate
            worst_exit = self._apply_slippage(stop_loss, side, 'exit')
            worst_exit_fee = quantity * worst_exit * self.fee_rate
            worst_loss = abs(entry_price - worst_exit) * quantity + entry_fee + worst_exit_fee
            reserved_stop_risk = sum(p['worst_loss'] for p in positions)
            if os.getenv('VIBE_PYRAMID_ONLY_WINNERS', 'false').lower() in {'1', 'true', 'yes'}:
                same_side = [p for p in positions if p['signal']['side'] == side]
                if same_side:
                    step = max(float(signal.get('pyramid_step_price', 0.0)), 0.0)
                    anchor = max(p['entry_price'] for p in same_side) if side == 'buy' else min(p['entry_price'] for p in same_side)
                    progressed = entry_price >= anchor + step if side == 'buy' else entry_price <= anchor - step
                    if not progressed:
                        skipped_signals += 1
                        return
            if quantity <= 0 or len(positions) >= max_pyramid_layers or cash < reserved_stop_risk + worst_loss:
                skipped_signals += 1
                return
            cash -= entry_fee
            positions.append({
                'signal': signal, 'entry_timestamp': timestamp, 'entry_price': entry_price,
                'stop_loss': stop_loss, 'take_profit': take_profit, 'quantity': quantity,
                'entry_fee': entry_fee, 'worst_loss': worst_loss,
            })

        max_compound_balance = float(os.getenv('MAX_COMPOUND_BALANCE', '1000.0'))
        original_risk = self.generator.risk_per_trade

        warmup = 80
        for index in range(warmup, len(candles_4h)):
            candle = candles_4h[index]
            if analysis_start_ms is not None and candle.timestamp < analysis_start_ms:
                continue

            # A signal produced at the preceding closed bar fills at this bar's open.
            # Cash is debited immediately for the entry fee; no future PnL is available
            # to subsequent sizing decisions.
            if pending_signal is not None:
                open_position(pending_signal, candle.timestamp, candle.open)
                pending_signal = None

            # Resolve an already-open position using only this bar's OHLC. If both
            # barriers are touched in one bar, choose the adverse stop outcome.
            open_positions: list[dict[str, Any]] = []
            for position in positions:
                side = position['signal']['side']
                hit_stop = candle.low <= position['stop_loss'] if side == 'buy' else candle.high >= position['stop_loss']
                hit_take = candle.high >= position['take_profit'] if side == 'buy' else candle.low <= position['take_profit']
                if hit_stop or hit_take:
                    raw_exit = position['stop_loss'] if hit_stop else position['take_profit']
                    reason = 'STOP_LOSS' if hit_stop else 'TAKE_PROFIT'
                    exit_price = self._apply_slippage(raw_exit, side, 'exit')
                    exit_fee = position['quantity'] * exit_price * self.fee_rate
                    gross_pnl = ((exit_price - position['entry_price']) * position['quantity'] if side == 'buy'
                                 else (position['entry_price'] - exit_price) * position['quantity'])
                    cash += gross_pnl - exit_fee
                    pnl = gross_pnl - position['entry_fee'] - exit_fee
                    trades.append(TradeResult(
                        timestamp=int(position['entry_timestamp'] / 1000),
                        exit_timestamp=int(candle.timestamp / 1000),
                        symbol=symbol, side=side, entry_price=position['entry_price'],
                        exit_price=exit_price, stop_loss_price=position['stop_loss'],
                        take_profit_price=position['take_profit'], quantity=position['quantity'],
                        pnl=pnl, exit_reason=reason,
                    ))
                    consecutive_losses = consecutive_losses + 1 if pnl < 0 else 0
                else:
                    open_positions.append(position)
            positions = open_positions

            # Mark equity every bar. This captures drawdown while a position remains open.
            marked_equity = cash
            for position in positions:
                side = position['signal']['side']
                marked_equity += ((candle.close - position['entry_price']) * position['quantity'] if side == 'buy'
                                  else (position['entry_price'] - candle.close) * position['quantity'])
            equity_curve.append(marked_equity)
            equity_timestamps.append(candle.timestamp)

            # Pyramiding is allowed up to the configured layer cap and reserved
            # stop risk. signal_close matches the live executor's market-order
            # path, with adverse slippage retained as the fill approximation.
            if len(positions) >= max_pyramid_layers or index >= len(candles_4h) - 1:
                continue
            window_4h = candles_4h[: index + 1]
            # Use only fully closed daily candles. A 1D candle timestamp marks its open,
            # so it is closed only after 24h. This keeps backtests aligned with live
            # anti-repaint behavior and avoids using future daily close data.
            window_1d = [candle for candle in candles_1d if candle.timestamp + 86_400_000 <= window_4h[-1].timestamp]
            if len(window_1d) < 60:
                continue

            if consecutive_losses >= 3:
                self.generator.risk_per_trade = original_risk / 3.0
            else:
                self.generator.risk_per_trade = original_risk

            effective_balance = min(cash, max_compound_balance)
            signal = self.generator.generate(symbol, window_1d[-120:], window_4h[-200:], effective_balance)
            if signal['action'] != 'TRADE':
                skipped_signals += 1
                continue

            signals_generated += 1
            if self.fill_mode == 'signal_close':
                open_position(signal, candle.timestamp, candle.close)
            else:
                pending_signal = signal

        # Close any remaining position at the final observable close. This is an
        # explicit end-of-sample liquidation, not a profit known before the end.
        if positions and candles_4h:
            last_candle = candles_4h[-1]
            for position in positions:
                side = position['signal']['side']
                exit_price = self._apply_slippage(last_candle.close, side, 'exit')
                exit_fee = position['quantity'] * exit_price * self.fee_rate
                gross_pnl = ((exit_price - position['entry_price']) * position['quantity'] if side == 'buy'
                             else (position['entry_price'] - exit_price) * position['quantity'])
                cash += gross_pnl - exit_fee
                pnl = gross_pnl - position['entry_fee'] - exit_fee
                trades.append(TradeResult(
                    timestamp=int(position['entry_timestamp'] / 1000),
                    exit_timestamp=int(last_candle.timestamp / 1000),
                    symbol=symbol, side=side, entry_price=position['entry_price'], exit_price=exit_price,
                    stop_loss_price=position['stop_loss'], take_profit_price=position['take_profit'],
                    quantity=position['quantity'], pnl=pnl, exit_reason='END_OF_SAMPLE',
                ))
            equity_curve[-1] = cash

        return BacktestResult(
            starting_balance=self.starting_balance,
            ending_balance=cash,
            trades=trades,
            equity_curve=equity_curve,
            equity_timestamps=equity_timestamps,
            signals_generated=signals_generated,
            skipped_signals=skipped_signals,
            analysis_start_timestamp=int(analysis_start_ms / 1000) if analysis_start_ms is not None else None,
            analysis_end_timestamp=int(analysis_end_ms / 1000) if analysis_end_ms is not None else None,
            period_days=days,
        )

    def _simulate_trade(self, signal: dict[str, Any], entry_window: Sequence[Candle], forward_candles: Sequence[Candle], equity: float) -> TradeResult | None:
        signal_entry_price = entry_window[-1].close
        stop_loss_price = float(signal['stop_loss_price'])
        take_profit_price = float(signal['take_profit_price'])
        side = signal['side']
        entry_price = self._apply_slippage(signal_entry_price, side, 'entry')
        quantity = float(signal['quantity']) if signal.get('quantity') else self.generator._calculate_quantity(equity, signal_entry_price, stop_loss_price)
        quantity = max(quantity, 0.0)
        if quantity == 0:
            return None

        entry_fee = quantity * entry_price * self.fee_rate
        exit_fee = 0.0
        raw_exit_price = forward_candles[-1].close if forward_candles else signal_entry_price
        exit_reason = 'TIME_EXIT'
        exit_timestamp = forward_candles[-1].timestamp if forward_candles else entry_window[-1].timestamp

        for candle in forward_candles:
            if side == 'buy':
                if candle.low <= stop_loss_price:
                    raw_exit_price = stop_loss_price
                    exit_reason = 'STOP_LOSS'
                    exit_timestamp = candle.timestamp
                    break
                if candle.high >= take_profit_price:
                    raw_exit_price = take_profit_price
                    exit_reason = 'TAKE_PROFIT'
                    exit_timestamp = candle.timestamp
                    break
            else:
                if candle.high >= stop_loss_price:
                    raw_exit_price = stop_loss_price
                    exit_reason = 'STOP_LOSS'
                    exit_timestamp = candle.timestamp
                    break
                if candle.low <= take_profit_price:
                    raw_exit_price = take_profit_price
                    exit_reason = 'TAKE_PROFIT'
                    exit_timestamp = candle.timestamp
                    break

        exit_price = self._apply_slippage(raw_exit_price, side, 'exit')
        exit_fee = quantity * exit_price * self.fee_rate
        gross_pnl = (exit_price - entry_price) * quantity if side == 'buy' else (entry_price - exit_price) * quantity
        pnl = gross_pnl - entry_fee - exit_fee

        return TradeResult(
            timestamp=signal['timestamp'],
            exit_timestamp=int(exit_timestamp / 1000),
            symbol=signal['symbol'],
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            quantity=quantity,
            pnl=pnl,
            exit_reason=exit_reason,
        )


def publish_latest_signal(symbol: str, days: int = 14, exchange_id: str | None = None) -> dict[str, Any]:
    exchange = build_exchange(exchange_id)
    redis_client = build_redis()
    publisher = RedisSignalPublisher(redis_client)
    generator = VibeTradingSignalGenerator(exchange, publisher)
    balance = float(redis_client.get('simulated_balance') or 10_000)

    symbol = normalize_derivative_symbol(exchange, symbol)

    raw_4h = fetch_ohlcv_with_retry(exchange, symbol, '4h', limit=max(days * 6, 120))
    raw_1d = fetch_ohlcv_with_retry(exchange, symbol, '1d', limit=max(days + 60, 90))
    candles_4h = to_candles(raw_4h[:-1] if len(raw_4h) > 1 else raw_4h)
    candles_1d = to_candles(raw_1d[:-1] if len(raw_1d) > 1 else raw_1d)
    signal = generator.generate(symbol, candles_1d[-90:], candles_4h[-90:], balance)
    return signal


def run_daily_strategist(symbol: str, days: int = 14, balance: float | None = None, exchange_id: str | None = None) -> dict[str, Any]:
    exchange = build_exchange(exchange_id)
    redis_client = build_redis()
    state_store = RedisStateStore(redis_client)
    generator = VibeTradingSignalGenerator(exchange, publisher=None)

    symbol = normalize_derivative_symbol(exchange, symbol)

    wallet_balance = balance if balance is not None else float(redis_client.get('simulated_balance') or 10_000)
    raw_4h = fetch_ohlcv_with_retry(exchange, symbol, '4h', limit=max(days * 6, 120))
    raw_1d = fetch_ohlcv_with_retry(exchange, symbol, '1d', limit=max(days + 60, 90))
    candles_4h = to_candles(raw_4h[:-1] if len(raw_4h) > 1 else raw_4h)
    candles_1d = to_candles(raw_1d[:-1] if len(raw_1d) > 1 else raw_1d)
    outlook = generator.build_daily_outlook(symbol, candles_1d[-90:], candles_4h[-90:], wallet_balance)
    state_store.save_daily_vibe(outlook)
    return outlook


def format_report(result: BacktestResult) -> str:
    return json.dumps(result.to_dict(), indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description='Vibe-Trading backtester and signal generator')
    parser.add_argument('--symbol', default=os.getenv('BACKTEST_SYMBOL', 'BTC/USDT'))
    parser.add_argument('--days', type=int, default=int(os.getenv('BACKTEST_DAYS', '90')))
    parser.add_argument('--balance', type=float, default=float(os.getenv('BACKTEST_BALANCE', '10000')))
    parser.add_argument('--exchange', default=None, help='Exchange ID override (binance, okx, etc.)')
    parser.add_argument('--slippage-bps', type=float, default=None, help='Adverse slippage in basis points per fill (default: BACKTEST_SLIPPAGE_BPS or 5)')
    parser.add_argument('--publish-latest', action='store_true', help='Publish the latest signal to Redis trading_signals')
    parser.add_argument('--daily-strategist', action='store_true', help='Generate and persist the daily outlook to Redis')
    parser.add_argument('--show-latest-only', action='store_true', help='Only generate and print the latest signal')
    args = parser.parse_args()

    exchange_id = args.exchange or os.getenv('CCXT_EXCHANGE', 'binance')
    exchange = build_exchange(exchange_id)

    symbol = args.symbol
    symbol = normalize_derivative_symbol(exchange, symbol)

    redis_client = build_redis()
    publisher = RedisSignalPublisher(redis_client)
    generator = VibeTradingSignalGenerator(exchange, publisher)

    if args.publish_latest or args.show_latest_only:
        signal = publish_latest_signal(symbol, args.days, exchange_id)
        print(json.dumps(signal, indent=2))
        return

    if args.daily_strategist:
        outlook = run_daily_strategist(symbol, args.days, args.balance, exchange_id)
        print(json.dumps(outlook, indent=2))
        return

    # For backtesting, we do NOT want to publish signals to the live Redis channel
    generator_backtest = VibeTradingSignalGenerator(exchange, publisher=None)
    backtester = Backtester(exchange, generator_backtest, starting_balance=args.balance, slippage_bps=args.slippage_bps)
    result = backtester.run(symbol, days=args.days)
    print(format_report(result))


if __name__ == '__main__':
    main()
