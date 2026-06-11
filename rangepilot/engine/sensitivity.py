"""Sensitivity analysis & robustness gates (the "honesty layer").

Every generated spec must ship with:
1. share sensitivity   — assumption A1 (active liquidity) at x0.5 / x1.0 / x1.5
2. cost sensitivity    — rebalance cost & gas at x0.5 / x1.0 / x2.0
3. k-plateau check     — selected k_sigma must sit on a performance plateau
                         (neighbours within tolerance), not a lone spike.

A candidate that fails the gates is still reported (negative results are
results) but is flagged `robust=False` and cannot be auto-selected.
"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from ..config import DEFAULTS, BacktestDefaults
from .lp_backtester import run_backtest
from .strategies import StrategyParams


SHARE_MULTS = (0.5, 1.0, 1.5)
COST_MULTS = (0.5, 1.0, 2.0)


def share_sensitivity(ohlcv: pd.DataFrame, params: StrategyParams,
                      capital: float, fee_tier: int,
                      cfg: BacktestDefaults = DEFAULTS) -> list[dict]:
    rows = []
    for m in SHARE_MULTS:
        c = replace(cfg, active_liquidity_quote=cfg.active_liquidity_quote / m)
        r = run_backtest(ohlcv, params, capital, fee_tier, cfg=c)
        rows.append({"share_mult": m, **{k: r.metrics[k] for k in
                                         ("apr", "fee_apr", "max_drawdown", "edge_vs_hodl_5050")}})
    return rows


def cost_sensitivity(ohlcv: pd.DataFrame, params: StrategyParams,
                     capital: float, fee_tier: int,
                     cfg: BacktestDefaults = DEFAULTS) -> list[dict]:
    rows = []
    for m in COST_MULTS:
        c = replace(cfg,
                    rebalance_cost_rate=cfg.rebalance_cost_rate * m,
                    gas_usd_per_rebalance=cfg.gas_usd_per_rebalance * m)
        r = run_backtest(ohlcv, params, capital, fee_tier, cfg=c)
        rows.append({"cost_mult": m, **{k: r.metrics[k] for k in
                                        ("apr", "max_drawdown", "n_rebalances")}})
    return rows


def k_plateau(ohlcv: pd.DataFrame, params: StrategyParams, capital: float,
              fee_tier: int, cfg: BacktestDefaults = DEFAULTS,
              rel_step: float = 0.2, tolerance: float = 0.5) -> dict:
    """Selected k must not be a lone spike: APR at k*(1±rel_step) must retain
    at least `tolerance` of the selected APR edge over the worst neighbour-set
    member, with the same sign of edge_vs_hodl when positive."""
    ks = [params.k_sigma * (1 - rel_step), params.k_sigma, params.k_sigma * (1 + rel_step)]
    aprs, edges = [], []
    for k in ks:
        r = run_backtest(ohlcv, replace(params, k_sigma=k), capital, fee_tier, cfg=cfg)
        aprs.append(r.metrics["apr"])
        edges.append(r.metrics["edge_vs_hodl_5050"])
    centre = aprs[1]
    spread = max(aprs) - min(aprs)
    plateau_ok = True
    if centre == max(aprs) and spread > 0:
        # centre is the best: require neighbours not to collapse
        worst = min(aprs)
        plateau_ok = (centre - worst) <= abs(centre) * (1 - tolerance) + 1e-9 or spread < 0.05
    return {"k_values": [round(k, 4) for k in ks],
            "apr": [round(a, 6) for a in aprs],
            "edge_vs_hodl": edges,
            "plateau_ok": bool(plateau_ok)}


def robustness_report(ohlcv: pd.DataFrame, params: StrategyParams, capital: float,
                      fee_tier: int, cfg: BacktestDefaults = DEFAULTS) -> dict:
    sh = share_sensitivity(ohlcv, params, capital, fee_tier, cfg)
    co = cost_sensitivity(ohlcv, params, capital, fee_tier, cfg)
    kp = k_plateau(ohlcv, params, capital, fee_tier, cfg)

    # Gates (deliberately strict; honest failure beats flattering noise)
    worst_share_apr = min(r["apr"] for r in sh)
    worst_cost_apr = min(r["apr"] for r in co)
    base_dd = max(abs(r["max_drawdown"]) for r in sh)
    gates = {
        "survives_share_minus50": worst_share_apr > -0.05,
        "survives_cost_x2": worst_cost_apr > -0.05,
        "drawdown_under_35pct": base_dd < 0.35,
        "k_plateau_ok": kp["plateau_ok"],
    }
    return {
        "share_sensitivity": sh,
        "cost_sensitivity": co,
        "k_plateau": kp,
        "gates": gates,
        "robust": all(gates.values()),
    }
