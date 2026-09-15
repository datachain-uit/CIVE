"""Debug script: Phân tích tại sao bot chỉ chọn SHORT."""
import sys
sys.path.insert(0, '.')

from backtester import (
    VibeTradingSignalGenerator, fetch_ohlcv_with_retry, to_candles, build_exchange,
    rsi, macd, closes as get_closes, ema
)

exchange = build_exchange('bybit')
symbol = 'XRP/USDT:USDT'
raw_4h = fetch_ohlcv_with_retry(exchange, symbol, '4h', limit=201)
raw_1d = fetch_ohlcv_with_retry(exchange, symbol, '1d', limit=121)

candles_4h = to_candles(raw_4h[:-1] if len(raw_4h) > 1 else raw_4h)
candles_1d = to_candles(raw_1d[:-1] if len(raw_1d) > 1 else raw_1d)

gen = VibeTradingSignalGenerator(exchange)
snap_1d = gen._snapshot(candles_1d)
snap_4h = gen._snapshot(candles_4h)

c1d = get_closes(candles_1d)
c4h = get_closes(candles_4h)

rsi_1d = rsi(c1d)
rsi_4h = rsi(c4h)
macd_1d, sig_1d, hist_1d = macd(c1d)
macd_4h, sig_4h, hist_4h = macd(c4h)
ema20_1d = ema(c1d, 20)
ema50_1d = ema(c1d, 50)
ema20_4h = ema(c4h, 20)
ema50_4h = ema(c4h, 50)

print('=== DAILY (1D) ===')
print(f'Regime: {snap_1d.regime} | trend_side: {snap_1d.trend_side} | ADX: {snap_1d.adx:.2f} | ATR%: {snap_1d.atr_pct:.4f}')
print(f'EMA20={ema20_1d:.4f}  EMA50={ema50_1d:.4f}  (EMA20>EMA50: {ema20_1d>ema50_1d})')
print(f'RSI={rsi_1d:.2f} | MACD={macd_1d:.6f} | Signal={sig_1d:.6f} | MACD>=Sig: {macd_1d>=sig_1d}')
print()
print('=== INTRADAY (4H) ===')
print(f'Regime: {snap_4h.regime} | trend_side: {snap_4h.trend_side} | ADX: {snap_4h.adx:.2f} | ATR%: {snap_4h.atr_pct:.4f}')
print(f'EMA20={ema20_4h:.4f}  EMA50={ema50_4h:.4f}  (EMA20>EMA50: {ema20_4h>ema50_4h})')
print(f'RSI={rsi_4h:.2f} | MACD={macd_4h:.6f} | Signal={sig_4h:.6f} | MACD>=Sig: {macd_4h>=sig_4h}')
print()

direction = gen._select_direction(candles_1d, candles_4h, snap_1d, snap_4h)
print(f'==> DIRECTION: {direction}')
print()

daily_side = snap_1d.trend_side
intra_side = snap_4h.trend_side

bull_1d = daily_side == 'buy' or (macd_1d >= sig_1d and rsi_1d >= 52)
bull_4h = intra_side == 'buy' or (macd_4h >= sig_4h and rsi_4h >= 52)
bear_1d = daily_side == 'sell' or (macd_1d <= sig_1d and rsi_1d <= 48)
bear_4h = intra_side == 'sell' or (macd_4h <= sig_4h and rsi_4h <= 48)

bullish = bull_1d and bull_4h
bearish = bear_1d and bear_4h

print('=== BULLISH BREAKDOWN ===')
print(f'  1D: trend_side==buy={daily_side == "buy"}  |  MACD>=sig AND rsi>=52={macd_1d >= sig_1d and rsi_1d >= 52}  => bull_1d={bull_1d}')
print(f'  4H: trend_side==buy={intra_side == "buy"}  |  MACD>=sig AND rsi>=52={macd_4h >= sig_4h and rsi_4h >= 52}  => bull_4h={bull_4h}')
print(f'  => BULLISH overall: {bullish}')
print()
print('=== BEARISH BREAKDOWN ===')
print(f'  1D: trend_side==sell={daily_side == "sell"}  |  MACD<=sig AND rsi<=48={macd_1d <= sig_1d and rsi_1d <= 48}  => bear_1d={bear_1d}')
print(f'  4H: trend_side==sell={intra_side == "sell"}  |  MACD<=sig AND rsi<=48={macd_4h <= sig_4h and rsi_4h <= 48}  => bear_4h={bear_4h}')
print(f'  => BEARISH overall: {bearish}')
print()
if bullish and bearish:
    print('  Both true => CONFLICT => returns None (no signal)')
elif bullish:
    print('  => BUY signal')
elif bearish:
    print('  => SELL signal')
else:
    print('  Neither => returns None (no signal)')
