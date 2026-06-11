"""Tearsheet renderer — the 90-second judge demo asset.

One PNG, four panels:
1. price path with the live position range bands + rebalance/pause markers
2. cumulative fees vs cumulative costs (the structural P&L race)
3. strategy equity vs HODL 50/50 vs 100% quote vs full-range LP
4. drawdown
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from ..engine.lp_backtester import BacktestResult


def render_tearsheet(result: BacktestResult, spec: dict, out_path: str) -> str:
    idx = result.equity.index
    fig, axes = plt.subplots(4, 1, figsize=(13, 14), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1.6, 2.2, 1.2]})
    fam = spec["strategy"]["family"]
    pair = spec["market"]["pair"]
    title = (f"RangePilot — {pair.get('base','?')}/{pair.get('quote','?')} "
             f"PancakeSwap V3 ({spec['market']['fee_rate']*100:.2f}% tier) — "
             f"{fam}, k={spec['strategy']['params']['k_sigma']}")
    fig.suptitle(title, fontsize=13)

    # P1 price + ranges
    ax = axes[0]
    ax.plot(idx, result.close, lw=1.0, label="price", color="#1f77b4")
    ax.plot(idx, result.range_lower, lw=0.9, ls="--", color="#2ca02c", label="range low")
    ax.plot(idx, result.range_upper, lw=0.9, ls="--", color="#d62728", label="range high")
    ax.fill_between(idx, result.range_lower, result.range_upper, alpha=0.08, color="green")
    for ev in result.events:
        if ev.reason in ("range_exit", "edge_band"):
            ax.axvline(ev.ts, color="orange", alpha=0.25, lw=0.8)
        elif ev.reason == "pause":
            ax.axvline(ev.ts, color="red", alpha=0.35, lw=0.8)
        elif ev.reason == "resume":
            ax.axvline(ev.ts, color="purple", alpha=0.3, lw=0.8)
    ax.set_ylabel("price (quote)")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_title("Position ranges, rebalances (orange) and pauses (red)", fontsize=10)

    # P2 fees vs costs
    ax = axes[1]
    ax.plot(idx, result.fees_cum, label="cumulative fees", color="#2ca02c")
    ax.plot(idx, result.costs_cum, label="cumulative costs (swap+gas)", color="#d62728")
    ax.set_ylabel("quote")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_title("Structural P&L race: fee income vs friction", fontsize=10)

    # P3 equity vs benchmarks
    ax = axes[2]
    ax.plot(idx, result.equity, label="RangePilot", lw=1.4, color="#1f77b4")
    ax.plot(idx, result.hodl_5050, label="HODL 50/50", lw=1.0, color="#7f7f7f")
    ax.plot(idx, result.hodl_quote, label="100% quote", lw=0.9, ls=":", color="#bcbd22")
    ax.plot(idx, result.full_range_lp, label="full-range LP (same share model)",
            lw=1.0, ls="--", color="#9467bd")
    ax.set_ylabel("equity (quote)")
    ax.legend(loc="upper left", fontsize=8)
    m = result.metrics
    ax.set_title(f"net={m['net_return']:+.2%}  APR={m['apr']:+.2%}  "
                 f"feeAPR={(m['fee_apr'] or 0):+.2%}  maxDD={m['max_drawdown']:.2%}  "
                 f"timeInRange={m['time_in_range']}  rebal={m['n_rebalances']}",
                 fontsize=10)

    # P4 drawdown
    ax = axes[3]
    eq = result.equity.ffill()
    dd = eq / eq.cummax() - 1.0
    ax.fill_between(idx, dd, 0, color="#d62728", alpha=0.4)
    ax.set_ylabel("drawdown")
    ax.set_xlabel("time (UTC)")

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path
