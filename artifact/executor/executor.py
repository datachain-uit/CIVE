from __future__ import annotations

import json
import hashlib
import logging
import math
import os
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, Iterable, Optional, Sequence

import ccxt
import redis
import requests
from dotenv import load_dotenv
from redis.exceptions import RedisError


load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / '.env')

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
)
logger = logging.getLogger('executor')


def safe_float(value: Any) -> float:
    """Safely convert value to float, returning 0.0 if None or invalid."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


@dataclass(slots=True)
class TradingSignal:
    timestamp: int
    symbol: str
    side: str
    leverage: int
    stop_loss_price: float
    take_profit_price: float
    quantity: Optional[float] = None
    action: str = 'TRADE'
    status: Optional[str] = None
    reason: Optional[str] = None
    market_power_score: Optional[float] = None  # Điểm số từ dashboard
    decision_hash: Optional[str] = None

    @classmethod
    def from_json(cls, payload: str | bytes | Dict[str, Any]) -> 'TradingSignal':
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode('utf-8')
        if isinstance(payload, str):
            data = json.loads(payload)
        else:
            data = payload

        required = ['timestamp', 'symbol', 'side', 'leverage', 'stop_loss_price', 'take_profit_price']
        missing = [field for field in required if field not in data]
        if missing:
            raise ValueError(f'missing signal fields: {", ".join(missing)}')

        return cls(
            timestamp=int(data['timestamp']),
            symbol=str(data['symbol']),
            side=str(data['side']).lower(),
            leverage=int(data['leverage']),
            stop_loss_price=safe_float(data.get('stop_loss_price')),
            take_profit_price=safe_float(data.get('take_profit_price')),
            quantity=float(data['quantity']) if data.get('quantity') is not None else None,
            action=str(data.get('action', 'TRADE')).upper(),
            status=str(data.get('status')) if data.get('status') is not None else None,
            reason=str(data.get('reason')) if data.get('reason') is not None else None,
            market_power_score=float(data.get('market_power_score')) if data.get('market_power_score') is not None else None,
            decision_hash=data.get('decision_hash'),
        )


@dataclass(slots=True)
class TradeState:
    trade_id: str
    signal: TradingSignal
    entry_price: float
    quantity: float
    stop_order_id: Optional[str]
    take_profit_order_id: Optional[str]
    breakeven_moved: bool = False
    created_at: int = 0

    def to_mapping(self) -> Dict[str, str]:
        data = {
            'trade_id': self.trade_id,
            'symbol': self.signal.symbol,
            'side': self.signal.side,
            'leverage': str(self.signal.leverage),
            'timestamp': str(self.signal.timestamp),
            'entry_price': f'{self.entry_price:.12f}',
            'quantity': f'{self.quantity:.12f}',
            'stop_loss_price': f'{self.signal.stop_loss_price:.12f}',
            'take_profit_price': f'{self.signal.take_profit_price:.12f}',
            'stop_order_id': self.stop_order_id or '',
            'take_profit_order_id': self.take_profit_order_id or '',
            'breakeven_moved': '1' if self.breakeven_moved else '0',
            'created_at': str(self.created_at or int(time.time())),
        }
        if self.signal.decision_hash:
            data['decision_hash'] = self.signal.decision_hash
        return data


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
class AutoTradeDecision:
    should_trade: bool
    side: Optional[str] = None
    reason: str = ''
    market_power_score: float = 0.0
    whale_score: float = 0.0
    adx: float = 0.0
    rsi: float = 50.0
    symbol: str = 'BTC/USDT'
    market_power_status: str = ''
    market_power_action: str = 'WAIT'
    news_score: float = 0.0
    news_reason: str = 'Not yet analyzed'
    entry_price: Optional[float] = None   # Precision limit price (None = market)
    entry_type: str = 'Market'            # 'Limit@FVG' | 'Limit@OB' | 'Market'
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    signal_candle_timestamp: Optional[int] = None
    rr_ratio: float = 0.0


class RedisSignalStore:
    def __init__(self, client: redis.Redis, history_key: str = 'recent_signals', active_set_key: str = 'active_trade_ids') -> None:
        self.client = client
        self.history_key = history_key
        self.active_set_key = active_set_key

    def push_history(self, signal: TradingSignal, outcome: str, detail: Optional[str] = None) -> None:
        payload = {
            **asdict(signal),
            'outcome': outcome,
            'detail': detail,
            'stored_at': int(time.time()),
        }
        payload['signal_hash'] = self._stable_hash(payload)
        payload['proof_status'] = 'pending_onchain'
        self.client.lpush(self.history_key, json.dumps(payload, separators=(',', ':')))
        self.client.ltrim(self.history_key, 0, 99)

    def push_agent_decision(self, decision: dict[str, Any]) -> str:
        payload = {
            **decision,
            'stored_at': int(time.time()),
            'agent_id': os.getenv('AGENT_ID', 'vibe-agent'),
            'agent_version': os.getenv('AGENT_VERSION', 'vibe-parity-v1'),
            'proof_status': os.getenv('AGENT_PROOF_STATUS', 'local_hash'),
        }
        dh = self._stable_hash(payload)
        payload['decision_hash'] = dh
        self.client.lpush('agent_decision_journal', json.dumps(payload, separators=(',', ':'), default=str))
        self.client.ltrim('agent_decision_journal', 0, 199)
        return dh

    @staticmethod
    def _stable_hash(payload: dict[str, Any]) -> str:
        hash_payload = {
            key: value
            for key, value in payload.items()
            if key not in {'signal_hash', 'decision_hash', 'tx_hash', 'proof_tx_hash'}
        }
        encoded = json.dumps(hash_payload, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
        return hashlib.sha256(encoded).hexdigest()

    def save_trade(self, trade: TradeState) -> None:
        trade_key = f'trade:{trade.trade_id}'
        self.client.hset(trade_key, mapping=trade.to_mapping())
        self.client.expire(trade_key, 60 * 60 * 24)
        self.client.sadd(self.active_set_key, trade.trade_id)

    def delete_trade(self, trade_id: str) -> None:
        self.client.delete(f'trade:{trade_id}')
        self.client.srem(self.active_set_key, trade_id)

    def load_active_trade_ids(self) -> list[str]:
        raw_ids = self.client.smembers(self.active_set_key)
        return sorted(item.decode('utf-8') for item in raw_ids)

    def load_trade(self, trade_id: str) -> Optional[Dict[str, str]]:
        raw = self.client.hgetall(f'trade:{trade_id}')
        if not raw:
            return None
        return {key.decode('utf-8'): value.decode('utf-8') for key, value in raw.items()}


class TradingExecutor:
    def __init__(self) -> None:
        self.redis = self._create_redis()
        self.signal_store = RedisSignalStore(self.redis)
        self.dry_run = False
        self.exchange_platform = os.getenv('EXCHANGE_PLATFORM', 'okx').strip().lower()
        self.is_demo = os.getenv('IS_DEMO', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}
        # BYBIT_USE_TESTNET=true  -> api-testnet.bybit.com (key từ testnet.bybit.com)
        # BYBIT_USE_TESTNET=false -> api-demo.bybit.com    (key từ demo.bybit.com)
        self.bybit_use_testnet = os.getenv('BYBIT_USE_TESTNET', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}
        self.margin_mode = os.getenv('MARGIN_MODE', 'isolated').strip().lower()
        self.market_data_platform = os.getenv('MARKET_DATA_EXCHANGE_PLATFORM', self.exchange_platform).strip().lower()
        self.market_data_is_demo = os.getenv('MARKET_DATA_IS_DEMO', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}
        # Nạp thông tin OKX trước khi khởi tạo exchange để tránh AttributeError.
        self.okx_api_key = os.getenv('OKX_API_KEY') or os.getenv('OKX_TESTNET_API_KEY') or ''
        self.okx_secret = os.getenv('OKX_SECRET') or os.getenv('OKX_SECRET_KEY') or os.getenv('OKX_TESTNET_SECRET') or ''
        self.okx_passphrase = os.getenv('OKX_PASSPHRASE') or os.getenv('OKX_API_PASSPHRASE') or ''
        self.okx_market_type = os.getenv('OKX_MARKET_TYPE', 'swap')
        self.bybit_market_type = os.getenv('BYBIT_MARKET_TYPE', 'swap')
        self.bybit_account_type = os.getenv('BYBIT_ACCOUNT_TYPE', 'UNIFIED')
        self.exchange = self._create_exchange()
        self.market_data_exchange = self._create_market_data_exchange()
        self.signal_channel = os.getenv('REDIS_SIGNAL_CHANNEL', 'trading_signals')
        self.signal_pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        self.signal_pubsub.subscribe(self.signal_channel)
        self.risk_per_trade = float(os.getenv('RISK_PER_TRADE', '0.01'))
        self.max_position_fraction = float(os.getenv('MAX_POSITION_FRACTION', '0.25'))
        # Number of pyramid layers and total risk are deliberately separate.
        # A high layer cap permits adding entries; it must not turn a transient
        # burst of signals into unbounded loss at the configured stop prices.
        self.max_total_open_risk_pct = float(os.getenv('MAX_TOTAL_OPEN_RISK_PCT', '0.06'))
        self.breakeven_trigger = float(os.getenv('BREAKEVEN_TRIGGER', '0.5'))
        self.poll_interval = int(os.getenv('MONITOR_INTERVAL_SECONDS', '10'))
        self.signal_poll_interval = float(os.getenv('SIGNAL_POLL_INTERVAL_SECONDS', '1.0'))
        self.auto_trade_enabled = os.getenv('AUTO_TRADE_ENABLED', 'true').lower() in {'1', 'true', 'yes', 'on'}
        self.auto_trade_interval = float(os.getenv('AUTO_TRADE_POLL_INTERVAL_SECONDS', '30'))
        self.auto_trade_symbol = os.getenv('AUTO_TRADE_SYMBOL', 'BTC/USDT')
        self.auto_trade_balance_fraction = float(os.getenv('AUTO_TRADE_BALANCE_FRACTION', '0.10'))
        self.forced_leverage = int(os.getenv('FORCED_LEVERAGE', '3'))
        self.auto_trade_leverage = self.forced_leverage
        self.auto_trade_take_profit_pct = float(os.getenv('AUTO_TRADE_TP_PERCENT', '0.03'))
        self.auto_trade_stop_loss_pct = float(os.getenv('AUTO_TRADE_SL_PERCENT', '0.015'))
        self.auto_trade_score_threshold = float(os.getenv('AUTO_TRADE_SCORE_THRESHOLD', '50'))
        self.auto_trade_test_threshold = float(os.getenv('AUTO_TRADE_TEST_THRESHOLD', '5'))
        self.auto_trade_test_window_seconds = int(os.getenv('AUTO_TRADE_TEST_WINDOW_SECONDS', '300'))
        self.auto_trade_hybrid_enabled = os.getenv('AUTO_TRADE_HYBRID_ENABLED', 'true').lower() in {'1', 'true', 'yes', 'on'}
        self.auto_trade_hybrid_score_floor = float(os.getenv('AUTO_TRADE_HYBRID_SCORE_FLOOR', '12'))
        self.auto_trade_hybrid_adx_min = float(os.getenv('AUTO_TRADE_HYBRID_ADX_MIN', '18'))
        self.auto_trade_hybrid_rsi_buy_min = float(os.getenv('AUTO_TRADE_HYBRID_RSI_BUY_MIN', '52'))
        self.auto_trade_hybrid_rsi_sell_max = float(os.getenv('AUTO_TRADE_HYBRID_RSI_SELL_MAX', '48'))
        self.auto_trade_hybrid_tf = os.getenv('AUTO_TRADE_HYBRID_TIMEFRAME', '1h')
        self.auto_trade_hybrid_lookback = int(os.getenv('AUTO_TRADE_HYBRID_LOOKBACK', '120'))
        self.disable_protective_orders = os.getenv('DISABLE_PROTECTIVE_ORDERS', 'false').lower() in {'1', 'true', 'yes', 'on'}
        self.vibe_parity_mode = os.getenv('VIBE_PARITY_MODE', 'true').lower() in {'1', 'true', 'yes', 'on'}
        self.smc_enabled = os.getenv('SMC_ENABLED', 'false').lower() in {'1', 'true', 'yes', 'on'}
        self.breakeven_enabled = os.getenv('BREAKEVEN_ENABLED', 'false').lower() in {'1', 'true', 'yes', 'on'}
        self.okx_td_mode = os.getenv('OKX_TD_MODE', self.margin_mode).strip().lower()
        # Pyramiding: 0 = off; >0 = max same-direction entry layers.
        # MAX_PYRAMID_CONTRACTS is kept as a legacy alias for MAX_PYRAMID_LAYERS.
        self.max_pyramid_layers = int(os.getenv('MAX_PYRAMID_LAYERS', os.getenv('MAX_PYRAMID_CONTRACTS', '0')))
        self.max_pyramid_contracts = self.max_pyramid_layers
        # Cooldown giữa các lần auto-trade — ngăn spam lệnh khi score liên tục đạt ngưỡng.
        self.auto_trade_cooldown_seconds = int(os.getenv('AUTO_TRADE_COOLDOWN_SECONDS', '1800'))
        self._last_auto_trade_at: float = 0.0
        # 'vibe'  = Vibe Strategy (EMA/MACD/ADX — backtest proven x30)
        # 'ai'    = AI score-based contrarian (requires backend + Gemini)
        self.auto_trade_mode = os.getenv('AUTO_TRADE_MODE', 'vibe').strip().lower()
        self.auto_trade_started_at = time.time()
        self.backend_dashboard_url = os.getenv('BACKEND_DASHBOARD_URL', 'http://127.0.0.1:8001/dashboard')
        self.discord_webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
        self.daily_loss_limit_pct = float(os.getenv('DAILY_LOSS_LIMIT_PCT', '0.05'))
        self.daily_summary_interval_seconds = int(os.getenv('DAILY_SUMMARY_INTERVAL_SECONDS', str(24 * 60 * 60)))
        self._starting_balance: Optional[float] = None
        self._stopped_due_to_daily_loss = False
        self._daily_summary_started_at = time.time()
        self._daily_stats_lock = threading.Lock()
        self._daily_trades_count = 0
        self._daily_wins_count = 0
        self._daily_losses_count = 0
        self._daily_total_pnl = 0.0
        self._daily_realized_pnl = 0.0
        self._daily_start_balance: Optional[float] = None
        self._consecutive_losses = 0
        self._ip_whitelist_warned = False  # Suppress repeated OKX 50110 IP whitelist spam
        self._last_auto_trade_candle_ts: dict[str, int] = {}

    @property
    def live_trading_mode(self) -> bool:
        return not self.dry_run

    def _create_redis(self) -> redis.Redis:
        url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        return redis.Redis.from_url(url, decode_responses=False, socket_connect_timeout=5, socket_timeout=5)

    def _create_exchange(self) -> ccxt.Exchange:
        exchange_id = self.exchange_platform
        if not hasattr(ccxt, exchange_id):
            raise ValueError(f'unsupported exchange: {exchange_id}')

        exchange_class = getattr(ccxt, exchange_id)

        if exchange_id == 'okx':
            cfg: dict[str, object] = {
                'apiKey': self.okx_api_key,
                'secret': self.okx_secret,
                'password': self.okx_passphrase,
                'enableRateLimit': True,
                'timeout': 15000,
                'options': {
                    'defaultType': self.okx_market_type,
                },
            }

            if not self.okx_api_key or not self.okx_secret or not self.okx_passphrase:
                self.dry_run = True
                logger.warning('Thiếu thông tin OKX, chuyển sang dry-run cho đến khi có API key/secret/passphrase')

            exchange = exchange_class(cfg)
            if self.is_demo:
                try:
                    exchange.set_sandbox_mode(True)
                    logger.info('OKX demo mode đã được bật bằng sandbox mode')
                except Exception as exc:
                    logger.warning('Không bật được sandbox mode cho OKX: %s', exc)
            return exchange

        if exchange_id == 'bybit':
            # Chọn key theo môi trường:
            #   BYBIT_USE_TESTNET=true  -> key từ testnet.bybit.com  -> api-testnet.bybit.com
            #   BYBIT_USE_TESTNET=false -> key từ demo.bybit.com     -> api-demo.bybit.com
            if self.bybit_use_testnet:
                api_key = (
                    os.getenv('BYBIT_TESTNET_API_KEY')
                    or os.getenv('BYBIT_DEMO_API_KEY')
                    or os.getenv('BYBIT_API_KEY')
                    or ''
                )
                secret = (
                    os.getenv('BYBIT_TESTNET_SECRET')
                    or os.getenv('BYBIT_DEMO_SECRET')
                    or os.getenv('BYBIT_SECRET')
                    or os.getenv('BYBIT_SECRET_KEY')
                    or ''
                )
            elif self.is_demo:
                api_key = (
                    os.getenv('BYBIT_DEMO_API_KEY')
                    or os.getenv('BYBIT_TESTNET_API_KEY')
                    or os.getenv('BYBIT_API_KEY')
                    or ''
                )
                secret = (
                    os.getenv('BYBIT_DEMO_SECRET')
                    or os.getenv('BYBIT_TESTNET_SECRET')
                    or os.getenv('BYBIT_SECRET')
                    or os.getenv('BYBIT_SECRET_KEY')
                    or ''
                )
            else:
                api_key = os.getenv('BYBIT_API_KEY') or os.getenv('BYBIT_DEMO_API_KEY') or os.getenv('BYBIT_TESTNET_API_KEY') or ''
                secret = os.getenv('BYBIT_SECRET') or os.getenv('BYBIT_SECRET_KEY') or os.getenv('BYBIT_DEMO_SECRET') or os.getenv('BYBIT_TESTNET_SECRET') or ''

            cfg: dict[str, object] = {
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
                'timeout': 15000,
                'options': {
                    'defaultType': self.bybit_market_type,
                    'defaultSubType': os.getenv('BYBIT_MARKET_SUBTYPE', 'linear'),
                    'recvWindow': 10000,
                    'adjustForTimeDifference': True,
                },
            }

            if not api_key or not secret:
                self.dry_run = True
                logger.warning('Bybit credentials missing; running in dry-run mode until credentials are available')

            exchange = exchange_class(cfg)
            if self.bybit_use_testnet:
                try:
                    # Testnet: key từ testnet.bybit.com -> api-testnet.bybit.com
                    exchange.urls['api'] = {
                        'public': 'https://api-testnet.bybit.com',
                        'private': 'https://api-testnet.bybit.com',
                    }
                    exchange.urls['www'] = 'https://testnet.bybit.com'
                    exchange.urls['test'] = 'https://api-testnet.bybit.com'
                    exchange.has['fetchCurrencies'] = False
                    logger.info('Bybit TESTNET mode enabled (key=%s...) — routing to api-testnet.bybit.com', api_key[:6])
                except Exception as exc:
                    logger.warning('Unable to enable Bybit testnet mode: %s', exc)
            elif self.is_demo:
                try:
                    # Demo Trading: key từ demo.bybit.com -> api-demo.bybit.com
                    exchange.options['demo'] = True
                    exchange.urls['api'] = {
                        'public': 'https://api-demo.bybit.com',
                        'private': 'https://api-demo.bybit.com',
                    }
                    exchange.urls['www'] = 'https://demo.bybit.com'
                    exchange.urls['test'] = 'https://api-demo.bybit.com'
                    exchange.has['fetchCurrencies'] = False
                    logger.info('Bybit DEMO mode enabled (key=%s...) — routing to api-demo.bybit.com', api_key[:6])
                except Exception as exc:
                    logger.warning('Unable to enable Bybit demo trading mode: %s', exc)
            else:
                logger.info('Bybit LIVE mode enabled (key=%s...) — routing to api.bybit.com', api_key[:6])
            return exchange

        api_key = os.getenv('BINANCE_API_KEY') or os.getenv('BINANCE_TESTNET_API_KEY') or ''
        secret = os.getenv('BINANCE_SECRET') or os.getenv('BINANCE_TESTNET_SECRET') or ''
        cfg = {
            'apiKey': api_key,
            'secret': secret,
            'enableRateLimit': True,
            'timeout': 15000,
            'options': {
                'defaultType': os.getenv('BINANCE_MARKET_TYPE', 'future'),
                'recvWindow': 10000,
                'adjustForTimeDifference': True,
            },
            'urls': {
                'api': {
                    'public': 'https://testnet.binancefuture.com/fapi/v1',
                    'private': 'https://testnet.binancefuture.com/fapi/v1',
                }
            },
        }

        if not api_key or not secret:
            self.dry_run = True
            logger.warning('Binance credentials missing; running in dry-run mode until credentials are available')

        exchange = exchange_class(cfg)

        if exchange_id == 'binance':
            try:
                # CRITICAL: Override all URLs to use testnet endpoint
                exchange.urls['api']['public'] = 'https://testnet.binancefuture.com/fapi/v1'
                exchange.urls['api']['private'] = 'https://testnet.binancefuture.com/fapi/v1'
                logger.debug('Exchange URLs overridden to testnet: %s', exchange.urls['api'])
            except Exception as exc:
                logger.warning('Failed to override exchange URLs: %s', exc)

            try:
                exchange.set_sandbox_mode(False)
            except Exception:
                logger.debug('exchange does not support set_sandbox_mode or it failed; continuing')
            try:
                exchange.has['fetchCurrencies'] = False
            except Exception:
                logger.debug('unable to set exchange.has["fetchCurrencies"]; continuing')

            try:
                exchange.has['fetchMarkets'] = True
            except Exception:
                logger.debug('unable to set exchange.has["fetchMarkets"]; continuing')

            try:
                exchange.sapiGetMarginAllPairs = lambda params=None: []
                exchange.sapiGetMarginIsolatedAllPairs = lambda params=None: []
            except Exception:
                logger.debug('unable to monkeypatch sapiGetMarginAllPairs/isolate; continuing')

            def filtered_load_markets(params: dict | None = None):
                try:
                    markets = exchange.fetch_fapi_markets(params or {})
                    return exchange.set_markets(markets)
                except Exception:
                    return exchange.__class__.load_markets(exchange, params or {})

            exchange.load_markets = filtered_load_markets

        return exchange

    def _create_market_data_exchange(self) -> ccxt.Exchange:
        exchange_id = self.market_data_platform
        if not hasattr(ccxt, exchange_id):
            raise ValueError(f'unsupported market data exchange: {exchange_id}')

        exchange_class = getattr(ccxt, exchange_id)
        # Tăng rateLimit lên 200ms (mặc định CCXT thường là 50-100ms)
        # để CCXT tự điều tiết bandwidth trước khi Bybit reject 10006
        rate_limit_ms = int(os.getenv('MARKET_DATA_RATE_LIMIT_MS', '200'))
        cfg: dict[str, object] = {
            'enableRateLimit': True,
            'rateLimit': rate_limit_ms,
            'timeout': 15000,
        }
        if exchange_id == 'okx':
            cfg['options'] = {'defaultType': self.okx_market_type}
        elif exchange_id == 'binance':
            cfg['options'] = {'defaultType': os.getenv('BINANCE_MARKET_TYPE', 'future')}
        elif exchange_id == 'bybit':
            cfg['options'] = {
                'defaultType': self.bybit_market_type,
                'defaultSubType': os.getenv('BYBIT_MARKET_SUBTYPE', 'linear'),
            }

        exchange = exchange_class(cfg)
        if self.market_data_is_demo:
            try:
                exchange.set_sandbox_mode(True)
                logger.info('Market data exchange %s sandbox mode enabled (rateLimit=%dms)', exchange_id, rate_limit_ms)
            except Exception as exc:
                logger.warning('Unable to enable sandbox mode for market data exchange %s: %s', exchange_id, exc)
        else:
            logger.info('Market data exchange %s uses live public data (rateLimit=%dms)', exchange_id, rate_limit_ms)
        return exchange

    def _fetch_balance_params(self) -> Dict[str, Any]:
        # OKX dùng tài khoản Trading cho Futures, nên cần type=trading.
        if self.exchange_platform == 'okx':
            return {'type': 'trading'}
        if self.exchange_platform == 'bybit':
            return {'accountType': self.bybit_account_type}
        return {}

    def _order_mode_params(self, reduce_only: bool = False) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            'reduceOnly': reduce_only,
        }
        if self.exchange_platform == 'okx':
            # OKX Futures/Swap yêu cầu tdMode='cross' hoặc 'isolated' (KHÔNG phải 'margin').
            # self.okx_td_mode được đọc từ OKX_TD_MODE trong .env (mặc định 'cross').
            # Dùng okx_td_mode thay vì margin_mode để tránh nhầm sang Spot Margin account.
            params.update({
                'tdMode': self.okx_td_mode,
            })
        elif self.exchange_platform == 'binance':
            params['newOrderRespType'] = 'RESULT'
        return params

    def _apply_position_settings(self, symbol: str, leverage: int) -> None:
        # Ép kiểu int để tránh lỗi "lever should be between 1 and 125".
        leverage = max(1, int(leverage))
        try:
            params: Dict[str, Any] = {'marginMode': self.margin_mode}
            if self.exchange_platform == 'bybit':
                params['category'] = os.getenv('BYBIT_CATEGORY', 'linear')
            self.exchange.set_leverage(leverage, symbol, params)
        except Exception as exc:
            logger.warning('Unable to set leverage/margin mode for %s: %s', symbol, exc)

    def run(self) -> None:
        logger.info('Starting executor')
        # Send a startup notification to Discord so we can verify webhook connectivity
        try:
            self._send_discord_message('🚀 Bot đã kết nối thành công!', 'Đang canh me thị trường...', 16776960)
        except Exception:
            # Avoid startup crash if notifier fails for any reason
            logger.debug('Startup Discord notification failed (ignored)')
        self._warm_up_exchange()
        try:
            self._starting_balance = self._fetch_usdt_balance_with_retry()
            logger.info('Starting balance snapshot: %.2f USDT', self._starting_balance)
        except Exception as exc:
            logger.warning('Unable to capture starting balance: %s', exc)

        # ── Khôi phục daily stats từ Redis nếu cùng ngày (tồn tại khi restart) ──
        self._restore_daily_stats_from_redis()

        monitor_thread = threading.Thread(target=self._monitor_active_trades, daemon=True)
        monitor_thread.start()

        daily_summary_thread = threading.Thread(target=self._daily_summary_loop, daemon=True)
        daily_summary_thread.start()

        if self.auto_trade_enabled:
            auto_trade_thread = threading.Thread(target=self._auto_trade_loop, daemon=True)
            auto_trade_thread.start()
            logger.info('Auto-trade mode enabled for %s', self.auto_trade_symbol)
        else:
            logger.info('Auto-trade mode disabled')

        while True:
            try:
                message = self.signal_pubsub.get_message(timeout=self.signal_poll_interval)
                if not message or message.get('type') != 'message':
                    continue

                payload = message.get('data')
                if payload is None:
                    continue
                signal = TradingSignal.from_json(payload)
                self._handle_signal(signal)
            except (RedisError, ccxt.NetworkError, ccxt.RateLimitExceeded) as exc:
                logger.warning('Transient runtime error: %s', exc)
                self._reconnect_signal_stream()
                time.sleep(10)
            except (ValueError, json.JSONDecodeError) as exc:
                logger.exception('Invalid signal payload: %s', exc)
            except ccxt.ExchangeError as exc:
                logger.exception('Exchange rejected signal: %s', exc)
                time.sleep(10)
            except KeyboardInterrupt:
                logger.info('Stopping executor')
                return
            except Exception as exc:  # pragma: no cover - defensive guard for 24/7 process
                logger.exception('Unhandled error: %s', exc)
                time.sleep(10)

    def _reconnect_signal_stream(self) -> None:
        try:
            self.signal_pubsub.close()
        except Exception:
            pass
        self.signal_pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        self.signal_pubsub.subscribe(self.signal_channel)

    def _warm_up_exchange(self) -> None:
        for attempt in range(3):
            try:
                self.exchange.load_markets()
                logger.info('Exchange markets loaded')
                try:
                    self.market_data_exchange.load_markets()
                    logger.info('Market data exchange markets loaded')
                except Exception as exc:
                    logger.warning('Market data exchange warm-up failed: %s', exc)
                self._send_discord_message('🚀 Hệ thống khởi động', 'Bot đã sẵn sàng đi săn! Chế độ: Autopilot', 0x00ff00)
                return
            except (ccxt.NetworkError, ccxt.RateLimitExceeded) as exc:
                logger.warning('Exchange warm-up failed (attempt %s): %s', attempt + 1, exc)
                time.sleep(2 ** attempt)
        raise RuntimeError('unable to load exchange markets after retries')

    def _handle_signal(self, signal: TradingSignal) -> None:
        if signal.action in {'WAIT', 'REST_DAY'} or signal.status == 'REST_DAY':
            reason = signal.reason or 'market regime filter requested no trade'
            logger.info('Skipping trade for %s: %s', signal.symbol, reason)
            self.signal_store.push_history(signal, 'skipped', reason)
            return

        if not self.auto_trade_enabled:
            reason = 'auto-trade disabled (MONITORING mode)'
            logger.info('Skipping trade for %s: %s', signal.symbol, reason)
            self.signal_store.push_history(signal, 'skipped', reason)
            return

        # Chặn signal có score quá thấp - tránh spam lệnh khi score chưa đủ ngưỡng
        if signal.market_power_score is not None:
            if abs(signal.market_power_score) < self.auto_trade_score_threshold:
                reason = f'Score {signal.market_power_score:.2f} is below the threshold of {self.auto_trade_score_threshold}'
                logger.info('Bỏ qua tín hiệu %s: %s', signal.symbol, reason)
                self.signal_store.push_history(signal, 'skipped', reason)
                return

        if signal.side not in {'buy', 'sell'}:
            raise ValueError(f'invalid trade side: {signal.side}')

        # enforce leverage lock for any incoming signal
        signal.leverage = self.forced_leverage
        self._check_daily_loss_and_maybe_stop()

        trade = self._open_trade(signal)
        self.signal_store.push_history(signal, 'executed', f'trade_id={trade.trade_id}')
        self.signal_store.save_trade(trade)
        logger.info('Trade opened: %s', trade.trade_id)
        self._send_discord_message(
            title=f'TRADE OPENED - {signal.side.upper()}',
            message='Lệnh từ signal queue đã được khớp.',
            color=0x2ECC71 if signal.side == 'buy' else 0xE74C3C,
            fields=[
                {'name': 'Trade ID', 'value': trade.trade_id, 'inline': False},
                {'name': 'Symbol', 'value': signal.symbol, 'inline': True},
                {'name': 'Leverage', 'value': f'{signal.leverage}x', 'inline': True},
                {'name': 'Quantity', 'value': f'{trade.quantity:.6f}', 'inline': True},
                {'name': 'Entry', 'value': f'{trade.entry_price:.4f}', 'inline': True},
                {'name': 'SL / TP', 'value': f'{signal.stop_loss_price:.4f} / {signal.take_profit_price:.4f}', 'inline': True},
                {'name': 'Reason', 'value': signal.reason or 'signal queue', 'inline': False},
            ],
        )

    def _open_trade(self, signal: TradingSignal, limit_price: Optional[float] = None, entry_type: str = 'Market') -> TradeState:
        """Open a trade using Market or Limit order.

        When limit_price is provided (Precision Entry via FVG/OB), places a Limit order
        on OKX with attached SL/TP so the exchange auto-activates them on fill.
        Falls back to Market order if limit_price is None.
        """
        ticker = self._fetch_ticker_with_retry(signal.symbol)
        entry_price = float(ticker['last'] or ticker['close'])
        if entry_price <= 0:
            raise ValueError(f'invalid entry price for {signal.symbol}')

        # ── Vibe ATR TP/SL Capping logic ──
        # Đọc các thông số ép trần từ .env đã cấu hình
        tp_max_pct = float(os.getenv('VIBE_ATR_TP_MAX_PCT', '0.05'))
        sl_max_pct = float(os.getenv('VIBE_ATR_SL_MAX_PCT', '0.03'))

        ref_price = limit_price if limit_price is not None else entry_price

        # Tính khoảng cách TP/SL thực tế từ giá entry_price hiện tại (hoặc limit_price)
        raw_tp_distance = abs(signal.take_profit_price - ref_price)
        raw_sl_distance = abs(signal.stop_loss_price - ref_price)

        # Tính khoảng cách tối đa cho phép theo % cấu hình
        max_tp_distance = ref_price * tp_max_pct
        max_sl_distance = ref_price * sl_max_pct

        # Ép trần: Nếu khoảng cách gốc vượt quá % cho phép thì bóp lại
        final_tp_distance = min(raw_tp_distance, max_tp_distance)
        final_sl_distance = min(raw_sl_distance, max_sl_distance)

        # Log nếu có sự thay đổi (ép trần)
        if raw_tp_distance > final_tp_distance:
            logger.info(
                '[%s] TP distance capped: raw=%.4f (%.2f%%) → capped=%.4f (%.2f%%) [VIBE_ATR_TP_MAX_PCT=%.1f%%]',
                signal.symbol, raw_tp_distance, (raw_tp_distance / ref_price) * 100,
                final_tp_distance, (final_tp_distance / ref_price) * 100,
                tp_max_pct * 100,
            )
        if raw_sl_distance > final_sl_distance:
            logger.info(
                '[%s] SL distance capped: raw=%.4f (%.2f%%) → capped=%.4f (%.2f%%) [VIBE_ATR_SL_MAX_PCT=%.1f%%]',
                signal.symbol, raw_sl_distance, (raw_sl_distance / ref_price) * 100,
                final_sl_distance, (final_sl_distance / ref_price) * 100,
                sl_max_pct * 100,
            )

        # Tính toán lại mức giá TP/SL chính xác theo hướng lệnh (Buy/Sell)
        if signal.side == 'buy':
            signal.take_profit_price = ref_price + final_tp_distance
            signal.stop_loss_price = ref_price - final_sl_distance
        else:
            signal.take_profit_price = ref_price - final_tp_distance
            signal.stop_loss_price = ref_price + final_sl_distance

        # Làm tròn giá trị SL/TP theo exchange price precision nếu có
        try:
            signal.take_profit_price = float(self.exchange.price_to_precision(signal.symbol, signal.take_profit_price))
            signal.stop_loss_price = float(self.exchange.price_to_precision(signal.symbol, signal.stop_loss_price))
        except Exception as exc:
            logger.warning('Failed to apply price precision for %s: %s, falling back to 4 decimal places rounding', signal.symbol, exc)
            signal.take_profit_price = round(signal.take_profit_price, 4)
            signal.stop_loss_price = round(signal.stop_loss_price, 4)

        if self.dry_run:
            return self._simulate_trade(signal, limit_price or entry_price)
        self._check_daily_loss_and_maybe_stop()

        final_leverage = max(1, int(getattr(signal, 'leverage', 1) or 1))
        signal.leverage = final_leverage

        # Dùng available margin (không tính unrealized PnL) để tránh over-size lệnh
        balance = self._fetch_available_margin_with_retry()
        max_compound_balance = float(os.getenv('MAX_COMPOUND_BALANCE', '1000.0'))
        effective_balance = min(balance, max_compound_balance)
        
        if signal.quantity and signal.quantity > 0:
            quantity = signal.quantity
        else:
            margin_amount = max(effective_balance * self.auto_trade_balance_fraction, 0.0)
            notional = margin_amount * max(self.forced_leverage, 1)
            quantity = notional / entry_price

        market = self.exchange.market(signal.symbol)
        quantity = self._apply_amount_precision(signal.symbol, quantity)
        min_qty = market.get('limits', {}).get('amount', {}).get('min', 0.0)
        if min_qty > 0 and quantity < min_qty:
            # Never silently lift an order above its calculated risk budget.
            # A small account / tight stop should skip, not become a larger
            # position merely because of exchange lot-size constraints.
            raise ValueError(
                f'calculated quantity {quantity:.8f} for {signal.symbol} is below exchange minimum {min_qty}'
            )
        self._validate_quantity(market, signal.symbol, quantity)
        # Budget against account equity, not free margin. Free margin naturally
        # shrinks after each layer and would otherwise make a 6% portfolio cap
        # reject the second normal 3%-risk layer before it is actually reached.
        try:
            risk_budget_balance = self._fetch_usdt_balance_with_retry()
        except Exception as exc:
            logger.warning('Could not fetch equity for aggregate stop-risk check; using free margin: %s', exc)
            risk_budget_balance = balance
        self._ensure_stop_risk_budget(risk_budget_balance, entry_price, signal.stop_loss_price, quantity)

        order_side = signal.side
        opposite_side = 'sell' if order_side == 'buy' else 'buy'
        self._apply_position_settings(signal.symbol, final_leverage)

        use_limit = limit_price is not None and self.exchange_platform == 'okx'

        if self.exchange_platform == 'okx':
            # ── OKX: Attach SL/TP directly to Entry (Limit or Market) ────────
            # Sàn OKX sẽ tự hiểu đây là một cặp bài trùng OCO (One-Cancels-the-Other).
            # Chỉ cần 1 trong 2 lệnh cắn (SL hoặc TP), cái còn lại tự động biến mất.
            params: Dict[str, Any] = {
                **self._order_mode_params(reduce_only=False),
                'slTriggerPx': str(signal.stop_loss_price),
                'slOrdPx': '-1',
                'tpTriggerPx': str(signal.take_profit_price),
                'tpOrdPx': '-1'
            }
            
            if use_limit:
                logger.info(
                    'Placing LIMIT order with attached SL/TP: %s %s qty=%.6f price=%.4f SL=%.4f TP=%.4f',
                    order_side.upper(), signal.symbol, quantity, limit_price,
                    signal.stop_loss_price, signal.take_profit_price,
                )
                entry_order = self._create_order_with_retry(
                    signal.symbol, 'limit', order_side, quantity, limit_price, params
                )
                filled_price = limit_price
            else:
                logger.info(
                    'Placing MARKET order with attached SL/TP: %s %s qty=%.6f SL=%.4f TP=%.4f',
                    order_side.upper(), signal.symbol, quantity,
                    signal.stop_loss_price, signal.take_profit_price,
                )
                params['leverage'] = final_leverage
                entry_order = self._create_order_with_retry(
                    signal.symbol, 'market', order_side, quantity, None, params
                )
                filled_price = self._extract_fill_price(entry_order, entry_price)

            stop_order_id = None
            take_profit_order_id = None
        elif self.exchange_platform == 'bybit':
            params = {
                **self._order_mode_params(reduce_only=False),
                'category': os.getenv('BYBIT_CATEGORY', 'linear'),
                'stopLoss': str(signal.stop_loss_price),
                'takeProfit': str(signal.take_profit_price),
                'tpslMode': os.getenv('BYBIT_TPSL_MODE', 'Full'),
            }
            logger.info(
                'Placing BYBIT MARKET order with attached SL/TP: %s %s qty=%.6f SL=%.4f TP=%.4f',
                order_side.upper(), signal.symbol, quantity,
                signal.stop_loss_price, signal.take_profit_price,
            )
            entry_order = self._create_order_with_retry(
                signal.symbol, 'market', order_side, quantity, None, params
            )
            filled_price = self._extract_fill_price(entry_order, entry_price)
            stop_order_id = None
            take_profit_order_id = None
        else:
            # ── Market Order (Non-OKX path) ─────────────────────────────────
            params = {
                'leverage': final_leverage,
                **self._order_mode_params(reduce_only=False),
            }
            entry_order = self._create_order_with_retry(signal.symbol, 'market', order_side, quantity, None, params)
            filled_price = self._extract_fill_price(entry_order, entry_price)
            entry_order_id = str(entry_order.get('id', ''))

            try:
                stop_order = self._create_protective_order(
                    symbol=signal.symbol, side=opposite_side, quantity=quantity,
                    stop_price=signal.stop_loss_price, order_type='STOP_MARKET',
                )
                take_profit_order = self._create_protective_order(
                    symbol=signal.symbol, side=opposite_side, quantity=quantity,
                    stop_price=signal.take_profit_price, order_type='TAKE_PROFIT_MARKET',
                )
            except Exception as protective_exc:
                # ── CRITICAL: SL/TP đặt thất bại → đóng entry ngay, hủy trade ──
                logger.error(
                    '🚨 SAFETY CLOSE: Không thể đặt SL/TP cho %s (entry_id=%s). '
                    'Đang đóng vị thế ngay lập tức để tránh naked position. Lỗi: %s',
                    signal.symbol, entry_order_id, protective_exc
                )
                self._send_discord_message(
                    title='🚨 SAFETY CLOSE - Không đặt được SL/TP',
                    message=(
                        f'Symbol: {signal.symbol}\n'
                        f'Entry ID: {entry_order_id}\n'
                        f'Lý do đóng: {protective_exc}\n'
                        f'Hành động: Đã gửi lệnh đóng Market để bảo vệ tài khoản.'
                    ),
                    color=0xFF0000,
                )
                try:
                    close_params = self._order_mode_params(reduce_only=True)
                    close_params.pop('reduceOnly', None)
                    self._create_order_with_retry(
                        signal.symbol, 'market', opposite_side, quantity, None, close_params
                    )
                    logger.warning('Safety close order sent for %s', signal.symbol)
                except Exception as close_exc:
                    logger.error('🚨 CRITICAL: Không thể đóng vị thế %s: %s — Vui lòng đóng thủ công trên sàn!', signal.symbol, close_exc)
                raise RuntimeError(f'Trade aborted: SL/TP failed → entry closed. Root cause: {protective_exc}') from protective_exc

            stop_order_id = str(stop_order.get('id')) if stop_order else None
            take_profit_order_id = str(take_profit_order.get('id')) if take_profit_order else None
            self._record_exchange_event(signal.symbol, 'stop_order', stop_order)
            self._record_exchange_event(signal.symbol, 'take_profit_order', take_profit_order)

        trade = TradeState(
            trade_id=str(uuid.uuid4()),
            signal=signal,
            entry_price=filled_price,
            quantity=quantity,
            stop_order_id=stop_order_id if use_limit else stop_order_id,
            take_profit_order_id=take_profit_order_id if use_limit else take_profit_order_id,
            created_at=int(time.time()),
        )

        self._record_exchange_event(signal.symbol, 'entry_order', entry_order)
        self._record_daily_trade_execution()
        logger.info('Trade opened: %s %s entry=%.4f qty=%.6f balance=%.2f', entry_type, trade.trade_id, filled_price, quantity, balance)
        return trade

    def _simulate_trade(self, signal: TradingSignal, entry_price: float) -> TradeState:
        balance = 5000.0
        quantity = signal.quantity if signal.quantity and signal.quantity > 0 else self._calculate_quantity(balance, entry_price, signal.stop_loss_price, signal.leverage)
        trade = TradeState(
            trade_id=f'dry-run-{uuid.uuid4()}',
            signal=signal,
            entry_price=entry_price,
            quantity=quantity,
            stop_order_id=None,
            take_profit_order_id=None,
            created_at=int(time.time()),
        )
        self.signal_store.push_history(signal, 'simulated', f'dry_run trade_id={trade.trade_id}')
        self._send_discord_message(
            title=f'DRY RUN - {signal.side.upper()}',
            message=(
                f'Symbol: {signal.symbol}\n'
                f'Quantity: {trade.quantity:.6f}\n'
                f'Entry: {trade.entry_price:.4f}\n'
                f'SL: {signal.stop_loss_price:.4f}\n'
                f'TP: {signal.take_profit_price:.4f}\n'
                f'Mode: Simulation (no Binance credentials)'
            ),
            color=0x3498DB,
        )
        logger.info('Dry-run trade simulated: %s', trade.trade_id)
        return trade

    def _monitor_active_trades(self) -> None:
        while True:
            try:
                self._check_daily_loss_and_maybe_stop()
                trade_ids = self.signal_store.load_active_trade_ids()
                
                # Group active trades by symbol to minimize API requests and avoid rate limits
                symbol_trades: dict[str, list[dict[str, Any]]] = {}
                for trade_id in trade_ids:
                    trade_data = self.signal_store.load_trade(trade_id)
                    if not trade_data:
                        self.signal_store.delete_trade(trade_id)
                        continue
                    symbol = trade_data.get('symbol')
                    if symbol:
                        symbol_trades.setdefault(symbol, []).append({'id': trade_id, 'data': trade_data})
                
                for symbol, trades in symbol_trades.items():
                    # Fetch active position and open conditional orders once per symbol
                    pos_info = self._get_open_position_info(symbol)
                    open_conditional_orders = self._fetch_open_conditional_orders(symbol)
                    
                    for item in trades:
                        self._inspect_trade(item['id'], item['data'], open_conditional_orders, pos_info)
            except (RedisError, ccxt.NetworkError, ccxt.RateLimitExceeded) as exc:
                logger.warning('Monitor loop transient error: %s', exc)
            except Exception as exc:  # pragma: no cover - defensive guard for 24/7 process
                logger.exception('Monitor loop error: %s', exc)
            time.sleep(self.poll_interval)

    def _fetch_open_conditional_orders(self, symbol: str) -> list[Dict[str, Any]]:
        orders: list[Dict[str, Any]] = []
        exchange_id = self.exchange_platform.lower()

        if self.dry_run:
            return orders

        try:
            if exchange_id == 'bybit':
                # Fetch stop orders (conditional orders, which includes Partial TP/SL)
                params = {
                    'category': os.getenv('BYBIT_CATEGORY', 'linear'),
                    'stopOrderFilter': 'StopOrder',
                }
                raw_orders = self.exchange.fetch_open_orders(symbol, params=params)
                for o in raw_orders:
                    orders.append({
                        'id': o.get('id'),
                        'triggerPrice': safe_float(o.get('triggerPrice') or o.get('price')),
                        'amount': safe_float(o.get('amount')),
                        'side': o.get('side').lower() if o.get('side') else '',
                        'info': o
                    })
            elif exchange_id == 'okx':
                # Fetch pending algo orders
                inst_id = symbol.replace('/', '-').replace(':USDT', '-SWAP')
                resp = self.exchange.privateGetTradeOrdersAlgoPending({
                    'instId': inst_id,
                    'ordType': 'conditional'
                })
                raw_orders = resp.get('data', [])
                for o in raw_orders:
                    orders.append({
                        'id': o.get('algoId'),
                        'triggerPrice': safe_float(o.get('slTriggerPx') or o.get('tpTriggerPx') or 0),
                        'amount': safe_float(o.get('sz') or 0),  # This is in contracts!
                        'side': o.get('side').lower() if o.get('side') else '',
                        'info': o
                    })
            else:
                # Fallback for other exchanges (e.g. Binance)
                raw_orders = self.exchange.fetch_open_orders(symbol)
                for o in raw_orders:
                    orders.append({
                        'id': o.get('id'),
                        'triggerPrice': safe_float(o.get('triggerPrice') or o.get('price')),
                        'amount': safe_float(o.get('amount')),
                        'side': o.get('side').lower() if o.get('side') else '',
                        'info': o
                    })
        except Exception as exc:
            logger.warning('Failed to fetch open conditional orders for %s on %s: %s', symbol, exchange_id, exc)
            
        return orders

    def _is_trade_active_on_exchange(
        self,
        trade_data: Dict[str, str],
        open_conditional_orders: list[Dict[str, Any]],
        pos_info: Optional[Dict[str, Any]]
    ) -> bool:
        if self.dry_run:
            return True

        symbol = trade_data.get('symbol', '')

        # 1. If no active position exists on exchange, check if there are pending entry limit orders.
        # If there are no active positions and no open entry orders, the trade must be closed.
        if pos_info is None:
            try:
                open_orders = self.exchange.fetch_open_orders(symbol)
                # Filter out stop orders (conditional orders)
                limit_entry_orders = [o for o in open_orders if o.get('info', {}).get('stopOrderType') is None and o.get('type') != 'stop']
                if limit_entry_orders:
                    return True
            except Exception as exc:
                logger.warning('Error checking pending entry orders for %s: %s', symbol, exc)
            
            logger.info('[%s] No active position and no open entry orders. Trade %s is closed.', symbol, trade_data.get('trade_id'))
            return False

        # 2. Check if the trade's TP/SL trigger orders are still active.
        # If we have stop_order_id or take_profit_order_id, check by ID first.
        stop_order_id = trade_data.get('stop_order_id')
        take_profit_order_id = trade_data.get('take_profit_order_id')
        
        active_ids = {o.get('id') for o in open_conditional_orders if o.get('id')}
        
        if stop_order_id and stop_order_id in active_ids:
            return True
        if take_profit_order_id and take_profit_order_id in active_ids:
            return True

        # 3. If order IDs are not found or not matched (e.g. Bybit attached TP/SL where IDs are not returned in order placement),
        # match by triggerPrice and quantity (allowing minor rounding tolerances).
        stop_loss_price = safe_float(trade_data.get('stop_loss_price'))
        take_profit_price = safe_float(trade_data.get('take_profit_price'))
        quantity = safe_float(trade_data.get('quantity'))

        # Determine contract size if OKX to convert coin quantity to contracts
        exchange_id = self.exchange_platform.lower()
        match_qty = quantity
        if exchange_id == 'okx':
            try:
                market = self.exchange.market(symbol)
                contract_size = float(market.get('contractSize') or 0.01)
                match_qty = max(1.0, round(quantity / contract_size))  # OKX sz is integer contracts
            except Exception:
                pass

        # We look for active trigger orders matching the target prices
        # Price tolerance: 0.1% to account for minor rounding.
        for o in open_conditional_orders:
            trig_price = o.get('triggerPrice', 0.0)
            amount = o.get('amount', 0.0)
            
            is_price_match = False
            if stop_loss_price > 0 and abs(trig_price - stop_loss_price) / stop_loss_price < 0.001:
                is_price_match = True
            elif take_profit_price > 0 and abs(trig_price - take_profit_price) / take_profit_price < 0.001:
                is_price_match = True
                
            if is_price_match:
                # Qty match with a 5% tolerance to handle contract rounding or partial fills
                if abs(amount - match_qty) / max(match_qty, 0.0001) < 0.05:
                    return True

        # Neither SL nor TP conditional order is active for this trade
        logger.info(
            '[%s] Trade %s has no active TP/SL orders on exchange (SL=%.4f, TP=%.4f, Qty=%.4f). Considering closed.',
            symbol, trade_data.get('trade_id'), stop_loss_price, take_profit_price, quantity
        )
        return False


    def _auto_trade_loop(self) -> None:
        while True:
            try:
                # ── Chọn engine tín hiệu ─────────────────────────────
                if self.auto_trade_mode == 'vibe':
                    decision = self._build_vibe_decision()
                else:
                    # AI score mode (giữ nguyên để dùng sau)
                    snapshot = self._fetch_dashboard_snapshot()
                    if snapshot is None:
                        logger.warning('Backend busy, retrying...')
                        time.sleep(self.auto_trade_interval)
                        continue
                    decision = self._build_auto_trade_decision(snapshot)

                logger.info(
                    'Auto-trade scan [%s]: adx=%.2f rsi=%.2f decision=%s reason=%s',
                    self.auto_trade_mode.upper(),
                    decision.adx,
                    decision.rsi,
                    'TRADE' if decision.should_trade else 'WATCH',
                    decision.reason[:80],
                )
                dh = None
                try:
                    decision_payload = asdict(decision)
                    decision_payload['decision'] = 'TRADE' if decision.should_trade else 'WATCH'
                    decision_payload['mode'] = self.auto_trade_mode
                    decision_payload['exchange_platform'] = self.exchange_platform
                    decision_payload['market_data_platform'] = self.market_data_platform
                    decision_payload['is_demo'] = self.is_demo
                    decision_payload['market_data_is_demo'] = self.market_data_is_demo
                    decision_payload['onchain_score'] = self._fetch_onchain_score()
                    dh = self.signal_store.push_agent_decision(decision_payload)
                except RedisError as exc:
                    logger.warning('Unable to store agent decision journal: %s', exc)

                # ── Ghi dự đoán lên Mantle blockchain (non-blocking) ─────────
                if dh and os.getenv('AGENT_PROOF_ENABLED', 'false').lower() in {'1', 'true', 'yes', 'on'}:
                    def _commit_to_chain(
                        _dh: str,
                        _decision: AutoTradeDecision,
                        _mode: str,
                    ) -> None:
                        try:
                            try:
                                from executor.mantle_proof import commit_signal_live, decision_code as _dc, stable_hash as _sh
                            except ImportError:
                                from mantle_proof import commit_signal_live, decision_code as _dc, stable_hash as _sh
                            _record = {
                                'decision': 'TRADE' if _decision.should_trade else 'WATCH',
                                'side': _decision.side or '',
                            }
                            _dec_code = _dc(_record)
                            _rr = max(0, min(65535, int((_decision.rr_ratio or 0.0) * 100)))
                            _mps_raw = _decision.market_power_score or 0.0
                            _mps = max(-100, min(100, int(_mps_raw * 10)))
                            _ts = int(_decision.signal_candle_timestamp or time.time())
                            _agent_id = os.getenv('AGENT_ID', 'vibe-agent')
                            tx = commit_signal_live(
                                signal_hash=_dh,
                                agent_id=_agent_id,
                                symbol=_decision.symbol,
                                decision=_dec_code,
                                rr_ratio=_rr,
                                entry_type=_decision.entry_type or 'Market',
                                signal_timestamp=_ts,
                                market_power_score=_mps,
                            )
                            if tx:
                                logger.info('[OnChain] Signal committed: tx=%s | decision=%s mps=%+d', tx, _dec_code, _mps)
                            else:
                                logger.warning('[OnChain] commit_signal_live returned None (check MANTLE_RPC or gas)')
                        except Exception as _exc:
                            logger.warning('[OnChain] Blockchain commit failed (non-fatal): %s', _exc)
                    threading.Thread(
                        target=_commit_to_chain,
                        args=(dh, decision, self.auto_trade_mode),
                        daemon=True,
                        name='mantle-proof',
                    ).start()

                if decision.should_trade and decision.side:
                    self._check_daily_loss_and_maybe_stop()
                    if self._stopped_due_to_daily_loss:
                        logger.warning('Auto-trade disabled due to daily loss limit')
                    else:
                        self._execute_auto_trade(decision, decision_hash=dh)

            except ccxt.RateLimitExceeded as exc:
                # ── Bybit 10006: Too many visits ─────────────────────
                # Ngủ im 60s rồi mới quét lại, không được retry ngay.
                backoff = int(os.getenv('RATE_LIMIT_BACKOFF_SECONDS', '60'))
                logger.warning(
                    '⏳ Rate limit hit (Bybit 10006): ngủ %ds trước khi tiếp tục. Chi tiết: %s',
                    backoff, exc,
                )
                time.sleep(backoff)
                continue  # bỏ qua time.sleep(auto_trade_interval) bên dưới

            except ccxt.NetworkError as exc:
                backoff = int(os.getenv('NETWORK_ERROR_BACKOFF_SECONDS', '15'))
                logger.warning('🌐 Network error, retry sau %ds: %s', backoff, exc)
                time.sleep(backoff)
                continue

            except Exception as exc:  # pragma: no cover
                logger.exception('Auto-trade loop error: %s', exc)
                time.sleep(5)

            time.sleep(self.auto_trade_interval)

    def _fetch_dashboard_snapshot(self) -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(self.backend_dashboard_url, timeout=20)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError('dashboard response must be a JSON object')
            return payload
        except requests.exceptions.ReadTimeout:
            logger.warning('Backend busy, retrying...')
            return None
        except requests.RequestException as exc:
            logger.warning('Backend request failed, retrying... %s', exc)
            return None
        except Exception as exc:
            logger.warning('Unexpected backend error, retrying... %s', exc)
            return None

    def _current_auto_trade_threshold(self) -> float:
        elapsed = time.time() - self.auto_trade_started_at
        if elapsed <= self.auto_trade_test_window_seconds:
            logger.debug('Đang trong test window (%.0f/%.0f giây), dùng test_threshold=%.0f', elapsed, self.auto_trade_test_window_seconds, self.auto_trade_test_threshold)
            return self.auto_trade_test_threshold
        logger.debug('Hết test window, dùng score_threshold=%.0f', self.auto_trade_score_threshold)
        return self.auto_trade_score_threshold

    def _build_auto_trade_decision(self, snapshot: Dict[str, Any]) -> AutoTradeDecision:
        market_vibe = snapshot.get('market_vibe') or {}

        market_power_score = float(market_vibe.get('market_power_score') or 0.0)
        market_power_status = str(market_vibe.get('market_power_status') or '')
        market_power_action = str(market_vibe.get('market_power_action') or 'WAIT')
        whale_layer = market_vibe.get('whale_layer') or {}
        whale_score = float(whale_layer.get('whale_score') or 0.0)
        news_score = float(market_vibe.get('news_score') or 0.0)
        news_reason = str(market_vibe.get('news_reason') or 'Not yet analyzed')
        trend_filters = self._fetch_hybrid_trend_filters(self.auto_trade_symbol)
        adx_value = trend_filters.get('adx', 0.0) if trend_filters else 0.0
        rsi_value = trend_filters.get('rsi', 50.0) if trend_filters else 50.0

        open_pos = self._get_open_position_info(self.auto_trade_symbol)
        active_symbol_layers = self._active_trade_layers(self.auto_trade_symbol)

        side: Optional[str] = None
        reason = 'waiting for extreme score and whale confirmation'
        threshold = self._current_auto_trade_threshold()
        # score_floor: dùng threshold hiện tại (không hard-code 50)
        score_floor = min(self.auto_trade_hybrid_score_floor, threshold)
        watch_reasons: list[str] = []

        # ── Kiểm tra vị thế đang mở ──────────────────────────────
        # Pyramiding: 0 blocks new entries; >0 allows same-direction layers up to the configured cap.
        if open_pos is not None or active_symbol_layers > 0:
            if self.max_pyramid_layers <= 0:
                watch_reasons.append('active position detected (pyramiding off)')
            # Chiều chỉ được xét sau khi xác định được side bên dưới

        if self.auto_trade_hybrid_enabled and abs(market_power_score) < score_floor:
            watch_reasons.append(f'Score({market_power_score:.1f}<{score_floor:.1f})')

        if market_power_score <= -threshold and whale_score < 0:
            side = 'buy'
            reason = 'panic score with bearish whale confirmation'
        elif market_power_score >= threshold and whale_score > 0:
            side = 'sell'
            reason = 'euphoria score with bullish whale confirmation'
        else:
            watch_reasons.append(f'Score/Whale gate(score={market_power_score:.1f}, whale={whale_score:.1f}, th={threshold:.1f})')

        # ── Kiểm tra pyramiding chiều + giới hạn ───────────────────
        if (open_pos is not None or active_symbol_layers > 0) and self.max_pyramid_layers > 0 and side is not None:
            same_side_layers = self._active_trade_layers(self.auto_trade_symbol, side)
            if open_pos is not None and same_side_layers == 0:
                same_side_layers = 1
            pos_is_long = open_pos['side'] == 'long' if open_pos is not None else side == 'buy'
            sig_is_long = side == 'buy'
            if open_pos is not None and pos_is_long != sig_is_long:
                watch_reasons.append(
                    f'Pyramid blocked: ngược chiều (pos={open_pos["side"]} vs signal={side})'
                )
            elif same_side_layers >= self.max_pyramid_layers:
                watch_reasons.append(
                    f'Pyramid limit: {same_side_layers}>={self.max_pyramid_layers} layers'
                )
            else:
                logger.info(
                    'Pyramiding: %d/%d same-side layers, adding %s',
                    same_side_layers, self.max_pyramid_layers, side,
                )

        if self.auto_trade_hybrid_enabled:
            if trend_filters is None:
                watch_reasons.append('Trend filters unavailable')
            else:
                if adx_value < self.auto_trade_hybrid_adx_min:
                    watch_reasons.append(f'ADX({adx_value:.1f}<{self.auto_trade_hybrid_adx_min:.1f})')
                if side == 'buy' and rsi_value < self.auto_trade_hybrid_rsi_buy_min:
                    watch_reasons.append(f'RSI_Low({rsi_value:.1f}<{self.auto_trade_hybrid_rsi_buy_min:.1f})')
                if side == 'sell' and rsi_value > self.auto_trade_hybrid_rsi_sell_max:
                    watch_reasons.append(f'RSI_High({rsi_value:.1f}>{self.auto_trade_hybrid_rsi_sell_max:.1f})')

        should_trade = side is not None and not watch_reasons
        decision_reason = reason if should_trade else ' | '.join(watch_reasons) if watch_reasons else reason

        return AutoTradeDecision(
            should_trade=should_trade,
            side=side if should_trade else None,
            reason=decision_reason,
            market_power_score=market_power_score,
            whale_score=whale_score,
            adx=adx_value,
            rsi=rsi_value,
            symbol=self.auto_trade_symbol,
            market_power_status=market_power_status,
            market_power_action=market_power_action,
            news_score=news_score,
            news_reason=news_reason,
        )

    def _fetch_hybrid_trend_filters(self, symbol: str) -> Optional[Dict[str, float]]:
        if not self.auto_trade_hybrid_enabled:
            return None

        for attempt in range(2):
            try:
                candles = self.market_data_exchange.fetch_ohlcv(symbol, timeframe=self.auto_trade_hybrid_tf, limit=max(self.auto_trade_hybrid_lookback, 60))
                if not candles or len(candles) < 40:
                    return None
                high_values = [float(row[2]) for row in candles]
                low_values = [float(row[3]) for row in candles]
                close_values = [float(row[4]) for row in candles]
                adx_value = self._calculate_adx(high_values, low_values, close_values, period=14)
                rsi_value = self._calculate_rsi(close_values, period=14)
                return {
                    'adx': adx_value,
                    'rsi': rsi_value,
                }
            except (ccxt.NetworkError, ccxt.RateLimitExceeded) as exc:
                logger.warning('Hybrid filter fetch failed for %s (attempt %s): %s', symbol, attempt + 1, exc)
                time.sleep(1)
            except Exception as exc:
                logger.warning('Hybrid filter calculation failed for %s: %s', symbol, exc)
                return None
        return None

    def _calculate_rsi(self, values: Sequence[float], period: int = 14) -> float:
        if len(values) <= period:
            return 50.0

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

    def _calculate_adx(self, high_values: Sequence[float], low_values: Sequence[float], close_values: Sequence[float], period: int = 14) -> float:
        if len(close_values) <= period * 2:
            return 0.0

        tr_values: list[float] = [high_values[0] - low_values[0]]
        plus_dm: list[float] = [0.0]
        minus_dm: list[float] = [0.0]

        for index in range(1, len(close_values)):
            current_high = high_values[index]
            current_low = low_values[index]
            previous_close = close_values[index - 1]
            tr_values.append(max(current_high - current_low, abs(current_high - previous_close), abs(current_low - previous_close)))

            up_move = current_high - high_values[index - 1]
            down_move = low_values[index - 1] - current_low
            plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
            minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)

        atr_smooth = sum(tr_values[1 : period + 1])
        plus_dm_smooth = sum(plus_dm[1 : period + 1])
        minus_dm_smooth = sum(minus_dm[1 : period + 1])
        dx_values: list[float] = []

        for index in range(period + 1, len(close_values)):
            atr_smooth = atr_smooth - (atr_smooth / period) + tr_values[index]
            plus_dm_smooth = plus_dm_smooth - (plus_dm_smooth / period) + plus_dm[index]
            minus_dm_smooth = minus_dm_smooth - (minus_dm_smooth / period) + minus_dm[index]

            current_atr = atr_smooth / period
            if current_atr == 0:
                continue

            plus_di = 100 * (plus_dm_smooth / period) / current_atr
            minus_di = 100 * (minus_dm_smooth / period) / current_atr
            denominator = plus_di + minus_di
            if denominator == 0:
                continue
            dx_values.append(100 * abs(plus_di - minus_di) / denominator)

        if len(dx_values) < period:
            return 0.0

        return sum(dx_values[-period:]) / period

    def _calculate_ema(self, values: Sequence[float], period: int) -> float:
        """Exponential Moving Average."""
        if len(values) < period:
            return values[-1] if values else 0.0
        multiplier = 2.0 / (period + 1)
        result = sum(values[:period]) / period
        for v in values[period:]:
            result = (v - result) * multiplier + result
        return result

    def _calculate_macd_histogram(self, values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float]:
        """Returns (macd_line, signal_line, histogram)."""
        if len(values) < slow + signal:
            return 0.0, 0.0, 0.0
        macd_vals: list[float] = []
        for end in range(slow, len(values) + 1):
            chunk = list(values[:end])
            macd_vals.append(self._calculate_ema(chunk, fast) - self._calculate_ema(chunk, slow))
        if len(macd_vals) < signal:
            return 0.0, 0.0, 0.0
        signal_line = self._calculate_ema(macd_vals, signal)
        return macd_vals[-1], signal_line, macd_vals[-1] - signal_line

    def _calculate_atr(self, highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> float:
        """ATR raw value."""
        if len(closes) <= period:
            return 0.0
        tr_vals: list[float] = [highs[0] - lows[0]]
        for i in range(1, len(closes)):
            tr_vals.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
        return sum(tr_vals[-period:]) / period

    def _calculate_atr_pct(self, highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> float:
        """ATR as percentage of last close."""
        if len(closes) <= period or closes[-1] <= 0:
            return 0.0
        tr_vals: list[float] = [highs[0] - lows[0]]
        for i in range(1, len(closes)):
            tr_vals.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
        atr_val = sum(tr_vals[-period:]) / period
        return atr_val / closes[-1]

    def _vibe_snapshot(
        self,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        trend_adx_threshold: float,
        chop_adx_threshold: float,
        high_atr_pct: float,
    ) -> RegimeSnapshot:
        """Calculate market regime snapshot. Matches backtester.py exactly."""
        atr_val = self._calculate_atr(highs, lows, closes)
        atr_pct = atr_val / closes[-1] if closes[-1] > 0 else 0.0
        adx_val = self._calculate_adx(highs, lows, closes)
        fast_ema = self._calculate_ema(closes, 20)
        slow_ema = self._calculate_ema(closes, 50)
        rsi_val = self._calculate_rsi(closes)
        macd_line, signal_line, histogram = self._calculate_macd_histogram(closes)

        if atr_pct >= high_atr_pct:
            return RegimeSnapshot('HIGH_VOLATILITY', 'ATR is too elevated', adx_val, atr_pct)

        if adx_val >= trend_adx_threshold and abs(fast_ema - slow_ema) / closes[-1] > 0.002:
            trend_side = None
            if fast_ema > slow_ema and macd_line >= signal_line and rsi_val >= 50:
                trend_side = 'buy'
            elif fast_ema < slow_ema and macd_line <= signal_line and rsi_val <= 50:
                trend_side = 'sell'
            regime = 'TRENDING' if trend_side else 'SIDEWAYS'
            reason = 'Trend filters aligned' if trend_side else 'Trend strength present but momentum is mixed'
            return RegimeSnapshot(regime, reason, adx_val, atr_pct, trend_side=trend_side)

        if adx_val <= chop_adx_threshold:
            return RegimeSnapshot('SIDEWAYS', 'Low ADX range regime', adx_val, atr_pct)

        if histogram > 0 and rsi_val > 55:
            return RegimeSnapshot('TRENDING', 'Momentum is bullish', adx_val, atr_pct, trend_side='buy')
        if histogram < 0 and rsi_val < 45:
            return RegimeSnapshot('TRENDING', 'Momentum is bearish', adx_val, atr_pct, trend_side='sell')

        return RegimeSnapshot('SIDEWAYS', 'No decisive trend edge', adx_val, atr_pct)

    def _vibe_too_choppy(self, daily_snapshot: RegimeSnapshot, intraday_snapshot: RegimeSnapshot, high_atr_pct: float, chop_adx_threshold: float) -> bool:
        """Check if market is too choppy or volatile. Matches backtester.py exactly."""
        return (
            daily_snapshot.regime == 'HIGH_VOLATILITY'
            or intraday_snapshot.regime == 'HIGH_VOLATILITY'
            or (intraday_snapshot.adx <= chop_adx_threshold and intraday_snapshot.atr_pct >= high_atr_pct * 0.35)
        )

    def _vibe_select_direction(
        self,
        closes_1d: list[float],
        closes_4h: list[float],
        daily_snapshot: RegimeSnapshot,
        intraday_snapshot: RegimeSnapshot,
        timestamp_ms: int | None = None,
    ) -> str | None:
        """Determine trend and momentum direction. Matches backtester.py exactly."""
        # Opt-in research profile.  It requires a persistent weekly UP-UP
        # state and a fresh 4H channel breakout, rather than re-entering every
        # candle while the standard confluence remains true.
        if os.getenv('VIBE_TECH_PROFILE', 'confluence').lower() == 'regime_breakout':
            lookback = max(10, int(os.getenv('VIBE_BREAKOUT_LOOKBACK', '20')))
            if len(closes_1d) < 16 or len(closes_4h) < lookback + 1:
                return None
            up_up = closes_1d[-1] >= closes_1d[-8] and closes_1d[-8] >= closes_1d[-15]
            down_down = closes_1d[-1] <= closes_1d[-8] and closes_1d[-8] <= closes_1d[-15]
            daily_fast = self._calculate_ema(closes_1d, 20)
            daily_slow = self._calculate_ema(closes_1d, 50)
            daily_macd, daily_signal, _ = self._calculate_macd_histogram(closes_1d)
            prior_high = max(closes_4h[-lookback - 1:-1])
            prior_low = min(closes_4h[-lookback - 1:-1])
            if up_up and daily_fast > daily_slow and daily_macd >= daily_signal and closes_4h[-1] > prior_high:
                return 'buy'
            if (os.getenv('VIBE_REGIME_BREAKOUT_ALLOW_SHORT', 'false').lower() in {'1', 'true', 'yes'}
                    and down_down and daily_fast < daily_slow and daily_macd <= daily_signal and closes_4h[-1] < prior_low):
                return 'sell'
            return None

        if os.getenv('VIBE_TECH_PROFILE', 'confluence').lower() == 'regime_momentum':
            # Daily decision cadence prevents repeated 4H pyramids while the
            # same weekly momentum state is unchanged.
            if len(closes_1d) < 16 or timestamp_ms is None or timestamp_ms % 86_400_000 != 72_000_000:
                return None
            up_up = closes_1d[-1] >= closes_1d[-8] and closes_1d[-8] >= closes_1d[-15]
            fast = self._calculate_ema(closes_1d, 20)
            slow = self._calculate_ema(closes_1d, 50)
            macd_line, macd_signal, _ = self._calculate_macd_histogram(closes_1d)
            if up_up and fast > slow and macd_line >= macd_signal:
                return 'buy'
            return None

        if os.getenv('VIBE_TECH_PROFILE', 'confluence').lower() == 'trend_pullback':
            if len(closes_1d) < 60 or len(closes_4h) < 51:
                return None
            daily_fast = self._calculate_ema(closes_1d, 20)
            daily_slow = self._calculate_ema(closes_1d, 50)
            daily_macd, daily_signal, _ = self._calculate_macd_histogram(closes_1d)
            intraday_fast_now = self._calculate_ema(closes_4h, 20)
            intraday_fast_prev = self._calculate_ema(closes_4h[:-1], 20)
            pullback_recovery = closes_4h[-2] <= intraday_fast_prev and closes_4h[-1] > intraday_fast_now
            if daily_fast > daily_slow and daily_macd >= daily_signal and pullback_recovery:
                return 'buy'
            return None

        daily_rsi = self._calculate_rsi(closes_1d)
        intraday_rsi = self._calculate_rsi(closes_4h)
        daily_macd_line, daily_signal, _ = self._calculate_macd_histogram(closes_1d)
        intraday_macd_line, intraday_signal, _ = self._calculate_macd_histogram(closes_4h)

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

    def _build_vibe_decision(self) -> AutoTradeDecision:
        """Vibe Strategy: trend-following EMA+MACD+ADX confluence trên 1D + 4H.

        Đồng bộ 100% logic với VibeTradingSignalGenerator trong backtester.py.
        """
        symbol = self.auto_trade_symbol
        high_atr_pct = float(os.getenv('VIBE_HIGH_ATR_PCT', '0.05'))
        trend_adx_threshold = float(os.getenv('VIBE_TREND_ADX', '25'))
        chop_adx_threshold = float(os.getenv('VIBE_CHOP_ADX', '18'))

        def _no_trade(reason: str, adx: float = 0.0, rsi: float = 50.0) -> AutoTradeDecision:
            return AutoTradeDecision(
                should_trade=False, reason=reason, symbol=symbol,
                adx=adx, rsi=rsi, market_power_status='VIBE', market_power_action='WAIT',
                market_power_score=0.0, whale_score=0.0,
            )

        # ── Fetch candles (với retry + backoff chống rate limit) ────
        def _fetch_ohlcv_with_backoff(tf: str, limit: int) -> list:
            max_attempts = int(os.getenv('CANDLE_FETCH_MAX_RETRIES', '3'))
            for attempt in range(max_attempts):
                try:
                    return self.market_data_exchange.fetch_ohlcv(symbol, tf, limit=limit)
                except ccxt.RateLimitExceeded as exc:
                    backoff = int(os.getenv('RATE_LIMIT_BACKOFF_SECONDS', '60')) * (attempt + 1)
                    logger.warning(
                        '⏳ Rate limit khi fetch %s candles (attempt %d/%d): ngủ %ds... Chi tiết: %s',
                        tf, attempt + 1, max_attempts, backoff, exc,
                    )
                    if attempt + 1 < max_attempts:
                        time.sleep(backoff)
                    else:
                        raise
                except ccxt.NetworkError as exc:
                    backoff = int(os.getenv('NETWORK_ERROR_BACKOFF_SECONDS', '15'))
                    logger.warning('🌐 Network error fetch %s (attempt %d/%d): retry sau %ds', tf, attempt + 1, max_attempts, backoff)
                    if attempt + 1 < max_attempts:
                        time.sleep(backoff)
                    else:
                        raise
            return []

        try:
            # Lấy nhiều hơn 1 nến để sau khi bỏ nến đang chạy dở [:-1] vẫn đủ dữ liệu
            raw_4h = _fetch_ohlcv_with_backoff('4h', 201)
            raw_1d = _fetch_ohlcv_with_backoff('1d', 121)
        except (ccxt.RateLimitExceeded, ccxt.NetworkError) as exc:
            logger.warning('Vibe: candle fetch failed sau tất cả lần thử: %s', exc)
            return _no_trade('candle fetch failed (rate limit / network)')
        except Exception as exc:
            logger.warning('Vibe: fetch candles failed: %s', exc)
            return _no_trade('candle fetch failed')

        # BỎ NẾN ĐANG CHẠY DỞ (NẾN CUỐI CÙNG [:-1]) ĐỂ GIỐNG HỆT BACKTESTER
        if len(raw_4h) > 1:
            raw_4h = raw_4h[:-1]
        if len(raw_1d) > 1:
            raw_1d = raw_1d[:-1]

        if len(raw_4h) < 80 or len(raw_1d) < 60:
            return _no_trade('insufficient candle data')

        signal_candle_timestamp = int(raw_4h[-1][0] / 1000)
        closes_4h = [float(c[4]) for c in raw_4h]
        highs_4h  = [float(c[2]) for c in raw_4h]
        lows_4h   = [float(c[3]) for c in raw_4h]
        closes_1d = [float(c[4]) for c in raw_1d]
        highs_1d  = [float(c[2]) for c in raw_1d]
        lows_1d   = [float(c[3]) for c in raw_1d]

        # ── Regime snapshots ──────────────────────────────────────────
        daily_snapshot = self._vibe_snapshot(
            highs_1d, lows_1d, closes_1d, trend_adx_threshold, chop_adx_threshold, high_atr_pct
        )
        intraday_snapshot = self._vibe_snapshot(
            highs_4h, lows_4h, closes_4h, trend_adx_threshold, chop_adx_threshold, high_atr_pct
        )

        logger.debug(
            'Vibe Daily Regime: %s (%s) | Intraday Regime: %s (%s)',
            daily_snapshot.regime, daily_snapshot.reason,
            intraday_snapshot.regime, intraday_snapshot.reason,
        )

        # ── Choppiness / Volatility filter ────────────────────────────
        if self._vibe_too_choppy(daily_snapshot, intraday_snapshot, high_atr_pct, chop_adx_threshold):
            reason = 'Market is too noisy or the fluctuation range is too large'
            if daily_snapshot.regime == 'HIGH_VOLATILITY' or intraday_snapshot.regime == 'HIGH_VOLATILITY':
                reason = 'Volatility is too strong, ATR is high and stop loss sweep risk is large, prioritizing staying out to preserve capital.'
            elif intraday_snapshot.adx <= chop_adx_threshold and intraday_snapshot.atr_pct >= high_atr_pct * 0.35:
                reason = 'Market is tight and lacks a clear direction, waiting for confirmation breakout before placing order.'
            return _no_trade(reason, intraday_snapshot.adx, self._calculate_rsi(closes_4h))

        # ── Direction signal ──────────────────────────────────────────
        side = self._vibe_select_direction(closes_1d, closes_4h, daily_snapshot, intraday_snapshot, int(raw_4h[-1][0]))
        if side is None:
            return _no_trade(
                'No consensus between trend and momentum',
                intraday_snapshot.adx,
                self._calculate_rsi(closes_4h),
            )

        # ── Tính toán SL/TP động dựa trên ATR của 4H (Giống hệt Backtester) ───────
        if self._entry_already_processed_for_candle(symbol, signal_candle_timestamp):
            return _no_trade(
                f'already processed closed 4h candle {signal_candle_timestamp}',
                intraday_snapshot.adx,
                self._calculate_rsi(closes_4h),
            )

        last_close = closes_4h[-1]
        atr_value = self._calculate_atr(highs_4h, lows_4h, closes_4h, period=14)

        # ── Configurable ATR multipliers (env-driven, safe defaults) ───────────
        # Dùng biến môi trường để dễ tối ưu theo từng coin:
        # - BTC: TP_MULTIPLIER=3.0 (ăn trend xa), SL_MULTIPLIER=1.5
        # - XRP/Altcoin: hạ TP_MULTIPLIER xuống 1.5 để cắn TP nhanh hơn
        sl_multiplier = float(os.getenv('VIBE_ATR_SL_MULTIPLIER', '1.5'))
        tp_multiplier = float(os.getenv('VIBE_ATR_TP_MULTIPLIER', '3.0'))

        raw_sl_distance = atr_value * sl_multiplier
        raw_tp_distance = atr_value * tp_multiplier

        # ── Percentage cap — tránh TP/SL quá xa cho altcoin ─────────────────
        # Ví dụ XRP ATR=0.04 → TP_dist=0.12 (10% giá) → quá xa, cap về 5%
        # BTC ATR=1500 → TP_dist=4500 (7% giá) → trong ngưỡng, giữ nguyên
        tp_max_pct = float(os.getenv('VIBE_ATR_TP_MAX_PCT', '0.05'))  # 5% mặc định
        sl_max_pct = float(os.getenv('VIBE_ATR_SL_MAX_PCT', '0.03'))  # 3% mặc định

        sl_distance = min(raw_sl_distance, last_close * sl_max_pct)
        tp_distance = min(raw_tp_distance, last_close * tp_max_pct)

        if raw_sl_distance != sl_distance:
            logger.info(
                'ATR SL capped: raw=%.4f (%.2f%%) → capped=%.4f (%.2f%%) [VIBE_ATR_SL_MAX_PCT=%.1f%%]',
                raw_sl_distance, (raw_sl_distance / last_close) * 100,
                sl_distance, (sl_distance / last_close) * 100,
                sl_max_pct * 100,
            )
        if raw_tp_distance != tp_distance:
            logger.info(
                'ATR TP capped: raw=%.4f (%.2f%%) → capped=%.4f (%.2f%%) [VIBE_ATR_TP_MAX_PCT=%.1f%%]',
                raw_tp_distance, (raw_tp_distance / last_close) * 100,
                tp_distance, (tp_distance / last_close) * 100,
                tp_max_pct * 100,
            )

        if side == 'buy':
            stop_loss_price = last_close - sl_distance
            take_profit_price = last_close + tp_distance
        else:
            stop_loss_price = last_close + sl_distance
            take_profit_price = last_close - tp_distance

        # Tròn số SL/TP theo bước giá
        stop_loss_price = round(stop_loss_price, 4)
        take_profit_price = round(take_profit_price, 4)

        # ── Active position / pyramiding check ──────────────────────
        open_pos = self._get_open_position_info(symbol)
        active_symbol_layers = self._active_trade_layers(symbol)
        if open_pos is not None or active_symbol_layers > 0:
            if self.max_pyramid_layers <= 0:
                return _no_trade('active position detected (pyramiding off)', intraday_snapshot.adx, self._calculate_rsi(closes_4h))
            if open_pos:
                pos_is_long = open_pos['side'] == 'long'
                sig_is_long = side == 'buy'
                if pos_is_long != sig_is_long:
                    return _no_trade(
                        f'Pyramid blocked: ngược chiều pos={open_pos["side"]} vs {side}',
                        intraday_snapshot.adx,
                        self._calculate_rsi(closes_4h),
                    )
                if os.getenv('VIBE_PYRAMID_ONLY_WINNERS', 'false').lower() in {'1', 'true', 'yes'}:
                    entry = float(open_pos.get('entry_price') or 0.0)
                    step = atr_value * float(os.getenv('VIBE_PYRAMID_STEP_ATR', '1.0'))
                    progressed = last_close >= entry + step if sig_is_long else last_close <= entry - step
                    if entry > 0 and not progressed:
                        return _no_trade(
                            'Pyramid blocked: existing layer has not advanced by the configured ATR step',
                            intraday_snapshot.adx,
                            self._calculate_rsi(closes_4h),
                        )
            same_side_layers = self._active_trade_layers(symbol, side)
            if open_pos is not None and same_side_layers == 0:
                same_side_layers = 1
            if same_side_layers >= self.max_pyramid_layers:
                return _no_trade(
                    f'Pyramid limit: {same_side_layers}>={self.max_pyramid_layers} layers',
                    intraday_snapshot.adx,
                    self._calculate_rsi(closes_4h),
                )

        # Fetch on-chain signal from Mantle reader (non-blocking, defaults to 0)
        onchain_score = self._fetch_onchain_score()
        onchain_bias = 'neutral'
        if onchain_score >= 3:
            onchain_bias = 'bullish'
        elif onchain_score <= -3:
            onchain_bias = 'bearish'

        # On-chain veto: if strong disagreement with signal direction, demote to WATCH
        if onchain_score <= -5 and side == 'buy':
            return _no_trade(
                f'On-chain veto: strong bearish signal (score={onchain_score:.1f}) conflicts with BUY',
                adx=intraday_snapshot.adx,
                rsi=self._calculate_rsi(closes_4h),
            )
        if onchain_score >= 5 and side == 'sell':
            return _no_trade(
                f'On-chain veto: strong bullish signal (score={onchain_score:.1f}) conflicts with SELL',
                adx=intraday_snapshot.adx,
                rsi=self._calculate_rsi(closes_4h),
            )

        rr_ratio = 0.0
        if stop_loss_price and take_profit_price and last_close:
            sl_dist = abs(last_close - stop_loss_price)
            tp_dist = abs(take_profit_price - last_close)
            if sl_dist > 0:
                rr_ratio = round(tp_dist / sl_dist, 2)

        return AutoTradeDecision(
            should_trade=True,
            side=side,
            reason=f'{daily_snapshot.regime} / {intraday_snapshot.regime} confluence | on-chain={onchain_bias}({onchain_score:+.1f})',
            adx=intraday_snapshot.adx,
            rsi=self._calculate_rsi(closes_4h),
            symbol=symbol,
            market_power_status='VIBE',
            market_power_action='TRADE',
            market_power_score=onchain_score,  # expose on-chain score as market_power_score
            whale_score=0.0,
            news_score=onchain_score,
            news_reason=f'Mantle on-chain score={onchain_score:+.1f} ({onchain_bias})',
            entry_price=last_close,
            entry_type='BacktesterClose',
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            signal_candle_timestamp=signal_candle_timestamp,
            rr_ratio=rr_ratio,
        )

    def _fetch_onchain_score(self) -> float:
        """Read latest Mantle on-chain score from Redis (set by mantle_onchain_reader.py).

        Returns a float in [-10, +10] (0.0 if not available).
        Positive = bullish on-chain activity; negative = bearish.
        """
        try:
            raw = self.redis.get('onchain_score:latest')
            if raw:
                data = json.loads(raw)
                return float(data.get('onchain_score', 0.0))
        except Exception as exc:
            logger.debug('onchain_score read failed (non-critical): %s', exc)
        return 0.0

    def _entry_gate_enabled(self) -> bool:
        return os.getenv('AUTO_TRADE_ONCE_PER_4H_CANDLE', 'true').lower() in {'1', 'true', 'yes', 'on'}

    def _entry_candle_key(self, symbol: str) -> str:
        safe_symbol = symbol.replace('/', '_').replace(':', '_')
        return f'auto_trade:last_entry_candle:{self.auto_trade_mode}:{safe_symbol}'

    def _entry_already_processed_for_candle(self, symbol: str, candle_timestamp: Optional[int]) -> bool:
        if not self._entry_gate_enabled() or candle_timestamp is None:
            return False
        key = self._entry_candle_key(symbol)
        local_ts = self._last_auto_trade_candle_ts.get(key, 0)
        try:
            raw = self.redis.get(key)
            if raw:
                stored_ts = int(raw.decode('utf-8') if isinstance(raw, (bytes, bytearray)) else raw)
                local_ts = max(local_ts, stored_ts)
        except Exception as exc:
            logger.debug('Unable to read candle entry gate key %s: %s', key, exc)
        return local_ts >= candle_timestamp

    def _mark_entry_candle_processed(self, symbol: str, candle_timestamp: Optional[int]) -> None:
        if not self._entry_gate_enabled() or candle_timestamp is None:
            return
        key = self._entry_candle_key(symbol)
        self._last_auto_trade_candle_ts[key] = candle_timestamp
        try:
            self.redis.set(key, str(candle_timestamp), ex=60 * 60 * 24 * 14)
        except Exception as exc:
            logger.warning('Unable to persist candle entry gate key %s: %s', key, exc)

    def _execute_auto_trade(self, decision: AutoTradeDecision, decision_hash: Optional[str] = None) -> None:
        """Execute auto-trade with Dynamic Leverage, Risk-% Sizing and SMC Precision Entry."""
        # ── Cooldown guard ────────────────────────────────────────
        # Ngăn bot nhồi lệnh liên tục khi score vẫn đạt ngưỡng sau mỗi chu kỳ quét.
        if self._entry_already_processed_for_candle(decision.symbol, decision.signal_candle_timestamp):
            logger.info(
                'Auto-trade skipped: closed 4h candle %s already processed for %s',
                decision.signal_candle_timestamp,
                decision.symbol,
            )
            return

        elapsed_since_last = time.time() - self._last_auto_trade_at
        if self._last_auto_trade_at > 0 and elapsed_since_last < self.auto_trade_cooldown_seconds:
            remaining = int(self.auto_trade_cooldown_seconds - elapsed_since_last)
            logger.info(
                '⏳ Auto-trade cooldown: còn %d giây nữa mới được vào lệnh tiếp theo (cooldown=%ds)',
                remaining, self.auto_trade_cooldown_seconds,
            )
            return

        try:
            from executor.smart_money import get_precision_entry
        except ImportError:
            from smart_money import get_precision_entry

        ticker = self._fetch_market_data_ticker_with_retry(decision.symbol)
        current_price = float(ticker['last'] or ticker['close'])
        if current_price <= 0:
            raise ValueError(f'invalid entry price for {decision.symbol}')

        # Dùng available margin để tính qty — không tính unrealized PnL
        free_balance = self._fetch_available_margin_with_retry()
        logger.info('Auto-trade balance check: available_margin=%.2f', free_balance)

        if free_balance <= 0:
            logger.warning('Không có số dư để trade, bỏ qua auto-trade')
            return

        # ── Dynamic Leverage ────────────────────────────────────────────────
        # 10x khi cả kỹ thuật và tin tức đều rất mạnh, ngược lại 2x để an toàn
        dynamic_lev_enabled = (
            os.getenv('DYNAMIC_LEVERAGE_ENABLED', 'true').lower() in {'1', 'true', 'yes'}
            and not self.vibe_parity_mode
        )
        high_lev = int(os.getenv('DYNAMIC_LEVERAGE_HIGH', '10'))
        low_lev = int(os.getenv('DYNAMIC_LEVERAGE_LOW', '2'))
        news_lev_threshold = float(os.getenv('DYNAMIC_LEVERAGE_NEWS_THRESHOLD', '10'))
        score_lev_threshold = float(os.getenv('DYNAMIC_LEVERAGE_SCORE_THRESHOLD', '50'))

        if dynamic_lev_enabled:
            tech_ok = abs(decision.market_power_score) >= score_lev_threshold
            news_ok = abs(decision.news_score) >= news_lev_threshold
            final_leverage = high_lev if (tech_ok and news_ok) else low_lev
            logger.info(
                'Dynamic leverage: tech_ok=%s news_ok=%s → %dx (score=%.1f news=%.1f)',
                tech_ok, news_ok, final_leverage, decision.market_power_score, decision.news_score,
            )
        else:
            final_leverage = int(os.getenv('VIBE_DEFAULT_LEVERAGE', str(self.forced_leverage))) if self.vibe_parity_mode else self.forced_leverage

        # ── Risk-% Position Sizing ───────────────────────────────────────────
        # Tính quantity dựa trên % rủi ro tài khoản thay vì % số dư cố định
        max_compound_balance = float(os.getenv('MAX_COMPOUND_BALANCE', '1000.0'))
        effective_balance = min(free_balance, max_compound_balance)
        risk_pct = float(os.getenv('VIBE_RISK_PER_TRADE' if self.vibe_parity_mode else 'RISK_PER_TRADE', os.getenv('RISK_PER_TRADE', '0.02')))
        
        # Áp dụng cơ chế giảm rủi ro chuỗi thua liên tiếp (tương tự backtester)
        if self._consecutive_losses >= 3:
            logger.info('Chuỗi thua liên tiếp >= 3 (hiện tại: %d) -> Giảm rủi ro xuống còn 1/3: %.4f%% -> %.4f%%', 
                        self._consecutive_losses, risk_pct * 100, (risk_pct / 3.0) * 100)
            risk_pct = risk_pct / 3.0
            
        risk_amount = effective_balance * risk_pct

        # ── SMC Precision Entry (FVG / Order Block) ──────────────────────────
        precision_price: Optional[float] = None
        entry_type = 'Market'
        if self.smc_enabled and not self.vibe_parity_mode:
            try:
                candles = self.market_data_exchange.fetch_ohlcv(
                    decision.symbol,
                    timeframe=os.getenv('SMC_TIMEFRAME', '15m'),
                    limit=int(os.getenv('SMC_LOOKBACK', '100')),
                )
                if candles and len(candles) >= 10:
                    max_offset = float(os.getenv('SMC_MAX_OFFSET_PCT', '0.005'))
                    precision_price, entry_type = get_precision_entry(
                        candles, decision.side, current_price, max_offset
                    )
                    logger.info('SMC entry: type=%s price=%s', entry_type, precision_price)
            except Exception as exc:
                logger.warning('SMC analysis failed, falling back to Market: %s', exc)
        elif self.vibe_parity_mode:
            entry_type = 'BacktesterClose'

        ref_price = float(decision.entry_price) if self.vibe_parity_mode and decision.entry_price else (precision_price if precision_price else current_price)

        # ── SL/TP Determination ───────────────────────────────────────────────
        if decision.stop_loss_price is not None and decision.take_profit_price is not None:
            # Structural ATR SL/TP levels from 4H closed candles (perfect alignment with backtest)
            sl_price = decision.stop_loss_price
            tp_price = decision.take_profit_price
            logger.info('Using structural ATR SL/TP: SL=%.2f, TP=%.2f', sl_price, tp_price)
        else:
            # Fallback to fixed percentages based on entry ref_price
            if decision.side == 'buy':
                sl_price = ref_price * (1 - self.auto_trade_stop_loss_pct)
                tp_price = ref_price * (1 + self.auto_trade_take_profit_pct)
            else:
                sl_price = ref_price * (1 + self.auto_trade_stop_loss_pct)
                tp_price = ref_price * (1 - self.auto_trade_take_profit_pct)
            sl_price = round(sl_price, 2)
            tp_price = round(tp_price, 2)
            logger.info('Using relative fixed SL/TP: SL=%.2f, TP=%.2f', sl_price, tp_price)

        # ── Quantity Sizing Based on Risk Distance ───────────────────────────
        stop_distance = abs(ref_price - sl_price)
        if stop_distance > 0:
            quantity = risk_amount / stop_distance
            sl_distance_pct = stop_distance / ref_price
        else:
            quantity = (free_balance * self.auto_trade_balance_fraction * final_leverage) / ref_price
            sl_distance_pct = 0.0

        logger.info(
            'Risk sizing: balance=%.2f risk=%.1f%% risk_amt=%.2f sl_dist=%.3f%% qty=%.6f ref_price=%.2f',
            free_balance, risk_pct * 100, risk_amount, sl_distance_pct * 100, quantity, ref_price,
        )

        # ── Minimum order validation (OKX SWAP: đơn vị là contracts) ──────────
        try:
            market = self.exchange.market(decision.symbol)
            min_qty = float(market.get('limits', {}).get('amount', {}).get('min') or 0.0)
            min_cost = float(market.get('limits', {}).get('cost', {}).get('min') or 0.0)

            if self.exchange_platform == 'okx':
                # OKX SWAP: sz = số contracts. 1 contract = contractSize BTC (vd 0.01 BTC).
                # Phải đảm bảo quantity >= 1 contract để tránh lỗi 51020.
                contract_size = float(market.get('contractSize') or 0.01)
                raw_contracts = quantity / contract_size
                n_contracts = max(1, int(raw_contracts))  # >= 1 contract
                quantity_in_contracts_btc = n_contracts * contract_size
                if raw_contracts < 1.0:
                    logger.warning(
                        'Qty %.8f BTC = %.4f contracts < 1, nâng lên %d contract (%.8f BTC)',
                        quantity, raw_contracts, n_contracts, quantity_in_contracts_btc,
                    )
                quantity = quantity_in_contracts_btc

            if min_qty > 0 and quantity < min_qty:
                logger.warning('Qty %.8f < min_qty %.8f, lifting to min', quantity, min_qty)
                quantity = min_qty
            if min_cost > 0 and quantity * ref_price < min_cost:
                quantity = min_cost / ref_price

            if quantity <= 0 or (min_qty > 0 and quantity < min_qty):
                logger.error('BỎ QUA: qty=%.8f không hợp lệ', quantity)
                return
        except Exception as exc:
            logger.warning('Không kiểm tra được min qty: %s', exc)
            return

        signal = TradingSignal(
            timestamp=int(time.time()),
            symbol=decision.symbol,
            side=decision.side,
            leverage=final_leverage,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            quantity=quantity,
            action='AUTO_TRADE',
            status='AUTOPILOT',
            reason=decision.reason,
            market_power_score=decision.market_power_score,
            decision_hash=decision_hash,
        )

        logger.info(
            'Auto-trade executing %s: score=%.2f news=%+.1f lev=%dx qty=%.6f entry=%s@%.4f',
            decision.side.upper(), decision.market_power_score, decision.news_score,
            final_leverage, quantity, entry_type, ref_price,
        )

        # ── Open the trade (Market or Limit) ─────────────────────────────────
        trade = self._open_trade(signal, limit_price=precision_price, entry_type=entry_type)
        self.signal_store.push_history(signal, 'executed', f'auto_trade trade_id={trade.trade_id}')
        self.signal_store.save_trade(trade)
        # Đặt cooldown timer sau khi mở lệnh thành công
        self._last_auto_trade_at = time.time()

        self._mark_entry_candle_processed(decision.symbol, decision.signal_candle_timestamp)

        onchain_score = decision.market_power_score  # now set to onchain_score in vibe mode
        onchain_line = f'On-Chain Score: {onchain_score:+.1f} | {decision.news_reason[:50]}'
        actual_entry = float(trade.entry_price)
        actual_sl = float(trade.signal.stop_loss_price)
        actual_tp = float(trade.signal.take_profit_price)
        rr_raw = abs(actual_tp - actual_entry) / max(abs(actual_sl - actual_entry), 0.0001)
        self._send_discord_message(
            title=f'AUTO TRADE - {signal.side.upper()} {decision.symbol}',
            message=(
                f'Entry Type: **{entry_type}** @ `{actual_entry:.4f}`\n'
                f'SL: `{actual_sl:.4f}` | TP: `{actual_tp:.4f}`\n'
                f'Qty: `{trade.quantity:.6f}` | Risk: `{risk_pct*100:.1f}%` | R:R: `{rr_raw:.2f}:1`\n'
                f'{onchain_line}\n'
                f'Reason: {decision.reason[:120]}'
            ),
            color=0x00D26A if signal.side == 'buy' else 0xFF4D4D,
            fields=[
                {'name': 'Leverage', 'value': f'{final_leverage}x', 'inline': True},
                {'name': 'ADX / RSI', 'value': f'{decision.adx:.1f} / {decision.rsi:.1f}', 'inline': True},
                {'name': 'SL Orders', 'value': 'OFF' if self.disable_protective_orders else 'ON', 'inline': True},
            ],
        )

    def _daily_summary_loop(self) -> None:
        """Send daily summary at the configured wall-clock time (DAILY_SUMMARY_TIME=HH:MM) in Vietnam timezone."""
        from zoneinfo import ZoneInfo
        vn_tz = ZoneInfo('Asia/Ho_Chi_Minh')

        time_str = os.getenv('DAILY_SUMMARY_TIME', '09:00')
        try:
            h, m = (int(x) for x in time_str.split(':'))
        except Exception:
            h, m = 9, 0
            logger.warning('Invalid DAILY_SUMMARY_TIME "%s", defaulting to 09:00', time_str)

        while True:
            try:
                now = datetime.now(vn_tz)
                target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if target <= now:
                    target += timedelta(days=1)
                wait_seconds = (target - now).total_seconds()
                logger.info(
                    'Daily summary scheduled at %02d:%02d VN (in %.0f min)',
                    h, m, wait_seconds / 60,
                )
                time.sleep(wait_seconds)
                self._send_daily_summary()
            except Exception as exc:
                logger.exception('Daily summary loop error: %s', exc)
                time.sleep(60)  # retry in 1 min on error

    def _redis_daily_key(self) -> str:
        """Redis hash key cho daily live stats (reset mỗi ngày)."""
        from zoneinfo import ZoneInfo
        vn_date = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d')
        return f'daily_live_stats:{vn_date}'

    def _fallback_filepath(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'daily_stats_fallback.json')

    def _persist_daily_stats_to_fallback_file(self) -> None:
        """Ghi daily stats ra file JSON fallback cục bộ."""
        try:
            from zoneinfo import ZoneInfo
            vn_date = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d')
            fallback_file = self._fallback_filepath()
            
            with self._daily_stats_lock:
                data = {
                    'date': vn_date,
                    'trades_count': self._daily_trades_count,
                    'wins_count': self._daily_wins_count,
                    'losses_count': self._daily_losses_count,
                    'realized_pnl': self._daily_realized_pnl,
                    'start_balance': self._daily_start_balance,
                    'consecutive_losses': self._consecutive_losses
                }
            
            temp_file = fallback_file + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            if os.path.exists(fallback_file):
                os.remove(fallback_file)
            os.rename(temp_file, fallback_file)
        except Exception as exc:
            logger.warning('Không ghi được stats ra file fallback: %s', exc)

    def _restore_daily_stats_from_redis(self) -> None:
        """Khôi phục daily stats từ Redis hoặc JSON fallback khi executor restart trong ngày."""
        from zoneinfo import ZoneInfo
        vn_date = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d')
        fallback_file = self._fallback_filepath()
        
        # 1. Cố gắng khôi phục từ Redis trước
        redis_raw = None
        try:
            redis_raw = self.redis.hgetall(self._redis_daily_key())
        except Exception as exc:
            logger.warning('Không kết nối được Redis để khôi phục stats: %s', exc)

        if redis_raw:
            try:
                # Giải mã dữ liệu từ bytes nếu decode_responses=False
                decoded_raw = {}
                for k, v in redis_raw.items():
                    try:
                        decoded_raw[k.decode('utf-8')] = v.decode('utf-8')
                    except Exception:
                        decoded_raw[str(k)] = str(v)
                
                with self._daily_stats_lock:
                    self._daily_trades_count = int(float(decoded_raw.get('trades_count', '0')))
                    self._daily_wins_count   = int(float(decoded_raw.get('wins_count',   '0')))
                    self._daily_losses_count = int(float(decoded_raw.get('losses_count', '0')))
                    self._daily_realized_pnl = float(decoded_raw.get('realized_pnl', '0'))
                    self._consecutive_losses = int(float(decoded_raw.get('consecutive_losses', '0')))
                    start_bal = decoded_raw.get('start_balance')
                    if start_bal:
                        self._daily_start_balance = float(start_bal)
                    else:
                        self._daily_start_balance = self._starting_balance
                logger.info(
                    'Daily stats khôi phục từ Redis: trades=%d wins=%d losses=%d pnl=%.4f start=%.2f consecutive_losses=%d',
                    self._daily_trades_count, self._daily_wins_count, self._daily_losses_count,
                    self._daily_realized_pnl, self._daily_start_balance or 0, self._consecutive_losses
                )
                # Đồng bộ ngược ra file fallback
                self._persist_daily_stats_to_fallback_file()
                return
            except Exception as exc:
                logger.warning('Lỗi giải mã dữ liệu Redis, thử dùng file fallback: %s', exc)

        # 2. Dự phòng: Khôi phục từ JSON fallback
        if os.path.exists(fallback_file):
            try:
                with open(fallback_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Luôn giữ lại consecutive_losses của ngày cũ để không bị mất vết thị trường xấu
                old_consecutive_losses = data.get('consecutive_losses', 0)
                
                if data.get('date') == vn_date:
                    with self._daily_stats_lock:
                        self._daily_trades_count = data.get('trades_count', 0)
                        self._daily_wins_count   = data.get('wins_count', 0)
                        self._daily_losses_count = data.get('losses_count', 0)
                        self._daily_realized_pnl = data.get('realized_pnl', 0.0)
                        self._consecutive_losses = old_consecutive_losses
                        self._daily_start_balance = data.get('start_balance', self._starting_balance)
                    logger.info(
                        'Daily stats khôi phục từ file fallback: trades=%d wins=%d losses=%d pnl=%.4f start=%.2f consecutive_losses=%d',
                        self._daily_trades_count, self._daily_wins_count, self._daily_losses_count,
                        self._daily_realized_pnl, self._daily_start_balance or 0, self._consecutive_losses
                    )
                    return
                else:
                    logger.info(
                        'File fallback là của ngày cũ (%s vs %s), khởi tạo ngày mới nhưng giữ consecutive_losses=%d.',
                        data.get('date'), vn_date, old_consecutive_losses
                    )
                    self._consecutive_losses = old_consecutive_losses
            except Exception as exc:
                logger.warning('Lỗi đọc file stats fallback: %s', exc)

        # 3. Mặc định nếu không có cả hai:
        self._daily_start_balance = self._starting_balance
        self._consecutive_losses = 0
        self._persist_daily_stats_to_fallback_file()

    def _persist_daily_stats_to_redis(self) -> None:
        """Ghi daily live stats lên Redis và file JSON fallback cục bộ."""
        # 1. Ghi ra file JSON fallback trước
        self._persist_daily_stats_to_fallback_file()
        
        # 2. Ghi lên Redis
        try:
            key = self._redis_daily_key()
            with self._daily_stats_lock:
                mapping = {
                    'trades_count': str(self._daily_trades_count),
                    'wins_count':   str(self._daily_wins_count),
                    'losses_count': str(self._daily_losses_count),
                    'realized_pnl': str(self._daily_realized_pnl),
                    'start_balance': str(self._daily_start_balance or 0),
                    'consecutive_losses': str(self._consecutive_losses),
                }
            self.redis.hset(key, mapping=mapping)
            self.redis.expire(key, 36 * 3600)  # hết hạn sau 36h
        except Exception as exc:
            logger.debug('Không ghi daily stats vào Redis: %s', exc)

    def _record_daily_trade_execution(self) -> None:
        with self._daily_stats_lock:
            self._daily_trades_count += 1
        self._persist_daily_stats_to_redis()

    def _build_daily_summary_message(
        self,
        trades_count: int,
        realized_pnl: float,
        balance_change: float,
        current_balance: float,
        start_balance: float,
        open_positions_count: int = 0,
    ) -> str:
        pnl_emoji = '🟢' if realized_pnl >= 0 else '🔴'
        bal_emoji  = '🟢' if balance_change >= 0 else '🔴'
        return (
            f'**Số lệnh mở:** {trades_count}\n'
            f'**Thắng / Thua:** {self._daily_wins_count}W / {self._daily_losses_count}L\n'
            f'{pnl_emoji} **Realized PnL:** {realized_pnl:+.4f} USDT\n'
            f'{bal_emoji} **Balance thay đổi:** {balance_change:+.2f} USDT\n'
            f'\n'
            f'💰 **Đầu ngày:** {start_balance:.2f} USDT\n'
            f'💰 **Hiện tại:** {current_balance:.2f} USDT\n'
            + (f'⏳ **Đang mở:** {open_positions_count} vị thế\n' if open_positions_count > 0 else '')
        )

    def _persist_daily_summary(self, trades_count: int, total_pnl: float, current_balance: float, start_balance: float) -> None:
        from zoneinfo import ZoneInfo
        summary = {
            'report_time': datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(timespec='seconds'),
            'trades_count': trades_count,
            'wins_count': self._daily_wins_count,
            'losses_count': self._daily_losses_count,
            'total_pnl': round(total_pnl, 8),
            'start_balance': round(start_balance, 8),
            'current_balance': round(current_balance, 8),
        }
        payload = json.dumps(summary, separators=(',', ':'), ensure_ascii=False)

        try:
            self.redis.hset('daily_summary:latest', mapping={k: str(v) for k, v in summary.items()})
            self.redis.lpush('daily_summary:history', payload)
            self.redis.ltrim('daily_summary:history', 0, 59)
        except RedisError as exc:
            logger.warning('Unable to persist daily summary to Redis: %s', exc)

    def _send_daily_summary(self) -> None:
        current_balance = self._fetch_usdt_balance_with_retry()

        # Đếm vị thế đang mở
        try:
            positions = self.exchange.fetch_positions([self.auto_trade_symbol])
            open_pos_count = sum(
                1 for p in positions
                if abs(float(p.get('contracts') or p.get('info', {}).get('positionAmt') or 0)) > 0
            )
        except Exception:
            open_pos_count = 0

        with self._daily_stats_lock:
            trades_count  = self._daily_trades_count
            realized_pnl  = self._daily_realized_pnl  # ← từ từng lệnh đóng, chính xác
            if self._daily_start_balance is None:
                self._daily_start_balance = current_balance
            start_balance    = float(self._daily_start_balance)
            balance_change   = current_balance - start_balance  # thay đổi balance thực tế
            message = self._build_daily_summary_message(
                trades_count, realized_pnl, balance_change,
                current_balance, start_balance, open_pos_count,
            )

        logger.info(
            'Daily summary: trades=%d wins=%d losses=%d realized_pnl=%.4f balance_change=%.2f balance=%.2f',
            trades_count, self._daily_wins_count, self._daily_losses_count,
            realized_pnl, balance_change, current_balance,
        )
        self._send_discord_message('📊 Daily Summary', message, 0x3498DB)
        self._persist_daily_summary(trades_count, realized_pnl, current_balance, start_balance)

        with self._daily_stats_lock:
            self._daily_trades_count  = 0
            self._daily_wins_count    = 0
            self._daily_losses_count  = 0
            self._daily_total_pnl     = 0.0
            self._daily_realized_pnl  = 0.0
            self._daily_start_balance = current_balance
            self._daily_summary_started_at = time.time()
        # Xóa live stats cũ trên Redis (ngày mới bắt đầu)
        try:
            self.redis.delete(self._redis_daily_key())
        except Exception:
            pass


    def _has_active_trade(self) -> bool:
        return len(self.signal_store.load_active_trade_ids()) > 0

    def _active_trade_layers(self, symbol: str, side: Optional[str] = None) -> int:
        """Count active Redis trade records for a symbol, optionally same side only."""
        layers = 0
        for trade_id in self.signal_store.load_active_trade_ids():
            trade_data = self.signal_store.load_trade(trade_id)
            if not trade_data:
                continue
            if trade_data.get('symbol') != symbol:
                continue
            if side is not None and trade_data.get('side') != side:
                continue
            layers += 1
        return layers

    def _open_stop_risk(self) -> float:
        """Worst-case loss at the recorded stops for all active bot trades.

        This intentionally uses the bot's persisted layers, not exchange margin:
        margin tells us whether an order may be accepted, whereas this tells us
        whether the portfolio still fits its loss budget if all stops are hit.
        Missing/corrupt records are ignored rather than estimated optimistically.
        """
        total = 0.0
        for trade_id in self.signal_store.load_active_trade_ids():
            trade_data = self.signal_store.load_trade(trade_id)
            if not trade_data:
                continue
            try:
                entry = float(trade_data['entry_price'])
                stop = float(trade_data['stop_loss_price'])
                quantity = float(trade_data['quantity'])
                total += abs(entry - stop) * max(quantity, 0.0)
            except (KeyError, TypeError, ValueError):
                logger.warning('Ignoring malformed active trade %s in stop-risk calculation', trade_id)
        return total

    def _ensure_stop_risk_budget(self, balance: float, entry_price: float, stop_price: float, quantity: float) -> None:
        """Reject an entry when cumulative stop loss would exceed its budget."""
        if self.max_total_open_risk_pct <= 0:
            return
        new_risk = abs(entry_price - stop_price) * quantity
        existing_risk = self._open_stop_risk()
        budget = max(balance, 0.0) * self.max_total_open_risk_pct
        if existing_risk + new_risk > budget + 1e-9:
            raise ValueError(
                'entry rejected: aggregate stop risk '
                f'{existing_risk + new_risk:.4f} exceeds budget {budget:.4f} '
                f'({self.max_total_open_risk_pct * 100:.2f}% of available margin)'
            )

    def _has_open_position(self, symbol: str) -> bool:
        return self._get_open_position_info(symbol) is not None

    def _get_open_position_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Trả về {'side': 'long'|'short', 'contracts': float} nếu đang có vị thế, else None."""
        try:
            positions = self.exchange.fetch_positions([symbol])
        except Exception:
            return None

        for position in positions:
            contracts = position.get('contracts')
            if contracts is None:
                contracts = position.get('info', {}).get('positionAmt')
            try:
                n = abs(float(contracts or 0))
                if n > 0:
                    pos_side = str(position.get('side') or '').lower()
                    if not pos_side:
                        # Infer từ positionAmt: dương = long, âm = short
                        amt = float(position.get('info', {}).get('positionAmt', 0))
                        pos_side = 'long' if amt >= 0 else 'short'
                    entry_price = position.get('entryPrice') or position.get('average') or position.get('info', {}).get('avgPrice')
                    return {'side': pos_side, 'contracts': n, 'entry_price': float(entry_price or 0.0)}
            except (TypeError, ValueError):
                continue
        return None

    def _send_discord_message(
        self,
        title: str,
        message: str,
        color: int = 0x3498DB,
        fields: Optional[list[Dict[str, Any]]] = None,
    ) -> None:
        if not self.discord_webhook_url:
            return

        exchange_name = self.exchange_platform.upper()
        mode_name = 'DEMO' if self.is_demo else 'LIVE'
        final_fields = [
            {'name': 'Exchange', 'value': exchange_name, 'inline': True},
            {'name': 'Mode', 'value': mode_name, 'inline': True},
            {'name': 'Auto-Trade', 'value': 'ON' if self.auto_trade_enabled else 'OFF', 'inline': True},
        ]
        if fields:
            final_fields.extend(fields)

        # Append on-chain proof contract link if configured
        proof_contract = os.getenv('AGENT_PROOF_CONTRACT')
        chain_name = os.getenv('AGENT_PROOF_CHAIN', 'Mantle Sepolia')
        if proof_contract:
            mantlescan_url = f'https://explorer.sepolia.mantle.xyz/address/{proof_contract}'
            final_fields.append({
                'name': 'On-Chain Ledger',
                'value': f'[{proof_contract[:14]}... ({chain_name})]({mantlescan_url})',
                'inline': False,
            })

        payload = {
            'embeds': [{
                'title': title,
                'description': message,
                'color': color,
                'fields': final_fields,
                'footer': {'text': 'Mantle AI Quant Agent | mantlescan.xyz'},
                'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            }]
        }

        try:
            response = requests.post(self.discord_webhook_url, json=payload, timeout=10)
            response.raise_for_status()
        except Exception as exc:
            logger.warning('Discord notification failed: %s', exc)

    def _record_closed_trade_result(self, trade_data: Dict[str, str], current_price: float) -> None:
        # Ghi nhận lệnh thắng/thua để báo cáo cuối ngày dễ theo dõi hơn.
        pnl_bps = 0
        try:
            entry_price = float(trade_data['entry_price'])
            quantity = float(trade_data['quantity'])
            side = trade_data['side']
            if side == 'buy':
                pnl = (current_price - entry_price) * quantity
                pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0.0
            else:
                pnl = (entry_price - current_price) * quantity
                pnl_pct = (entry_price - current_price) / entry_price if entry_price > 0 else 0.0
            pnl_bps = int(pnl_pct * 10000)
        except Exception:
            pnl = 0.0

        with self._daily_stats_lock:
            self._daily_realized_pnl += pnl
            if pnl >= 0:
                self._daily_wins_count += 1
                self._consecutive_losses = 0
            else:
                self._daily_losses_count += 1
                self._consecutive_losses += 1
        # Write-through: persist ngay sau khi trade đóng
        self._persist_daily_stats_to_redis()

        # Save to agent_decision_outcomes
        decision_hash = trade_data.get('decision_hash')
        if decision_hash:
            try:
                outcome_payload = {
                    'outcome': 'win' if pnl >= 0 else 'loss',
                    'pnl_bps': pnl_bps,
                    'detail': f'Closed at {current_price:.4f} (Entry: {entry_price:.4f})',
                    'stored_at': int(time.time()),
                }
                self.redis.hset('agent_decision_outcomes', decision_hash, json.dumps(outcome_payload))
                logger.info('Saved trade outcome for decision %s to Redis: outcome=%s, pnl_bps=%d', 
                            decision_hash, outcome_payload['outcome'], pnl_bps)
            except Exception as exc:
                logger.warning('Failed to save trade outcome to Redis: %s', exc)

    def _close_all_open_positions(self) -> None:
        try:
            positions = self.exchange.fetch_positions()
        except Exception as exc:
            logger.warning('Không lấy được danh sách vị thế để đóng hết: %s', exc)
            return

        for position in positions:
            try:
                contracts = position.get('contracts')
                if contracts is None:
                    contracts = position.get('info', {}).get('positionAmt')
                amount = abs(float(contracts))
                if amount <= 0:
                    continue

                symbol = position.get('symbol')
                if not symbol:
                    continue

                raw_side = str(position.get('side') or '').lower()
                if raw_side in {'long', 'buy'}:
                    close_side = 'sell'
                elif raw_side in {'short', 'sell'}:
                    close_side = 'buy'
                else:
                    close_side = 'sell' if float(contracts) > 0 else 'buy'

                params = self._order_mode_params(reduce_only=True)
                self._create_order_with_retry(symbol, 'market', close_side, amount, None, params)
                logger.warning('Đã gửi lệnh đóng vị thế %s %s amount=%s', symbol, close_side.upper(), amount)
            except Exception as exc:
                logger.warning('Không đóng được một vị thế: %s', exc)

    def _close_all_positions_and_stop(self, message: str) -> None:
        self._close_all_open_positions()
        try:
            self._send_discord_message('🛑 BOT DỪNG - Cầu chì Daily Loss', message, 0xFF0000)
        except Exception:
            logger.warning('Failed to send daily-loss Discord notification')
        os._exit(1)

    def _check_daily_loss_and_maybe_stop(self) -> None:
        if self.daily_loss_limit_pct <= 0:
            return
        if self._stopped_due_to_daily_loss:
            return
        baseline = self._daily_start_balance if self._daily_start_balance is not None else self._starting_balance
        if baseline is None:
            return

        try:
            current = self._fetch_usdt_balance_with_retry()
        except Exception as exc:
            logger.warning('Could not fetch balance for daily loss check: %s', exc)
            return

        total_pnl = current - float(baseline)
        threshold_value = -float(baseline) * self.daily_loss_limit_pct

        if total_pnl <= threshold_value:
            self._stopped_due_to_daily_loss = True
            msg = (
                f'Giới hạn lỗ hàng ngày bị chạm: bắt đầu={baseline:.2f} USDT, '
                f'hiện tại={current:.2f} USDT, PnL={total_pnl:.2f} USDT, giới hạn={self.daily_loss_limit_pct * 100:.2f}%'
            )
            logger.error(msg)
            self._close_all_positions_and_stop(msg)

    def _inspect_trade(self, trade_id: str, trade_data: Dict[str, str], open_conditional_orders: list[Dict[str, Any]] = None, pos_info: Optional[Dict[str, Any]] = None) -> None:
        symbol = trade_data['symbol']
        side = trade_data['side']
        entry_price = float(trade_data['entry_price'])
        take_profit = float(trade_data['take_profit_price'])
        stop_loss = float(trade_data['stop_loss_price'])
        quantity = float(trade_data['quantity'])
        breakeven_moved = trade_data.get('breakeven_moved', '0') == '1'

        current_price = float(self._fetch_ticker_with_retry(symbol)['last'])
        if current_price <= 0:
            return

        if self.breakeven_enabled and not breakeven_moved and self._should_move_stop_to_breakeven(side, entry_price, take_profit, current_price):
            self._move_stop_to_breakeven(trade_id, trade_data, quantity, entry_price)
            return

        self._refresh_trade_state(trade_id, current_price, stop_loss, take_profit, open_conditional_orders, pos_info)

    def _should_move_stop_to_breakeven(self, side: str, entry_price: float, take_profit: float, current_price: float) -> bool:
        target_distance = abs(take_profit - entry_price)
        if target_distance <= 0:
            return False

        progress = (current_price - entry_price) if side == 'buy' else (entry_price - current_price)
        return progress >= target_distance * self.breakeven_trigger

    def _move_stop_to_breakeven(self, trade_id: str, trade_data: Dict[str, str], quantity: float, entry_price: float) -> None:
        symbol = trade_data['symbol']
        side = trade_data['side']
        stop_order_id = trade_data.get('stop_order_id') or None
        opposite_side = 'sell' if side == 'buy' else 'buy'

        if stop_order_id:
            self._cancel_protective_order(stop_order_id, symbol)

        new_stop_order = self._create_protective_order(
            symbol=symbol,
            side=opposite_side,
            quantity=quantity,
            stop_price=entry_price,
            order_type='STOP_MARKET',
        )
        trade = TradeState(
            trade_id=trade_id,
            signal=TradingSignal(
                timestamp=int(trade_data['timestamp']),
                symbol=symbol,
                side=side,
                leverage=int(trade_data['leverage']),
                stop_loss_price=float(trade_data['stop_loss_price']),
                take_profit_price=float(trade_data['take_profit_price']),
            ),
            entry_price=entry_price,
            quantity=quantity,
            stop_order_id=str(new_stop_order.get('id')) if new_stop_order else None,
            take_profit_order_id=trade_data.get('take_profit_order_id') or None,
            breakeven_moved=True,
            created_at=int(trade_data.get('created_at', time.time())),
        )
        self.signal_store.save_trade(trade)
        logger.info('Moved stop-loss to breakeven for %s', trade_id)

    def _refresh_trade_state(self, trade_id: str, current_price: float, stop_loss: float, take_profit: float, open_conditional_orders: list[Dict[str, Any]] = None, pos_info: Optional[Dict[str, Any]] = None) -> None:
        trade_data = self.signal_store.load_trade(trade_id)
        if not trade_data:
            self.signal_store.delete_trade(trade_id)
            return

        # Check if the trade has closed on the exchange
        trade_closed = False
        if open_conditional_orders is not None:
            trade_closed = not self._is_trade_active_on_exchange(trade_data, open_conditional_orders, pos_info)
        else:
            trade_closed = self._position_closed(trade_data['symbol'])

        if trade_closed:
            # ── Hủy toàn bộ SL/TP algo orders còn treo ──────────────────────
            # Khi TP khớp → OKX đóng vị thế nhưng KHÔNG tự hủy SL còn lại.
            # Nếu để SL treo → khi giá chạm đến trigger nó sẽ mở vị thế ngược
            # chiều ngoài ý muốn. Phải cancel hết trước khi xóa Redis trade.
            stop_order_id        = trade_data.get('stop_order_id') or ''
            take_profit_order_id = trade_data.get('take_profit_order_id') or ''
            symbol_cancel        = trade_data['symbol']

            for oid, label in [(stop_order_id, 'SL'), (take_profit_order_id, 'TP')]:
                if oid:
                    try:
                        self._cancel_protective_order(oid, symbol_cancel)
                        logger.info('Cancelled orphaned %s algo order %s after position closed', label, oid)
                    except Exception as exc:
                        logger.warning('Could not cancel orphaned %s order %s (may already be filled/cancelled): %s', label, oid, exc)

            self._record_closed_trade_result(trade_data, current_price)
            logger.info('Trade closed on exchange: %s', trade_id)
            self.signal_store.delete_trade(trade_id)
            return

        trade = TradeState(
            trade_id=trade_id,
            signal=TradingSignal(
                timestamp=int(trade_data['timestamp']),
                symbol=trade_data['symbol'],
                side=trade_data['side'],
                leverage=int(trade_data['leverage']),
                stop_loss_price=stop_loss,
                take_profit_price=take_profit,
                decision_hash=trade_data.get('decision_hash'),
            ),
            entry_price=float(trade_data['entry_price']),
            quantity=float(trade_data['quantity']),
            stop_order_id=trade_data.get('stop_order_id') or None,
            take_profit_order_id=trade_data.get('take_profit_order_id') or None,
            breakeven_moved=trade_data.get('breakeven_moved', '0') == '1',
            created_at=int(trade_data.get('created_at', time.time())),
        )
        self.signal_store.save_trade(trade)
        self._record_exchange_event(trade.signal.symbol, 'monitor_tick', {
            'trade_id': trade_id,
            'current_price': current_price,
        })

    def _position_closed(self, symbol: str) -> bool:
        """Check if a position is closed on the exchange.

        When in dry_run mode (e.g. auth/IP-whitelist failure), we cannot reliably
        query the exchange – treat the position as closed so stale Redis entries
        get cleaned up automatically and the bot can resume scanning.
        """
        if self.dry_run:
            logger.debug('Dry-run mode: treating %s position as closed for Redis cleanup', symbol)
            return True
        try:
            positions = self.exchange.fetch_positions([symbol])
        except ccxt.AuthenticationError:
            # Auth failure outside dry_run – same treatment: clean up stale trade
            logger.warning('Auth error checking position %s – assuming closed to avoid phantom block', symbol)
            return True
        except Exception:
            return False

        for position in positions:
            contracts = position.get('contracts')
            if contracts is None:
                contracts = position.get('info', {}).get('positionAmt')
            try:
                if abs(float(contracts)) > 0:
                    return False
            except (TypeError, ValueError):
                continue

        # Position is 0. Check if there is an unfilled entry limit order.
        try:
            open_orders = self.exchange.fetch_open_orders(symbol)
            if open_orders:
                # We still have open orders (e.g. pending Limit entry), so trade is not closed
                return False
        except Exception as exc:
            logger.warning('Error fetching open orders for %s: %s', symbol, exc)
            return False

        return True

    def _set_leverage(self, symbol: str, leverage: int) -> None:
        try:
            safe_leverage = max(1, int(leverage))
            self.exchange.set_leverage(safe_leverage, symbol, {'marginMode': self.margin_mode})
        except Exception as exc:
            logger.warning('Unable to set leverage for %s: %s', symbol, exc)

    def _calculate_quantity(self, balance: float, entry_price: float, stop_loss_price: float, leverage: int) -> float:
        risk_pct = self.risk_per_trade
        if self._consecutive_losses >= 3:
            risk_pct = risk_pct / 3.0
        risk_amount = balance * risk_pct
        stop_distance = abs(entry_price - stop_loss_price)
        if stop_distance <= 0:
            raise ValueError('stop loss must differ from entry price')

        raw_quantity = risk_amount / stop_distance
        max_affordable_quantity = (balance * max(leverage, 1) * self.max_position_fraction) / entry_price
        quantity = min(raw_quantity, max_affordable_quantity)
        if quantity <= 0:
            raise ValueError('calculated quantity is not positive')
        return quantity

    def _fetch_usdt_balance_with_retry(self) -> float:
        for attempt in range(3):
            try:
                balance = self.exchange.fetch_balance(self._fetch_balance_params())
                self._ip_whitelist_warned = False  # Reset on success
                return self._extract_usdt_balance(balance)
            except ccxt.AuthenticationError as exc:
                error_str = str(exc)
                if '50110' in error_str:
                    # OKX IP whitelist error – log once, then stay silent
                    if not self._ip_whitelist_warned:
                        logger.error(
                            'OKX API error 50110: IP %s không có trong whitelist. '
                            'Vào OKX → API Keys → Sửa key → Thêm IP hoặc bỏ IP restriction. '
                            'Bot chuyển sang dry-run.',
                            error_str.split('IP ')[1].split(' ')[0] if 'IP ' in error_str else '?',
                        )
                        self._ip_whitelist_warned = True
                else:
                    logger.warning('Authentication failed while fetching balance: %s', exc)
                
                if self.live_trading_mode:
                    msg = f"CRITICAL: Lỗi xác thực API khi lấy số dư (AuthenticationError). Dừng bot để bảo vệ tài khoản! Chi tiết: {exc}"
                    logger.error(msg)
                    try:
                        self._send_discord_message('🚨 CRITICAL ERROR - AUTHENTICATION FAILED', msg, 0xFF0000)
                    except Exception:
                        pass
                    os._exit(1)  # Auth error = sai key, dừng hẳn là đúng
                
                self.dry_run = True
                return 5000.0
            except (ccxt.NetworkError, ccxt.RateLimitExceeded) as exc:
                logger.warning('Balance fetch failed (attempt %s): %s', attempt + 1, exc)
                time.sleep(2 ** attempt)
        
        if self.live_trading_mode:
            msg = "⚠️ Không thể lấy số dư sau 3 lần thử (lỗi mạng tạm thời). Bot tiếp tục retry sau 60s."
            logger.warning(msg)
            try:
                self._send_discord_message('⚠️ Cảnh báo - Balance Fetch Failed', msg, 0xFFA500)
            except Exception:
                pass
            time.sleep(60)
            raise RuntimeError('balance fetch failed after 3 attempts — loop will retry')
            
        logger.warning('Failed to fetch balance after retries, using dry-run balance: 5000.0 USDT')
        return 5000.0

    def _extract_usdt_balance(self, balance: Dict[str, Any]) -> float:
        """Trả về tổng equity tài khoản (totalEq/totalEquity/walletBalance) — dùng cho báo cáo & kiểm tra cầu chì.
        Khớp với số dư hiển thị trên ứng dụng sàn (bao gồm unrealized PnL)."""
        exchange_id = self.exchange_platform.lower()
        info = balance.get('info', {})

        # 1. THỬ CÁCH PHỔ THÔNG VÀ AN TOÀN NHẤT CỦA CCXT TRƯỚC (Ăn tiền 90% các sàn)
        if isinstance(balance, dict) and 'total' in balance:
            if 'USDT' in balance['total'] and balance['total']['USDT'] is not None:
                total_val = float(balance['total']['USDT'])
                if total_val > 0:
                    return total_val
        if isinstance(balance, dict) and 'free' in balance:
            if 'USDT' in balance['free'] and balance['free']['USDT'] is not None:
                free_val = float(balance['free']['USDT'])
                if free_val > 0:
                    return free_val

        # -------------------------------------------------------------
        # TRƯỜNG HỢP 1: SÀN BYBIT
        # -------------------------------------------------------------
        if exchange_id == 'bybit' and isinstance(info, dict):
            # Thử lấy tổng Equity của Unified Trading Account trước
            info_list = info.get('result', {}).get('list', [])
            if not info_list:
                info_list = info.get('list', [])
            
            if info_list and isinstance(info_list, list):
                total_eq = info_list[0].get('totalEquity')
                if total_eq is not None:
                    try:
                        val = float(total_eq)
                        if val > 0:
                            return val
                    except (ValueError, TypeError):
                        pass

        # -------------------------------------------------------------
        # TRƯỜNG HỢP 2: SÀN OKX
        # -------------------------------------------------------------
        elif exchange_id == 'okx' and isinstance(info, dict):
            info_data = info.get('data', [])
            if info_data and isinstance(info_data, list):
                for key in ('totalEq', 'total_eq'):
                    val = info_data[0].get(key)
                    if val is not None:
                        try:
                            f_val = float(val)
                            if f_val > 0:
                                return f_val
                        except (ValueError, TypeError):
                            pass
            
            for key in ('totalEq', 'total_eq'):
                val = info.get(key)
                if val is not None:
                    try:
                        f_val = float(val)
                        if f_val > 0:
                            return f_val
                    except (ValueError, TypeError):
                        pass

        # -------------------------------------------------------------
        # TRƯỜNG HỢP 3: SÀN BINANCE
        # -------------------------------------------------------------
        elif exchange_id == 'binance' and isinstance(info, dict):
            # Binance Futures: tổng ví (marginBalance hoặc totalWalletBalance)
            for key in ('totalMarginBalance', 'totalWalletBalance'):
                val = info.get(key)
                if val is not None:
                    try:
                        f_val = float(val)
                        if f_val > 0:
                            return f_val
                    except (ValueError, TypeError):
                        pass
            
            assets = info.get('assets', [])
            if isinstance(assets, list):
                for asset in assets:
                    if isinstance(asset, dict) and asset.get('asset') == 'USDT':
                        for key in ('marginBalance', 'walletBalance'):
                            val = asset.get(key)
                            if val is not None:
                                try:
                                    f_val = float(val)
                                    if f_val > 0:
                                        return f_val
                                except (ValueError, TypeError):
                                    pass

        # -------------------------------------------------------------
        # DỰ PHÒNG TỔNG QUÁT (GENERAL FALLBACK CHO TẤT CẢ CÁC SÀN)
        # -------------------------------------------------------------
        candidates = [
            balance.get('total', {}).get('USDT') if isinstance(balance.get('total'), dict) else None,
            balance.get('free', {}).get('USDT') if isinstance(balance.get('free'), dict) else None,
            balance.get('USDT', {}).get('total') if isinstance(balance.get('USDT'), dict) else None,
            balance.get('USDT', {}).get('free') if isinstance(balance.get('USDT'), dict) else None,
        ]
        for candidate in candidates:
            if candidate is not None:
                try:
                    val = float(candidate)
                    if val > 0:
                        return val
                except (ValueError, TypeError):
                    pass

        # Nỗ lực cuối cùng: bóc bất kỳ key nào chứa số dư USDT từ info
        if isinstance(info, dict):
            for k, v in info.items():
                if 'balance' in k.lower() or 'margin' in k.lower() or 'equity' in k.lower():
                    try:
                        val = float(v)
                        if val > 0:
                            return val
                    except (ValueError, TypeError):
                        pass

        raise ValueError(f'unable to locate USDT balance in {exchange_id.upper()} exchange response')

    def _extract_available_margin(self, balance: Dict[str, Any]) -> float:
        """Trả về margin khả dụng (availEq/free/totalAvailableBalance) — dùng để tính position size.
        Hỗ trợ đa sàn: Binance (Futures), OKX (Unified), Bybit (Unified/Standard)."""
        exchange_id = self.exchange_platform.lower()
        info = balance.get('info', {})

        # 1. THỬ CÁCH PHỔ THÔNG VÀ AN TOÀN NHẤT CỦA CCXT TRƯỚC (Ăn tiền 90% các sàn)
        if isinstance(balance, dict) and 'free' in balance:
            if 'USDT' in balance['free'] and balance['free']['USDT'] is not None:
                margin_val = float(balance['free']['USDT'])
                if margin_val > 0:
                    return margin_val

        # -------------------------------------------------------------
        # TRƯỜNG HỢP 1: SÀN BYBIT
        # -------------------------------------------------------------
        if exchange_id == 'bybit' and isinstance(info, dict):
            # Thử lấy từ Unified Trading Account (UTA) của Bybit trước
            info_list = info.get('result', {}).get('list', [])
            if not info_list:
                info_list = info.get('list', [])
            
            if info_list and isinstance(info_list, list):
                avail = info_list[0].get('totalAvailableBalance')
                if avail is not None:
                    try:
                        val = float(avail)
                        if val > 0:
                            return val
                    except (ValueError, TypeError):
                        pass

        # -------------------------------------------------------------
        # TRƯỜNG HỢP 2: SÀN OKX
        # -------------------------------------------------------------
        elif exchange_id == 'okx' and isinstance(info, dict):
            info_data = info.get('data', [])
            if info_data and isinstance(info_data, list):
                avail = info_data[0].get('availEq')
                if avail is not None:
                    try:
                        val = float(avail)
                        if val > 0:
                            return val
                    except (ValueError, TypeError):
                        pass
            
            avail = info.get('availEq')
            if avail is not None:
                try:
                    val = float(avail)
                    if val > 0:
                        return val
                except (ValueError, TypeError):
                    pass

        # -------------------------------------------------------------
        # TRƯỜNG HỢP 3: SÀN BINANCE
        # -------------------------------------------------------------
        elif exchange_id == 'binance' and isinstance(info, dict):
            assets = info.get('assets', [])
            if isinstance(assets, list):
                for asset in assets:
                    if isinstance(asset, dict) and asset.get('asset') == 'USDT':
                        for key in ('maxWithdrawAmount', 'availableBalance'):
                            val = asset.get(key)
                            if val is not None:
                                try:
                                    f_val = float(val)
                                    if f_val > 0:
                                        return f_val
                                except (ValueError, TypeError):
                                    pass

        # -------------------------------------------------------------
        # DỰ PHÒNG TỔNG QUÁT (GENERAL FALLBACK CHO TẤT CẢ CÁC SÀN)
        # -------------------------------------------------------------
        candidates = [
            balance.get('free', {}).get('USDT') if isinstance(balance.get('free'), dict) else None,
            balance.get('total', {}).get('USDT') if isinstance(balance.get('total'), dict) else None,
            balance.get('USDT', {}).get('free') if isinstance(balance.get('USDT'), dict) else None,
            balance.get('USDT', {}).get('total') if isinstance(balance.get('USDT'), dict) else None,
        ]
        for candidate in candidates:
            if candidate is not None:
                try:
                    val = float(candidate)
                    if val > 0:
                        return val
                except (ValueError, TypeError):
                    pass

        # Nỗ lực cuối cùng: bóc bất kỳ key nào chứa số dư USDT từ info
        if isinstance(info, dict):
            for k, v in info.items():
                if 'balance' in k.lower() or 'margin' in k.lower() or 'equity' in k.lower():
                    try:
                        val = float(v)
                        if val > 0:
                            return val
                    except (ValueError, TypeError):
                        pass

        raise ValueError(f'unable to locate available margin in {exchange_id.upper()} exchange response')

    def _fetch_available_margin_with_retry(self) -> float:
        """Lấy margin khả dụng (availEq) từ OKX/Bybit — dùng riêng để tính qty lệnh mới."""
        for attempt in range(3):
            try:
                balance = self.exchange.fetch_balance(self._fetch_balance_params())
                self._ip_whitelist_warned = False  # Reset on success
                return self._extract_available_margin(balance)
            except ccxt.AuthenticationError as exc:
                error_str = str(exc)
                if '50110' in error_str:
                    # OKX IP whitelist error
                    if not self._ip_whitelist_warned:
                        logger.error(
                            'OKX API error 50110: IP %s không có trong whitelist. '
                            'Vào OKX → API Keys → Sửa key → Thêm IP hoặc bỏ IP restriction. '
                            'Bot chuyển sang dry-run.',
                            error_str.split('IP ')[1].split(' ')[0] if 'IP ' in error_str else '?',
                        )
                        self._ip_whitelist_warned = True
                elif '10010' in error_str or 'PermissionDenied' in error_str:
                    # Bybit IP whitelist error
                    if not self._ip_whitelist_warned:
                        logger.error(
                            'Bybit API error 10010: IP không có trong whitelist. '
                            'Vào Bybit → API Management → Sửa key → Thêm IP hoặc chọn No IP restriction. '
                            'Bot chuyển sang dry-run.'
                        )
                        self._ip_whitelist_warned = True
                else:
                    logger.warning('Authentication failed while fetching available margin: %s', exc)
                
                if self.live_trading_mode:
                    msg = f"CRITICAL: Lỗi xác thực API khi lấy margin khả dụng (AuthenticationError). Dừng bot để bảo vệ tài khoản! Chi tiết: {exc}"
                    logger.error(msg)
                    try:
                        self._send_discord_message('🚨 CRITICAL ERROR - AUTHENTICATION FAILED', msg, 0xFF0000)
                    except Exception:
                        pass
                    os._exit(1)  # Auth error = sai key, dừng hẳn là đúng
                
                self.dry_run = True
                return 5000.0
            except (ccxt.NetworkError, ccxt.RateLimitExceeded) as exc:
                logger.warning('Available margin fetch failed (attempt %d): %s', attempt + 1, exc)
                time.sleep(2 ** attempt)
            except Exception as exc:
                logger.warning('Unexpected error fetching available margin: %s', exc)
                break
        
        if self.live_trading_mode:
            msg = "⚠️ Không thể lấy margin khả dụng sau 3 lần thử (lỗi mạng tạm thời). Bỏ qua lệnh này, retry sau."
            logger.warning(msg)
            try:
                self._send_discord_message('⚠️ Cảnh báo - Margin Fetch Failed', msg, 0xFFA500)
            except Exception:
                pass
            raise RuntimeError('margin fetch failed after 3 attempts — trade skipped')
            
        if self.dry_run:
            return 5000.0
        raise RuntimeError('failed to fetch available margin after 3 attempts')

    def _fetch_ticker_with_retry(self, symbol: str) -> Dict[str, Any]:
        for attempt in range(3):
            try:
                return self.exchange.fetch_ticker(symbol)
            except (ccxt.NetworkError, ccxt.RateLimitExceeded) as exc:
                logger.warning('Ticker fetch failed for %s (attempt %s): %s', symbol, attempt + 1, exc)
                time.sleep(2 ** attempt)
        raise RuntimeError(f'failed to fetch ticker for {symbol}')

    def _fetch_market_data_ticker_with_retry(self, symbol: str) -> Dict[str, Any]:
        for attempt in range(3):
            try:
                return self.market_data_exchange.fetch_ticker(symbol)
            except (ccxt.NetworkError, ccxt.RateLimitExceeded) as exc:
                logger.warning('Market-data ticker fetch failed for %s (attempt %s): %s', symbol, attempt + 1, exc)
                time.sleep(2 ** attempt)
        raise RuntimeError(f'failed to fetch market-data ticker for {symbol}')

    def _create_order_with_retry(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float],
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        params = params or {}
        # Đảm bảo order_type luôn là 'limit' hoặc 'market' viết thường
        if not order_type or str(order_type).lower() not in ['limit', 'market']:
            order_type_str = str(order_type).lower() if order_type else 'limit'
            if order_type_str in ['limit', 'market']:
                order_type = order_type_str
            else:
                logger.warning("Invalid order_type '%s' normalized to 'limit'", order_type)
                order_type = 'limit'
        else:
            order_type = str(order_type).lower()

        # Popping conflicting params
        params.pop('ordType', None)
        params.pop('order_type', None)

        retry_unsafe = os.getenv('ORDER_CREATE_RETRY_ON_NETWORK_ERROR', 'false').lower() in {'1', 'true', 'yes', 'on'}
        for attempt in range(3):
            try:
                return self.exchange.create_order(symbol, order_type, side, amount, price, params)
            except (ccxt.NetworkError, ccxt.RateLimitExceeded) as exc:
                # A timeout/rate-limit response can arrive after the exchange has
                # accepted the order. Retrying blindly can therefore double an
                # entry, which is worse than skipping one signal in live trading.
                if not retry_unsafe:
                    self._record_exchange_event(symbol, 'order_submission_uncertain', {
                        'type': order_type,
                        'side': side,
                        'amount': amount,
                        'price': price,
                        'error': str(exc),
                    })
                    raise RuntimeError(
                        f'order submission uncertain for {symbol}; not retrying to avoid a duplicate order: {exc}'
                    ) from exc
                logger.warning('Order creation failed for %s (attempt %s): %s', symbol, attempt + 1, exc)
                time.sleep(2 ** attempt)
        raise RuntimeError(f'failed to place order for {symbol}')

    def _cancel_order_with_retry(self, order_id: str, symbol: str) -> None:
        for attempt in range(3):
            try:
                self.exchange.cancel_order(order_id, symbol)
                return
            except (ccxt.NetworkError, ccxt.RateLimitExceeded) as exc:
                logger.warning('Order cancel failed for %s (attempt %s): %s', order_id, attempt + 1, exc)
                time.sleep(2 ** attempt)
            except ccxt.OrderNotFound:
                return
        logger.warning('Unable to cancel order %s for %s after retries', order_id, symbol)

    def _cancel_protective_order(self, order_id: str, symbol: str) -> None:
        """Cancel a SL/TP order. For OKX uses the algo cancel endpoint."""
        if not order_id:
            return
        if self.exchange_platform == 'okx':
            inst_id = symbol.replace('/', '-').replace(':USDT', '-SWAP')
            try:
                # Dùng hàm chuẩn của CCXT để xử lý JSON đúng định dạng thay vì dùng API ẩn
                if hasattr(self.exchange, 'cancel_algo_order'):
                    self.exchange.cancel_algo_order(order_id, symbol)
                    logger.info('OKX algo order cancelled natively: algoId=%s', order_id)
                else:
                    self.exchange.privatePostTradeCancelAlgos([{'algoId': order_id, 'instId': inst_id}])
                    logger.info('OKX algo order cancelled via implicit API: algoId=%s', order_id)
            except Exception as exc:
                logger.warning('Unable to cancel OKX algo order %s: %s', order_id, exc)
        else:
            self._cancel_order_with_retry(order_id, symbol)

    def _create_protective_order(self, symbol: str, side: str, quantity: float, stop_price: float, order_type: str) -> Optional[Dict[str, Any]]:
        """Place a SL or TP trigger order.

        For OKX Swap/Futures we MUST use the native /trade/order-algo endpoint
        (privatePostTradeOrderAlgo). The standard create_order path hits
        /trade/order which does NOT support conditional trigger orders on Swap
        accounts and returns error 51149 (timeout) or 51317 (margin mismatch).

        For other exchanges (Binance etc.) we keep the CCXT unified path.
        """
        if self.disable_protective_orders:
            logger.warning('DISABLE_PROTECTIVE_ORDERS=true, bỏ qua lệnh bảo vệ %s cho %s', order_type, symbol)
            return None

        # ── OKX native algo order ─────────────────────────────────────────────
        if self.exchange_platform == 'okx':
            # Convert CCXT symbol "BTC/USDT:USDT" → OKX instId "BTC-USDT-SWAP"
            inst_id = symbol.replace('/', '-').replace(':USDT', '-SWAP')
            is_sl = order_type == 'STOP_MARKET'

            # OKX SWAP dùng đơn vị CONTRACTS (không phải BTC).
            # 1 BTC-USDT-SWAP contract = contractSize BTC (thường 0.01 BTC).
            # Phải chia quantity cho contractSize → lấy số contracts nguyên >= 1.
            algo_sz_contracts: int = 1  # fallback an toàn: tối thiểu 1 contract
            try:
                market = self.exchange.market(symbol)
                contract_size = float(market.get('contractSize') or 0.01)
                raw_contracts = quantity / contract_size
                algo_sz_contracts = max(1, int(raw_contracts))  # luôn >= 1 contract
                logger.info(
                    'OKX algo sz: qty=%.8f contractSize=%.4f → %d contract(s)',
                    quantity, contract_size, algo_sz_contracts,
                )
            except Exception as exc:
                logger.warning('Không tính được contractSize, dùng sz=1: %s', exc)

            # OKX isolated margin yêu cầu trường 'ccy' (settlement currency).
            # Với USDT-margined SWAP (BTC/USDT:USDT), ccy = 'USDT'.
            # Với cross margin, ccy không cần thiết nhưng thêm vào cũng không sao.
            # Tách settle currency từ symbol: 'BTC/USDT:USDT' → 'USDT'
            try:
                settle_ccy = symbol.split(':')[-1] if ':' in symbol else symbol.split('/')[-1].split(':')[0]
            except Exception:
                settle_ccy = 'USDT'

            algo_params: Dict[str, Any] = {
                'instId':  inst_id,
                'tdMode':  self.okx_td_mode,   # 'cross' hoặc 'isolated'
                'ccy':     settle_ccy,          # Bắt buộc với isolated margin (OKX error 50014)
                'side':    side,
                'ordType': 'conditional',
                'sz':      str(algo_sz_contracts),
            }
            if is_sl:
                algo_params['slTriggerPx']     = str(stop_price)
                algo_params['slOrdPx']         = '-1'       # -1 = market khi trigger
                algo_params['slTriggerPxType'] = 'last'
            else:
                algo_params['tpTriggerPx']     = str(stop_price)
                algo_params['tpOrdPx']         = '-1'
                algo_params['tpTriggerPxType'] = 'last'

            try:
                resp = self.exchange.privatePostTradeOrderAlgo(algo_params)
                algo_id = resp.get('data', [{}])[0].get('algoId', '')
                logger.info(
                    'OKX algo order placed (%s): algoId=%s  triggerPx=%.4f sz=%d contract(s)',
                    order_type, algo_id, stop_price, algo_sz_contracts,
                )
                # Trả về dict tương thích với phần còn lại của code (dùng 'id')
                return {'id': algo_id, 'algoId': algo_id}
            except ccxt.ExchangeError as exc:
                logger.error(
                    '🚨 SAFETY ABORT: OKX từ chối algo order %s (sz=%d contracts). '
                    'Ném lỗi lên caller để đóng entry. Chi tiết: %s',
                    order_type, algo_sz_contracts, exc,
                )
                raise

        # ── Non-OKX (Binance…): CCXT unified trigger order ───────────────────
        params = self._order_mode_params(reduce_only=True)
        params['triggerPrice'] = float(stop_price)
        try:
            return self._create_order_with_retry(symbol, 'market', side, quantity, None, params)
        except ccxt.ExchangeError:
            raise

    def _extract_fill_price(self, order: Dict[str, Any], fallback_price: float) -> float:
        average = order.get('average')
        if average:
            return float(average)
        filled_price = order.get('price')
        if filled_price:
            return float(filled_price)
        info = order.get('info', {})
        for key in ('avgPrice', 'price'):
            if key in info and info[key]:
                try:
                    return float(info[key])
                except (TypeError, ValueError):
                    continue
        return fallback_price

    def _apply_amount_precision(self, symbol: str, amount: float) -> float:
        """Chuyển đổi số lượng (coin) sang contract-aligned qty cho OKX Swap/Futures.

        Với các sàn dùng contractSize (ví dụ OKX BTC-USDT-SWAP: 1 contract = 0.01 BTC):
        1. Tính số contracts cần thiết (làm tròn lên, tối thiểu 1).
        2. Quy đổi ngược từ contracts → coin qty.
        3. Áp dụng amount_to_precision của sàn để làm tròn tick cuối.

        Điều này ngăn lỗi OKX 51131 (The order quantity is less than the minimum
        order quantity of the contract).
        """
        try:
            market = self.exchange.market(symbol)
            contract_size = float(market.get('contractSize') or 0)
            if contract_size > 0:
                # Tính số nguyên contracts, ép tối thiểu là 1
                contracts = math.floor(amount / contract_size)
                if contracts < 1:
                    logger.warning(
                        'Qty %.8f < 1 contract (contractSize=%.8f) for %s — lifting to 1 contract',
                        amount, contract_size, symbol,
                    )
                    contracts = 1
                amount = contracts * contract_size
            return float(self.exchange.amount_to_precision(symbol, amount))
        except Exception as exc:
            logger.warning('Failed to apply amount precision for %s: %s', symbol, exc)
            return amount

    def _validate_quantity(self, market: Dict[str, Any], symbol: str, quantity: float) -> None:
        """Kiểm tra quantity hợp lệ theo giới hạn của sàn.

        Đối với OKX Swap/Futures, limits.amount.min được tính bằng contracts.
        Hàm này kiểm tra sau khi _apply_amount_precision đã quy đổi về contract-aligned qty.
        """
        minimum = market.get('limits', {}).get('amount', {}).get('min')
        if minimum is not None and quantity < float(minimum):
            raise ValueError(
                f'quantity {quantity:.8f} for {symbol} below market minimum {minimum} (contracts)'
            )
        if quantity <= 0:
            raise ValueError(f'invalid quantity for {symbol}')

    def _record_exchange_event(self, symbol: str, event_type: str, payload: Any) -> None:
        try:
            event = {
                'event_type': event_type,
                'symbol': symbol,
                'stored_at': int(time.time()),
                'payload': payload,
            }
            self.redis.lpush('execution_events', json.dumps(event, default=str, separators=(',', ':')))
            self.redis.ltrim('execution_events', 0, 199)
        except RedisError as exc:
            logger.warning('Unable to write execution event: %s', exc)


def main() -> None:
    executor = TradingExecutor()
    executor.run()


if __name__ == '__main__':
    main()
