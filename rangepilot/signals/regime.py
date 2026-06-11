"""Regime signal layer — the "decision brain" of every RangePilot strategy.

Two providers behind one interface:

* LocalComputedSignals  — deterministic, computed purely from the OHLCV frame
  (rolling realized vol percentile + trend filter). Used for offline
  reproducibility and as the backtest ground truth.
* CMCHubSignals         — pulls CMC Agent Hub pre-computed indicators / MCP
  tools at generation time and maps them onto the same regime enum.
  [VERIFY-DAY1] exact tool/field names; until verified it degrades to
  LocalComputedSignals and records that degradation in the spec.

Regimes: "low" / "mid" / "high" volatility, plus boolean `trend_stress`
(strong directional move where passive LP bleeds IL fastest).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

REGIMES = ("low", "mid", "high")


@dataclass
class RegimeFrame:
    """Per-bar regime annotations aligned to the OHLCV index."""
    sigma_ann: pd.Series        # rolling annualized realized vol
    vol_pct: pd.Series          # rolling percentile rank of sigma (0..1)
    regime: pd.Series           # "low" | "mid" | "high"
    trend_stress: pd.Series     # bool
    source: str                 # "local" | "cmc-hub" | "cmc-hub-degraded-to-local"


class LocalComputedSignals:
    """Deterministic regime engine from OHLCV only (no network)."""

    def __init__(self, vol_window: int = 72, pct_window: int = 24 * 30,
                 low_q: float = 0.33, high_q: float = 0.66,
                 trend_fast: int = 24, trend_slow: int = 24 * 7,
                 trend_thresh: float = 0.06,
                 bar_hours: float = 1.0):
        self.vol_window = vol_window
        self.pct_window = pct_window
        self.low_q, self.high_q = low_q, high_q
        self.trend_fast, self.trend_slow = trend_fast, trend_slow
        self.trend_thresh = trend_thresh
        self.bar_hours = bar_hours

    def compute(self, ohlcv: pd.DataFrame) -> RegimeFrame:
        close = ohlcv["close"].astype(float)
        rets = np.log(close / close.shift(1))
        bars_per_year = (24 * 365) / self.bar_hours
        sigma_ann = rets.rolling(self.vol_window, min_periods=max(8, self.vol_window // 4)) \
                        .std() * np.sqrt(bars_per_year)
        sigma_ann = sigma_ann.bfill().fillna(0.5)

        def _pct(window: pd.Series) -> float:
            cur = window.iloc[-1]
            return float((window <= cur).mean())

        vol_pct = sigma_ann.rolling(self.pct_window, min_periods=self.vol_window) \
                           .apply(_pct, raw=False)
        vol_pct = vol_pct.fillna(0.5)

        regime = pd.Series(np.where(vol_pct <= self.low_q, "low",
                            np.where(vol_pct >= self.high_q, "high", "mid")),
                           index=ohlcv.index)

        ema_f = close.ewm(span=self.trend_fast, adjust=False).mean()
        ema_s = close.ewm(span=self.trend_slow, adjust=False).mean()
        trend_stress = ((ema_f / ema_s - 1.0).abs() >= self.trend_thresh)

        return RegimeFrame(sigma_ann=sigma_ann, vol_pct=vol_pct, regime=regime,
                           trend_stress=trend_stress, source="local")


class CMCHubSignals:
    """CMC Agent Hub pre-computed indicators -> RangePilot regime mapping.

    Generation-time only (not for historical backtests, which always use the
    Local engine on point-in-time OHLCV to avoid lookahead). On any failure
    this provider degrades to LocalComputedSignals and the degradation is
    written into the spec's `data_lineage` (honest-disclosure discipline).
    """

    def __init__(self, client=None):
        # client: rangepilot.data.cmc_client.CMCClient (kept optional so the
        # module imports clean offline)
        self.client = client
        self._fallback = LocalComputedSignals()

    def compute(self, ohlcv: pd.DataFrame) -> RegimeFrame:
        live = None
        if self.client is not None:
            try:
                live = self.client.fetch_hub_indicators()  # [VERIFY-DAY1]
            except Exception:
                live = None
        base = self._fallback.compute(ohlcv)
        if not live:
            return RegimeFrame(**{**base.__dict__, "source": "cmc-hub-degraded-to-local"})
        # Map whatever regime/stress fields the Hub exposes onto the final bar.
        regime = base.regime.copy()
        stress = base.trend_stress.copy()
        hub_regime = str(live.get("market_regime", "")).lower()
        if hub_regime in REGIMES:
            regime.iloc[-1] = hub_regime
        if "risk_flag" in live:
            stress.iloc[-1] = bool(live["risk_flag"]) or bool(stress.iloc[-1])
        return RegimeFrame(sigma_ann=base.sigma_ann, vol_pct=base.vol_pct,
                           regime=regime, trend_stress=stress, source="cmc-hub")
