"""Dependency-free execution semantics shared by research backtests.

The ordering is deliberately conservative for OHLC bars: decisions are filled
at the next bar open, funding is settled for the position held at its timestamp,
and only then may the bar's low trigger the stop.  A high observed in the same
bar can tighten a trailing stop only for the following bar.
"""
from __future__ import annotations

from dataclasses import dataclass


EXECUTION_SEMANTICS = "open_funding_intrabar_v2"
EVENT_ORDER = (
    "delisting_exit",
    "bar_open_rebalance",
    "funding_settlement",
    "intrabar_stop",
    "close_mark",
)


@dataclass(frozen=True)
class LongStopResult:
    fill_price: float | None
    next_peak: float
    effective_stop: float
    reason: str | None


def long_stop_transition(
    row: list[float], position: dict, trail_atr: float,
) -> LongStopResult:
    """Evaluate one long-position bar without inventing an intrabar path."""
    open_price, high, low = map(float, (row[1], row[2], row[3]))
    prior_peak = float(position["peak"])
    effective_stop = max(
        float(position["stop"]),
        prior_peak - trail_atr * float(position["atr"]),
    )
    if open_price <= effective_stop:
        return LongStopResult(open_price, prior_peak, effective_stop, "gap_stop")
    if low <= effective_stop:
        return LongStopResult(effective_stop, prior_peak, effective_stop, "intrabar_stop")
    return LongStopResult(None, max(prior_peak, high), effective_stop, None)


def funding_payment(quantity: float, mark_price: float, funding_rate: float) -> float:
    """Return cash paid by a long; a negative result is funding received."""
    return float(quantity) * float(mark_price) * float(funding_rate)
