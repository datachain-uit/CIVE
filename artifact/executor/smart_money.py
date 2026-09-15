"""
smart_money.py – Smart Money Concepts (SMC) analysis for precision entry.

Implements:
  - find_nearest_fvg()   : Fair Value Gap detection on OHLCV data
  - find_order_block()   : Order Block detection on OHLCV data
  - get_precision_entry(): Returns the best limit price and entry type label
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

logger = logging.getLogger("smart_money")

# OHLCV row: [timestamp, open, high, low, close, volume]
OHLCVRow = Sequence[float]


@dataclass
class EntryZone:
    price: float          # Limit order price to place
    zone_top: float       # Top of the zone
    zone_bottom: float    # Bottom of the zone
    zone_type: str        # "FVG" | "OrderBlock"
    strength: float       # 0.0–1.0 (gap size relative to ATR or block size)
    candle_index: int     # Index of the trigger candle in the OHLCV array


# ---------------------------------------------------------------------------
# ATR helper
# ---------------------------------------------------------------------------

def _calculate_atr(candles: list[OHLCVRow], period: int = 14) -> float:
    """Calculate Average True Range over the last `period` candles."""
    if len(candles) < period + 1:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(candles)):
        high = float(candles[i][2])
        low = float(candles[i][3])
        prev_close = float(candles[i - 1][4])
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs[-period:]) / period


# ---------------------------------------------------------------------------
# Fair Value Gap (FVG)
# ---------------------------------------------------------------------------

def find_nearest_fvg(
    candles: list[OHLCVRow],
    side: str,                    # "buy" → bullish FVG (gap below price), "sell" → bearish FVG
    min_gap_atr_ratio: float = 0.15,  # Gap must be > 15% of ATR to be significant
    lookback: int = 50,
) -> Optional[EntryZone]:
    """
    Identify the nearest unfilled Fair Value Gap.

    Bullish FVG (side='buy'):
        Candle[i-1].high < Candle[i+1].low  →  gap between them = zone to buy into
    Bearish FVG (side='sell'):
        Candle[i-1].low > Candle[i+1].high  →  gap between them = zone to sell into

    Returns the CLOSEST (most recent) FVG to current price.
    """
    if len(candles) < 3:
        return None

    atr = _calculate_atr(candles)
    min_gap = atr * min_gap_atr_ratio if atr > 0 else 0

    current_price = float(candles[-1][4])
    candidates: list[tuple[float, EntryZone]] = []  # (distance, zone)

    scan = candles[-lookback:] if len(candles) > lookback else candles

    for i in range(1, len(scan) - 1):
        prev_high = float(scan[i - 1][2])
        prev_low = float(scan[i - 1][3])
        next_high = float(scan[i + 1][2])
        next_low = float(scan[i + 1][3])

        if side == "buy":
            # Bullish FVG: gap between prev_high and next_low
            if next_low > prev_high:
                gap_size = next_low - prev_high
                if gap_size >= min_gap:
                    mid = (prev_high + next_low) / 2
                    strength = min(gap_size / atr, 1.0) if atr > 0 else 0.5
                    zone = EntryZone(
                        price=mid,
                        zone_top=next_low,
                        zone_bottom=prev_high,
                        zone_type="FVG",
                        strength=strength,
                        candle_index=i,
                    )
                    candidates.append((abs(current_price - mid), zone))

        elif side == "sell":
            # Bearish FVG: gap between next_high and prev_low
            if prev_low > next_high:
                gap_size = prev_low - next_high
                if gap_size >= min_gap:
                    mid = (prev_low + next_high) / 2
                    strength = min(gap_size / atr, 1.0) if atr > 0 else 0.5
                    zone = EntryZone(
                        price=mid,
                        zone_top=prev_low,
                        zone_bottom=next_high,
                        zone_type="FVG",
                        strength=strength,
                        candle_index=i,
                    )
                    candidates.append((abs(current_price - mid), zone))

    if not candidates:
        return None

    # Return the nearest FVG to current price that's still "ahead" (price hasn't blown past it)
    # Sort by distance ascending
    candidates.sort(key=lambda x: x[0])
    for dist, zone in candidates:
        if side == "buy" and zone.price < current_price:
            return zone
        if side == "sell" and zone.price > current_price:
            return zone

    # Fallback: just return nearest regardless of direction
    return candidates[0][1] if candidates else None


# ---------------------------------------------------------------------------
# Order Block
# ---------------------------------------------------------------------------

def find_order_block(
    candles: list[OHLCVRow],
    side: str,                     # "buy" → bullish OB (last bearish candle before up move)
    min_move_atr_ratio: float = 0.5,  # Move after OB must be > 50% of ATR
    lookback: int = 50,
) -> Optional[EntryZone]:
    """
    Identify the nearest Order Block.

    Bullish Order Block (side='buy'):
        Last DOWN candle before a strong UP move.
        Entry: upper wick of that down candle (price returns to refill the block).

    Bearish Order Block (side='sell'):
        Last UP candle before a strong DOWN move.
        Entry: lower wick of that up candle.

    Returns the most recent and nearest OB to current price.
    """
    if len(candles) < 4:
        return None

    atr = _calculate_atr(candles)
    min_move = atr * min_move_atr_ratio if atr > 0 else 0

    current_price = float(candles[-1][4])
    candidates: list[tuple[float, EntryZone]] = []

    scan = candles[-lookback:] if len(candles) > lookback else candles

    for i in range(1, len(scan) - 2):
        o = float(scan[i][1])
        h = float(scan[i][2])
        lo = float(scan[i][3])
        c = float(scan[i][4])

        # Check subsequent move
        next_close = float(scan[i + 1][4])
        move = abs(next_close - c)

        if side == "buy":
            # Bullish OB: bearish candle (close < open) followed by strong bullish move
            is_bearish = c < o
            strong_up = next_close > c and move >= min_move
            if is_bearish and strong_up:
                # Zone: from close to high of the bearish candle
                zone_bottom = lo
                zone_top = h
                entry = (zone_bottom + zone_top) / 2  # Mid of the OB candle
                strength = min(move / atr, 1.0) if atr > 0 else 0.5
                zone = EntryZone(
                    price=entry,
                    zone_top=zone_top,
                    zone_bottom=zone_bottom,
                    zone_type="OrderBlock",
                    strength=strength,
                    candle_index=i,
                )
                candidates.append((abs(current_price - entry), zone))

        elif side == "sell":
            # Bearish OB: bullish candle (close > open) followed by strong bearish move
            is_bullish = c > o
            strong_down = next_close < c and move >= min_move
            if is_bullish and strong_down:
                zone_bottom = lo
                zone_top = h
                entry = (zone_bottom + zone_top) / 2
                strength = min(move / atr, 1.0) if atr > 0 else 0.5
                zone = EntryZone(
                    price=entry,
                    zone_top=zone_top,
                    zone_bottom=zone_bottom,
                    zone_type="OrderBlock",
                    strength=strength,
                    candle_index=i,
                )
                candidates.append((abs(current_price - entry), zone))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])

    # Return the nearest OB that's still "valid" (price hasn't blown through it)
    for dist, zone in candidates:
        if side == "buy" and zone.price < current_price:
            return zone
        if side == "sell" and zone.price > current_price:
            return zone

    return candidates[0][1] if candidates else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_precision_entry(
    candles: list[OHLCVRow],
    side: str,
    current_price: float,
    max_entry_offset_pct: float = 0.005,  # Max 0.5% away from current price
) -> tuple[Optional[float], str]:
    """
    Main entry point: find the best Smart Money entry price.

    Priority: FVG > Order Block > None (use Market)

    Returns:
        (entry_price, entry_type)
        entry_type: "Limit@FVG" | "Limit@OB" | "Market"
    """
    if not candles or len(candles) < 10:
        logger.warning("Insufficient candle data for SMC analysis, using Market entry")
        return None, "Market"

    # Try FVG first (more precise, tighter zones)
    fvg = find_nearest_fvg(candles, side)
    if fvg is not None:
        # Sanity check: don't place limit too far from current price
        offset_pct = abs(fvg.price - current_price) / current_price
        if offset_pct <= max_entry_offset_pct:
            logger.info(
                "FVG found: price=%.4f zone=[%.4f–%.4f] strength=%.2f offset=%.3f%%",
                fvg.price, fvg.zone_bottom, fvg.zone_top, fvg.strength, offset_pct * 100,
            )
            return fvg.price, f"Limit@FVG"
        else:
            logger.info("FVG at %.4f too far (%.2f%% > %.2f%%), trying OB...", fvg.price, offset_pct * 100, max_entry_offset_pct * 100)

    # Try Order Block
    ob = find_order_block(candles, side)
    if ob is not None:
        offset_pct = abs(ob.price - current_price) / current_price
        if offset_pct <= max_entry_offset_pct:
            logger.info(
                "OB found: price=%.4f zone=[%.4f–%.4f] strength=%.2f offset=%.3f%%",
                ob.price, ob.zone_bottom, ob.zone_top, ob.strength, offset_pct * 100,
            )
            return ob.price, f"Limit@OB"
        else:
            logger.info("OB at %.4f too far (%.2f%% > %.2f%%), using Market", ob.price, offset_pct * 100, max_entry_offset_pct * 100)

    # Fallback: Market order
    logger.info("No valid SMC zone near price %.4f, using Market entry", current_price)
    return None, "Market"
