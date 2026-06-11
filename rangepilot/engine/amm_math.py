"""Concentrated-liquidity (Uniswap V3 / PancakeSwap V3) position math.

Conventions
-----------
* token0 = base asset, token1 = quote asset.
* price P = quote per base (token1 per token0).
* A position over [Pa, Pb] with liquidity L holds, at spot P:
    s  = sqrt(clamp(P, Pa, Pb)),  sa = sqrt(Pa),  sb = sqrt(Pb)
    amount0 = L * (sb - s) / (s * sb)
    amount1 = L * (s - sa)
* Position value (in quote) V(P) = amount0(P) * P + amount1(P).

All formulas follow the Uniswap V3 whitepaper; PancakeSwap V3 is a fork with
identical math (different fee tiers / tick spacings, see config.FEE_TIERS).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

TICK_BASE = 1.0001


# -- tick <-> price ----------------------------------------------------------

def price_to_tick(price: float) -> int:
    if price <= 0:
        raise ValueError("price must be > 0")
    return int(math.floor(math.log(price) / math.log(TICK_BASE)))


def tick_to_price(tick: int) -> float:
    return TICK_BASE ** tick


def align_tick(tick: int, spacing: int, *, round_up: bool) -> int:
    """Snap a raw tick to the fee tier's tick spacing grid."""
    if spacing <= 0:
        raise ValueError("spacing must be > 0")
    q = tick / spacing
    snapped = math.ceil(q) if round_up else math.floor(q)
    return int(snapped * spacing)


def aligned_range(pa: float, pb: float, spacing: int) -> tuple[int, int, float, float]:
    """Return (tick_lower, tick_upper, Pa_aligned, Pb_aligned) on the grid.

    Lower tick is rounded down, upper tick rounded up, so the aligned range
    always contains the requested one. Guarantees tick_lower < tick_upper.
    """
    tl = align_tick(price_to_tick(pa), spacing, round_up=False)
    tu = align_tick(price_to_tick(pb), spacing, round_up=True)
    if tu <= tl:
        tu = tl + spacing
    return tl, tu, tick_to_price(tl), tick_to_price(tu)


# -- liquidity / amounts / value ---------------------------------------------

def _sqrts(p: float, pa: float, pb: float) -> tuple[float, float, float]:
    if not (0 < pa < pb):
        raise ValueError("require 0 < Pa < Pb")
    s = math.sqrt(min(max(p, pa), pb))
    return s, math.sqrt(pa), math.sqrt(pb)


def unit_amounts(p: float, pa: float, pb: float) -> tuple[float, float]:
    """(amount0, amount1) held per unit of liquidity L at spot p."""
    s, sa, sb = _sqrts(p, pa, pb)
    amount0 = (sb - s) / (s * sb)
    amount1 = s - sa
    return amount0, amount1


def liquidity_for_capital(capital_quote: float, p0: float, pa: float, pb: float) -> "Position":
    """Size a position: deploy `capital_quote` (denominated in token1) at spot p0.

    Returns a Position with L chosen so that entry value == capital_quote.
    """
    if capital_quote <= 0:
        raise ValueError("capital must be > 0")
    u0, u1 = unit_amounts(p0, pa, pb)
    unit_value = u0 * p0 + u1
    if unit_value <= 0:
        raise ValueError("degenerate range")
    L = capital_quote / unit_value
    return Position(L=L, pa=pa, pb=pb, entry_price=p0,
                    entry_amount0=L * u0, entry_amount1=L * u1)


@dataclass
class Position:
    L: float
    pa: float
    pb: float
    entry_price: float
    entry_amount0: float
    entry_amount1: float

    # -- state queries --
    def amounts(self, p: float) -> tuple[float, float]:
        u0, u1 = unit_amounts(p, self.pa, self.pb)
        return self.L * u0, self.L * u1

    def value(self, p: float) -> float:
        a0, a1 = self.amounts(p)
        return a0 * p + a1

    def hodl_value(self, p: float) -> float:
        """Value of just holding the entry token amounts (no LP)."""
        return self.entry_amount0 * p + self.entry_amount1

    def il_vs_hodl(self, p: float) -> float:
        """Impermanent loss vs holding entry amounts (negative = loss)."""
        return self.value(p) - self.hodl_value(p)

    def in_range(self, p: float) -> bool:
        return self.pa <= p <= self.pb

    def range_overlap_fraction(self, low: float, high: float) -> float:
        """Fraction of the candle's [low, high] span inside the range.

        Proxy for in-range time within a bar (assumption A3). If the candle is
        a single point, returns 1.0 when inside the range else 0.0.
        """
        if high < low:
            low, high = high, low
        span = high - low
        if span <= 0:  # degenerate single-point candle
            return 1.0 if self.in_range(low) else 0.0
        lo = max(low, self.pa)
        hi = min(high, self.pb)
        if hi <= lo:
            return 0.0
        return (hi - lo) / span


# -- range construction -------------------------------------------------------

def geometric_range(p0: float, width_ratio: float) -> tuple[float, float]:
    """Symmetric-in-log range: [p0 / r, p0 * r] with r = 1 + width_ratio."""
    if width_ratio <= 0:
        raise ValueError("width_ratio must be > 0")
    r = 1.0 + width_ratio
    return p0 / r, p0 * r


def width_from_vol(sigma_ann: float, horizon_hours: float, k: float,
                   floor: float = 0.005, cap: float = 0.60) -> float:
    """Range half-width as k * sigma over the expected holding horizon.

    sigma_ann : annualized realized vol (e.g. 0.8 = 80%)
    horizon   : expected hours until next rebalance check matters
    """
    sigma_h = sigma_ann * math.sqrt(max(horizon_hours, 1e-9) / (24 * 365))
    return float(min(max(k * sigma_h, floor), cap))
