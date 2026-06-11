"""StrategySpec — the contract between research and execution.

One JSON document, three consumers:
1. Judges            — backtest summary, robustness report, honest assumptions.
2. An executor agent — `execution_mapping` translates every rule into concrete
                       PancakeSwap V3 contract calls (note: PancakeSwap is
                       called directly; the BNB AI Agent SDK has *no* trading
                       primitives — it is used for identity/commerce, see
                       rangepilot/apex/).
3. APEX settlement   — the canonical JSON's sha256 is the deliverable content
                       hash anchored on-chain (IPFS upload handled by the
                       bnbagent SDK).
"""
from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
import subprocess
from datetime import datetime, timezone

from ..config import (CHAIN, DEX, PANCAKE_V3_CONTRACTS, FEE_TIERS,
                      BacktestDefaults, DEFAULTS)
from ..engine.strategies import StrategyParams

SPEC_VERSION = "1.1.0"


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unversioned"


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of(obj: dict | str | bytes) -> str:
    if isinstance(obj, dict):
        obj = canonical_json(obj)
    if isinstance(obj, str):
        obj = obj.encode("utf-8")
    return hashlib.sha256(obj).hexdigest()


def data_manifest(ohlcv_path: str | None, ohlcv_df) -> dict:
    raw_hash = None
    rel_path = ohlcv_path
    if ohlcv_path:
        try:
            with open(ohlcv_path, "rb") as f:
                raw_hash = hashlib.sha256(f.read()).hexdigest()
        except Exception:
            raw_hash = None
        # Portability: store the path relative to the repo root so the same
        # study yields the same research_sha256 on any machine. Integrity is
        # carried by the file sha256, not the path string.
        try:
            _repo = Path(__file__).resolve().parents[2]
            rel_path = str(Path(ohlcv_path).resolve().relative_to(_repo))
        except Exception:
            rel_path = Path(ohlcv_path).name
    return {
        "source_path": rel_path,
        "rows": int(len(ohlcv_df)),
        "start": str(ohlcv_df.index[0]),
        "end": str(ohlcv_df.index[-1]),
        "sha256": raw_hash,
        "columns": list(map(str, ohlcv_df.columns)),
    }


def build_spec(*,
               pair: dict,
               capital_quote: float,
               fee_tier: int,
               params: StrategyParams,
               backtest_metrics: dict,
               oos_metrics: dict | None,
               robustness: dict,
               regime_source: str,
               data_lineage: dict,
               twak_validation: dict | None,
               cfg: BacktestDefaults = DEFAULTS,
               notes: str = "") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    spec: dict = {
        "spec_version": SPEC_VERSION,
        "generator": {
            "name": "RangePilot",
            "engine_commit": _git_commit(),
            "python": platform.python_version(),
            "generated_at": now,
        },
        "market": {
            "chain": CHAIN,
            "dex": DEX,
            "pair": pair,                      # {"base":..,"quote":..,"pool_address":..}
            "fee_tier": fee_tier,
            "fee_rate": FEE_TIERS[fee_tier]["rate"],
            "tick_spacing": FEE_TIERS[fee_tier]["tick_spacing"],
        },
        "capital": {"amount_quote": capital_quote, "denomination": pair.get("quote", "quote")},
        "strategy": {
            "family": params.family,
            "params": params.to_dict(),
            "regime_source": regime_source,
        },
        "rebalance_rules": {
            "trigger": params.rebalance_trigger,
            "edge_band": params.edge_band,
            "cooldown_bars": params.cooldown_bars,
            "max_rebalances_per_day": params.max_rebalances_per_day,
        },
        "risk_controls": {
            "pause_in_stress": params.pause_in_stress,
            "pause_in_high_vol": params.pause_in_high_vol,
            "token_risk_screen_required": True,
            "max_position_share_of_active_liquidity": cfg.share_cap,
        },
        "backtest": {
            "in_sample": backtest_metrics,
            "out_of_sample": oos_metrics,
            "robustness": robustness,
        },
        "assumptions_and_disclosures": {
            "A1_active_liquidity_quote": cfg.active_liquidity_quote,
            "A1_note": ("Fee share uses a STATIC active-liquidity snapshot; CMC "
                        "provides no historical tick-level liquidity. Stress "
                        "tested at x0.5/x1.0/x1.5 in robustness.share_sensitivity."),
            "A2_rebalance_cost_rate": cfg.rebalance_cost_rate,
            "A2_gas_usd_per_rebalance": cfg.gas_usd_per_rebalance,
            "A2_entry_cost_rate": cfg.entry_cost_rate,
            "A3_note": ("In-bar time-in-range proxied by candle [low,high] overlap "
                        "with the position range."),
            "A4_note": "Volume is quote-denominated per-bar volume from CMC DEX OHLCV.",
            "no_alpha_claim": ("RangePilot optimizes a payoff STRUCTURE (fees vs IL) "
                               "under volatility regimes. It does not claim "
                               "directional price-prediction alpha."),
        },
        "data_lineage": data_lineage,
        "execution_mapping": _execution_mapping(fee_tier),
        "validation": twak_validation or {"status": "not_run"},
        "notes": notes,
    }
    # research_sha256: stable across re-runs of the same study — excludes the
    # volatile generator block (timestamp/commit). Use it to compare runs.
    spec["research_sha256"] = sha256_of(
        {k: v for k, v in spec.items() if k not in ("generator", "research_sha256")})
    # spec_sha256: hash of the full canonical document — what an APEX
    # deliverable anchors on-chain (each delivered artifact is unique).
    spec["spec_sha256"] = sha256_of({k: v for k, v in spec.items() if k != "spec_sha256"})
    return spec


def _execution_mapping(fee_tier: int) -> dict:
    npm = PANCAKE_V3_CONTRACTS["nonfungible_position_manager"]
    router = PANCAKE_V3_CONTRACTS["swap_router"]
    return {
        "venue_contracts_bsc_mainnet": PANCAKE_V3_CONTRACTS,
        "verify_note": "[VERIFY-DAY1] re-check addresses on docs.pancakeswap.finance before any signing.",
        "actions": [
            {"rule": "open_position",
             "contract": npm,
             "call": "mint(MintParams{token0,token1,fee,tickLower,tickUpper,...})",
             "params_from_spec": ["market.fee_tier", "strategy.params.k_sigma",
                                   "regime->width via strategy.params.regime_width_mult"]},
            {"rule": "rebalance.exit",
             "contract": npm,
             "call": "decreaseLiquidity + collect + burn"},
            {"rule": "rebalance.swap_to_ratio",
             "contract": router,
             "call": "exactInputSingle(...)",
             "twak_note": "This leg is a plain swap and is executable via the "
                          "Trust Wallet Agent Kit swap skill within user-set caps."},
            {"rule": "pause.exit_to_quote",
             "contract": npm, "call": "decreaseLiquidity + collect + burn, then router swap to quote"},
        ],
        "executor_note": ("Position mint/burn are generic contract calls (not a TWAK "
                          "native skill); under TWAK they are proposed via WalletConnect "
                          "for user approval, or executed by any generic BSC executor. "
                          "Swap legs map to TWAK-native swap automation."),
    }


def save_spec(spec: dict, path: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
    return path
