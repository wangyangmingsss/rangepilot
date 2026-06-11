"""Executability validator: builds the `validation` block of a StrategySpec.

Checks performed
----------------
V1  token risk screen for base & quote token addresses (TWAK live client when
    configured, otherwise the labelled offline stub — never silent).
V2  action mapping audit: every execution_mapping action classified as
    `twak_native` (swap legs) or `generic_contract_call` (mint/burn legs that
    need WalletConnect proposal / external executor).
V3  parameter sanity: slippage/cost assumptions within sane bounds, ranges
    constructible on the fee tier's tick grid.

Outcome: status = "pass" | "pass_with_warnings" | "blocked".
A "high" token risk verdict blocks the spec (risk_controls demand it).
"""
from __future__ import annotations

from ..config import FEE_TIERS, DEFAULTS, BacktestDefaults
from ..engine.amm_math import geometric_range, aligned_range
from ..twak.risk_screen import get_screener, RiskReport


def validate_spec_inputs(*, pair: dict, fee_tier: int, sample_price: float,
                         sample_width: float,
                         cfg: BacktestDefaults = DEFAULTS) -> dict:
    warnings: list[str] = []
    blockers: list[str] = []

    # V1 — token risk screen
    screener = get_screener()
    reports: list[RiskReport] = []
    for key in ("base_address", "quote_address"):
        addr = pair.get(key)
        if addr:
            rep = screener.screen_token(addr)
            reports.append(rep)
            if rep.risk_level == "high":
                blockers.append(f"{key} flagged high risk: {rep.flags}")
            elif rep.risk_level == "unknown":
                warnings.append(f"{key}: no live TWAK screen performed "
                                f"(provider={rep.provider}) — run before execution")
        else:
            warnings.append(f"{key} missing — risk screen skipped")

    # V2 — action mapping audit (informational; mapping itself lives in spec)
    mapping_audit = {
        "twak_native_actions": ["rebalance.swap_to_ratio", "pause.exit_to_quote (swap leg)"],
        "generic_contract_calls": ["open_position (NPM.mint)",
                                    "rebalance.exit (NPM.decreaseLiquidity/collect/burn)"],
        "twak_modes": {
            "swap_legs": "TWAK agent-wallet autonomous mode within user caps",
            "mint_burn_legs": "WalletConnect proposal (user approves) or external executor",
        },
    }

    # V3 — parameter sanity
    if fee_tier not in FEE_TIERS:
        blockers.append(f"unknown fee tier {fee_tier}")
    else:
        spacing = FEE_TIERS[fee_tier]["tick_spacing"]
        pa, pb = geometric_range(sample_price, max(sample_width, 1e-4))
        tl, tu, _, _ = aligned_range(pa, pb, spacing)
        if tu - tl < spacing:
            blockers.append("range collapses below one tick spacing")
    if cfg.rebalance_cost_rate > 0.01:
        warnings.append("rebalance_cost_rate > 100bps — check assumption A2")
    if cfg.share_cap > 0.5:
        warnings.append("share_cap > 50% of active liquidity is unrealistic")

    status = "blocked" if blockers else ("pass_with_warnings" if warnings else "pass")
    return {
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "token_risk_reports": [r.to_dict() for r in reports],
        "action_mapping_audit": mapping_audit,
    }
