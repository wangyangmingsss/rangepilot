#!/usr/bin/env python3
"""Generate the bundled deterministic sample market (seed-fixed).

Regime-switching GBM: three vol states with a Markov chain, plus one strong
trend leg, volume positively coupled to realized vol — designed to exercise
every code path (rebalances, pauses, all three regimes) in the offline demo
and the test suite.

    python scripts/gen_sample_data.py            # writes data/sample/*.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sample" / "WBNB_USDT_1h_sample.csv"

SEED = 20260611
N_BARS = 24 * 150           # ~5 months hourly
P0 = 600.0                  # WBNB/USDT style level
BASE_VOL_HOURLY = {0: 0.004, 1: 0.009, 2: 0.020}   # low / mid / high
TRANS = np.array([[0.995, 0.004, 0.001],
                  [0.006, 0.990, 0.004],
                  [0.002, 0.010, 0.988]])
TREND_START, TREND_LEN, TREND_DRIFT = int(N_BARS * 0.55), 24 * 12, 0.0016
BASE_VOLUME = 60_000.0      # quote units per hour (~1.4M/day vs 2M active liq — realistic DEX pool regime)


def main() -> int:
    rng = np.random.default_rng(SEED)
    state = 1
    prices = [P0]
    states = []
    for i in range(N_BARS):
        state = rng.choice(3, p=TRANS[state])
        states.append(state)
        drift = TREND_DRIFT if TREND_START <= i < TREND_START + TREND_LEN else 0.0
        sigma = BASE_VOL_HOURLY[state]
        ret = drift + sigma * rng.standard_normal()
        prices.append(prices[-1] * float(np.exp(ret)))
    close = np.array(prices[1:])
    openp = np.array(prices[:-1])
    span = np.abs(rng.standard_normal(N_BARS)) * close * \
        np.array([BASE_VOL_HOURLY[s] for s in states]) * 1.6
    high = np.maximum(openp, close) + span / 2
    low = np.minimum(openp, close) - span / 2
    low = np.maximum(low, close * 0.5)
    vol_state = np.array([BASE_VOL_HOURLY[s] for s in states])
    volume = BASE_VOLUME * (0.5 + 2.5 * vol_state / vol_state.max()) * \
        (0.7 + 0.6 * rng.random(N_BARS))

    ts = pd.date_range("2026-01-01", periods=N_BARS, freq="1h", tz="UTC")
    df = pd.DataFrame({"ts": ts, "open": openp, "high": high, "low": low,
                       "close": close, "volume_quote": volume.round(2)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, float_format="%.6f")
    print(f"wrote {OUT} ({len(df)} bars, seed={SEED}, "
          f"P[{close.min():.1f},{close.max():.1f}])")
    return 0


if __name__ == "__main__":
    sys.exit(main())
