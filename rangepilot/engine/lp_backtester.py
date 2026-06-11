"""RangePilot LP backtest engine.

Simulates a concentrated-liquidity market-making policy over an OHLCV path.

No-lookahead discipline
-----------------------
* All decisions at bar *i* use information up to and including bar *i*'s close.
* Fees for bar *i* accrue only to a position that was already open when bar
  *i* started (i.e. opened at the close of an earlier bar).
* Regime series are rolling/backward-looking only (see signals.regime).

Fee model (assumptions A1–A4, all disclosed in the spec)
--------------------------------------------------------
fee_bar = volume_quote_bar * fee_rate * share * overlap_fraction
  share            = position_value / (position_value + active_liquidity_quote),
                     capped at `share_cap`  (A1, ±50% sensitivity-tested)
  overlap_fraction = |[low,high] ∩ [Pa,Pb]| / |[low,high]|              (A3)
Costs: entry swap cost, per-rebalance cost rate + fixed gas (A2).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import FEE_TIERS, DEFAULTS, BacktestDefaults
from .amm_math import (Position, liquidity_for_capital, geometric_range,
                       width_from_vol, aligned_range)
from .strategies import StrategyParams
from ..signals.regime import RegimeFrame, LocalComputedSignals


@dataclass
class RebalanceEvent:
    ts: object
    price: float
    reason: str            # "range_exit" | "edge_band" | "pause" | "resume"
    old_range: tuple | None
    new_range: tuple | None
    cost_quote: float


@dataclass
class BacktestResult:
    close: pd.Series
    equity: pd.Series
    hodl_5050: pd.Series
    hodl_quote: pd.Series
    full_range_lp: pd.Series
    fees_cum: pd.Series
    costs_cum: pd.Series
    in_position: pd.Series
    range_lower: pd.Series
    range_upper: pd.Series
    events: list[RebalanceEvent]
    metrics: dict
    params: StrategyParams
    config: dict
    regime_source: str

    def summary(self) -> dict:
        return dict(self.metrics)


REQUIRED_COLS = ("open", "high", "low", "close", "volume_quote")


def _validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"OHLCV missing columns: {missing}")
    df = df.copy()
    df = df.sort_index()
    if df["close"].le(0).any():
        raise ValueError("non-positive close prices")
    return df


def run_backtest(ohlcv: pd.DataFrame,
                 params: StrategyParams,
                 capital_quote: float,
                 fee_tier: int = 2500,
                 cfg: BacktestDefaults = DEFAULTS,
                 regimes: RegimeFrame | None = None,
                 warmup_bars: int | None = None) -> BacktestResult:
    df = _validate_ohlcv(ohlcv)
    if fee_tier not in FEE_TIERS:
        raise ValueError(f"unknown fee tier {fee_tier}")
    fee_rate = FEE_TIERS[fee_tier]["rate"]
    spacing = FEE_TIERS[fee_tier]["tick_spacing"]

    if regimes is None:
        regimes = LocalComputedSignals(bar_hours=cfg.bar_interval_hours).compute(df)
    if warmup_bars is None:
        warmup_bars = min(len(df) // 5, 24 * 14)

    n = len(df)
    idx = df.index
    close = df["close"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    vol_q = df["volume_quote"].to_numpy(float)
    sigma = regimes.sigma_ann.reindex(df.index).to_numpy(float)
    regime = regimes.regime.reindex(df.index).astype(str).to_numpy()
    stress = regimes.trend_stress.reindex(df.index).fillna(False).to_numpy(bool)

    cash = capital_quote
    pos: Position | None = None
    pos_share = 0.0
    paused = False
    last_rebalance_i = -10**9
    rebalances_today: dict = {}
    events: list[RebalanceEvent] = []

    equity = np.full(n, np.nan)
    fees_cum = np.zeros(n)
    costs_cum = np.zeros(n)
    in_pos = np.zeros(n, dtype=bool)
    rlo = np.full(n, np.nan)
    rhi = np.full(n, np.nan)

    fees_total = 0.0
    costs_total = 0.0
    overlap_sum = 0.0
    overlap_bars = 0
    il_vs_hodl_price = 0.0  # Σ per-position (exit LP value − exit HODL value)

    # benchmarks (frictionless marks, same start bar)
    bench_started = False
    h50_a0 = h50_a1 = 0.0
    fr_pos: Position | None = None
    fr_share = 0.0
    fr_fees = 0.0
    hodl5050 = np.full(n, np.nan)
    hodlq = np.full(n, np.nan)
    fullrange = np.full(n, np.nan)

    def _share_for(value_quote: float) -> float:
        s = value_quote / (value_quote + max(cfg.active_liquidity_quote, 1e-9))
        return float(min(s, cfg.share_cap))

    def _width(i: int) -> float:
        w = width_from_vol(sigma[i], params.horizon_hours, params.k_sigma)
        mult = params.regime_width_mult.get(regime[i], 1.0)
        return float(min(max(w * mult, 0.004), 0.75))

    def _open_position(i: int, reason: str) -> None:
        nonlocal cash, pos, pos_share, costs_total, last_rebalance_i
        entry_cost = cash * cfg.entry_cost_rate
        deploy = cash - entry_cost
        if deploy <= 0:
            return
        w = _width(i)
        pa_raw, pb_raw = geometric_range(close[i], w)
        _, _, pa, pb = aligned_range(pa_raw, pb_raw, spacing)
        new_pos = liquidity_for_capital(deploy, close[i], pa, pb)
        cash = 0.0
        costs_total += entry_cost
        pos = new_pos
        pos_share = _share_for(deploy)
        last_rebalance_i = i
        events.append(RebalanceEvent(idx[i], close[i], reason, None, (pa, pb), entry_cost))

    def _close_position(i: int, reason: str, *, rebalance_cost: bool) -> None:
        nonlocal cash, pos, costs_total, il_vs_hodl_price
        assert pos is not None
        value = pos.value(close[i])
        il_vs_hodl_price += pos.il_vs_hodl(close[i])
        cost = (value * cfg.rebalance_cost_rate + cfg.gas_usd_per_rebalance) if rebalance_cost else 0.0
        cost = min(cost, value)
        cash += value - cost
        costs_total += cost
        events.append(RebalanceEvent(idx[i], close[i], reason, (pos.pa, pos.pb), None, cost))
        pos = None

    for i in range(n):
        ts = idx[i]
        day = pd.Timestamp(ts).date() if not isinstance(ts, (int, np.integer)) else ts // 24

        # 1) accrue fees for the bar on a pre-existing position
        if pos is not None:
            ovl = pos.range_overlap_fraction(low[i], high[i])
            overlap_sum += ovl
            overlap_bars += 1
            fee = max(vol_q[i] - cfg.min_bar_volume_quote, 0.0) * fee_rate * pos_share * ovl
            fees_total += fee
            cash += fee
        if fr_pos is not None:
            fr_fees += max(vol_q[i], 0.0) * fee_rate * fr_share  # always in range

        # 2) decisions at close
        if i >= warmup_bars:
            if not bench_started:
                # start benchmarks frictionless at the same bar strategies may start
                h50_a0 = (capital_quote / 2) / close[i]
                h50_a1 = capital_quote / 2
                fr_pos = liquidity_for_capital(capital_quote, close[i],
                                               close[i] / 100.0, close[i] * 100.0)
                fr_share = _share_for(capital_quote)
                bench_started = True

            want_pause = (params.pause_in_stress and stress[i]) or \
                         (params.pause_in_high_vol and regime[i] == "high")

            if pos is not None and want_pause:
                _close_position(i, "pause", rebalance_cost=True)
                paused = True
            elif pos is None and paused and not want_pause:
                paused = False
                events.append(RebalanceEvent(ts, close[i], "resume", None, None, 0.0))

            if pos is not None and not want_pause:
                trigger = False
                if params.rebalance_trigger == "range_exit":
                    trigger = not pos.in_range(close[i])
                elif params.rebalance_trigger == "edge_band":
                    band = params.edge_band * (pos.pb - pos.pa)
                    trigger = close[i] <= pos.pa + band or close[i] >= pos.pb - band
                cool_ok = (i - last_rebalance_i) >= params.cooldown_bars
                day_ct = rebalances_today.get(day, 0)
                if trigger and cool_ok and day_ct < params.max_rebalances_per_day:
                    _close_position(i, params.rebalance_trigger, rebalance_cost=True)
                    _open_position(i, "reopen")
                    rebalances_today[day] = day_ct + 1

            if pos is None and not paused and not want_pause and cash > 0:
                _open_position(i, "initial" if not events else "reopen")

        # 3) mark equity
        pv = pos.value(close[i]) if pos is not None else 0.0
        equity[i] = cash + pv
        fees_cum[i] = fees_total
        costs_cum[i] = costs_total
        in_pos[i] = pos is not None
        if pos is not None:
            rlo[i], rhi[i] = pos.pa, pos.pb
        if bench_started:
            hodl5050[i] = h50_a0 * close[i] + h50_a1
            hodlq[i] = capital_quote
            fullrange[i] = fr_pos.value(close[i]) + fr_fees  # type: ignore[union-attr]

    # mark open position's IL at the end (consistent decomposition)
    if pos is not None:
        il_vs_hodl_price += pos.il_vs_hodl(close[-1])

    eq = pd.Series(equity, index=idx).ffill()
    metrics = _metrics(eq, pd.Series(hodl5050, index=idx),
                       fees_total, costs_total, il_vs_hodl_price,
                       overlap_sum, overlap_bars,
                       len([e for e in events if e.new_range and e.reason != "initial"]),
                       capital_quote, cfg, warmup_bars)

    return BacktestResult(
        close=pd.Series(close, index=idx),
        equity=eq,
        hodl_5050=pd.Series(hodl5050, index=idx),
        hodl_quote=pd.Series(hodlq, index=idx),
        full_range_lp=pd.Series(fullrange, index=idx),
        fees_cum=pd.Series(fees_cum, index=idx),
        costs_cum=pd.Series(costs_cum, index=idx),
        in_position=pd.Series(in_pos, index=idx),
        range_lower=pd.Series(rlo, index=idx),
        range_upper=pd.Series(rhi, index=idx),
        events=events,
        metrics=metrics,
        params=params,
        config={"fee_tier": fee_tier, "capital_quote": capital_quote,
                **{k: getattr(cfg, k) for k in vars(cfg)}},
        regime_source=regimes.source,
    )


def _metrics(eq: pd.Series, hodl: pd.Series, fees: float, costs: float,
             il_price: float, ovl_sum: float, ovl_bars: int, n_rebal: int,
             capital: float, cfg: BacktestDefaults, warmup: int) -> dict:
    eq_v = eq.dropna()
    start_v = float(eq_v.iloc[warmup] if len(eq_v) > warmup else eq_v.iloc[0])
    end_v = float(eq_v.iloc[-1])
    n_bars = max(len(eq_v) - warmup, 1)
    hours = n_bars * cfg.bar_interval_hours
    years = hours / cfg.annualization_hours
    net_ret = end_v / capital - 1.0
    apr = net_ret / years if years > 0 else float("nan")

    rets = eq_v.iloc[warmup:].pct_change().dropna()
    bars_per_day = int(24 / cfg.bar_interval_hours) or 1
    daily = (1 + rets).groupby(np.arange(len(rets)) // bars_per_day).prod() - 1
    sharpe = float(daily.mean() / daily.std() * np.sqrt(365)) if len(daily) > 2 and daily.std() > 0 else float("nan")

    roll_max = eq_v.cummax()
    max_dd = float(((eq_v - roll_max) / roll_max).min())

    hodl_v = hodl.dropna()
    edge_vs_hodl = (end_v - float(hodl_v.iloc[-1])) / capital if len(hodl_v) else float("nan")

    return {
        "net_return": round(net_ret, 6),
        "apr": round(apr, 6),
        "sharpe_daily_ann": round(sharpe, 4) if sharpe == sharpe else None,
        "max_drawdown": round(max_dd, 6),
        "fees_total_quote": round(fees, 4),
        "fee_apr": round((fees / capital) / years, 6) if years > 0 else None,
        "costs_total_quote": round(costs, 4),
        "il_vs_hodl_price_quote": round(il_price, 4),
        "edge_vs_hodl_5050": round(edge_vs_hodl, 6) if edge_vs_hodl == edge_vs_hodl else None,
        "time_in_range": round(ovl_sum / ovl_bars, 4) if ovl_bars else None,
        "n_rebalances": int(n_rebal),
        "bars": int(n_bars),
        "years": round(years, 4),
    }
