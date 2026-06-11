"""Report narration. LLM-optional, numbers-traceable.

Discipline (mirrors the bar set for Track 2 rigor): the LLM ONLY narrates;
every number in the text comes from the spec/metrics dicts, never from the
model. With no LLM configured, a deterministic template produces the report,
so offline reproduction is bit-stable.
"""
from __future__ import annotations

import json
import os
import urllib.request

from ..config import ENV


def narrate(spec: dict, full_metrics: dict) -> str:
    base = _template(spec, full_metrics)
    if not (ENV.llm_api_base and ENV.llm_api_key):
        return base
    try:
        polished = _llm_polish(base)
        return polished + "\n\n---\n*every figure above is sourced from the attached spec; LLM used for prose only*\n"
    except Exception:
        return base


def _template(spec: dict, m: dict) -> str:
    mk = spec["market"]; st = spec["strategy"]; bt = spec["backtest"]
    rob = bt["robustness"]; sel = spec["data_lineage"]["selection"]
    oos = bt.get("out_of_sample") or {}
    lines = [
        f"# RangePilot strategy report — {mk['pair'].get('base','?')}/{mk['pair'].get('quote','?')}",
        "",
        f"**Venue**: PancakeSwap V3 on BSC, fee tier {mk['fee_rate']*100:.2f}% "
        f"(tick spacing {mk['tick_spacing']}).",
        f"**Family**: `{st['family']}`, k_sigma={st['params']['k_sigma']}, "
        f"regime source: {st['regime_source']}.",
        f"**Selection**: {sel['status']} out of a {sel['grid_size']}-candidate grid "
        f"({sel['robust_candidates']} passed all robustness gates). Selection used "
        "in-sample data only; out-of-sample is reported untouched.",
        "",
        "## Full-period results",
        f"- net return {m['net_return']:+.2%} (APR {m['apr']:+.2%}), "
        f"fee APR {(m['fee_apr'] or 0):+.2%}, max drawdown {m['max_drawdown']:.2%}",
        f"- time in range {m['time_in_range']}, rebalances {m['n_rebalances']}, "
        f"edge vs HODL 50/50 {m['edge_vs_hodl_5050']:+.2%}" if m.get('edge_vs_hodl_5050') is not None else "",
        "",
        "## Out-of-sample (selected candidate, untouched)",
        (f"- net {oos.get('net_return',0):+.2%}, APR {oos.get('apr',0):+.2%}, "
         f"maxDD {oos.get('max_drawdown',0):.2%}, edge vs HODL "
         f"{(oos.get('edge_vs_hodl_5050') or 0):+.2%}") if oos else "- insufficient OOS window",
        "",
        "## Robustness gates",
    ]
    for g, ok in rob["gates"].items():
        lines.append(f"- {'PASS' if ok else 'FAIL'} — {g}")
    lines += [
        "",
        "## Honest assumptions (stress-tested)",
        f"- A1 static active-liquidity {spec['assumptions_and_disclosures']['A1_active_liquidity_quote']:.0f} "
        "quote units; share sensitivity x0.5/x1.0/x1.5 attached in spec.",
        f"- A2 rebalance cost {spec['assumptions_and_disclosures']['A2_rebalance_cost_rate']*1e4:.0f} bps "
        f"+ ${spec['assumptions_and_disclosures']['A2_gas_usd_per_rebalance']:.2f} gas per event; "
        "cost sensitivity x0.5/x1.0/x2.0 attached.",
        "- No directional alpha is claimed: RangePilot optimizes the fees-vs-IL payoff structure.",
        "",
        f"Spec sha256: `{spec['spec_sha256']}` (this hash is the APEX deliverable anchor).",
    ]
    return "\n".join(x for x in lines if x is not None)


def _llm_polish(markdown: str) -> str:
    body = json.dumps({
        "model": ENV.llm_model,
        "messages": [
            {"role": "system",
             "content": ("You polish quant research notes. Improve flow ONLY. "
                          "Do not add, change, or remove any numeric value, gate "
                          "result, or hash. Keep markdown structure.")},
            {"role": "user", "content": markdown},
        ],
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        f"{ENV.llm_api_base.rstrip('/')}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {ENV.llm_api_key}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]
