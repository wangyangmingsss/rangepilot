"""RangePilot global configuration.

All tunables live here. Values marked [VERIFY-DAY1] must be confirmed against
live docs/chain during the Day-1 smoke tests (see scripts/day1_smoke_tests.py).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Chain / venue constants
# ---------------------------------------------------------------------------

CHAIN = "bsc"
CHAIN_ID_MAINNET = 56
CHAIN_ID_TESTNET = 97
DEX = "pancakeswap-v3"

# PancakeSwap V3 core contracts on BSC mainnet. [VERIFY-DAY1] against
# https://docs.pancakeswap.finance (addresses are stable but must be re-checked
# before generating any execution mapping that someone could sign).
PANCAKE_V3_CONTRACTS = {
    "factory": "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
    "nonfungible_position_manager": "0x46A15B0b27311cedF172AB29E4f4766fbE7F4364",
    "swap_router": "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
    "quoter_v2": "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997",
}

# PancakeSwap V3 fee tiers (in hundredths of a bip, i.e. 500 = 0.05%)
# and their tick spacings.
FEE_TIERS = {
    100: {"rate": 0.0001, "tick_spacing": 1},
    500: {"rate": 0.0005, "tick_spacing": 10},
    2500: {"rate": 0.0025, "tick_spacing": 50},
    10000: {"rate": 0.01, "tick_spacing": 200},
}

# ---------------------------------------------------------------------------
# CMC Agent Hub endpoints  [VERIFY-DAY1: exact params / plan gating / x402 routes]
# ---------------------------------------------------------------------------

CMC_REST_BASE = "https://pro-api.coinmarketcap.com"
CMC_MCP_URL = "https://mcp.coinmarketcap.com/mcp"
CMC_X402_BASE = "https://pro-api.coinmarketcap.com"  # x402 routes share base [VERIFY-DAY1]

CMC_ENDPOINTS = {
    "dex_ohlcv_historical": "/v4/dex/pairs/ohlcv/historical",
    "dex_quotes_latest": "/v4/dex/pairs/quotes/latest",
    "dex_search": "/v4/dex/spot-pairs/latest",  # discovery fallback [VERIFY-DAY1]
    "fear_greed": "/v3/fear-and-greed/latest",  # NOT used for alpha (see docs) – health check only
}

# ---------------------------------------------------------------------------
# Backtest defaults (every one of these is surfaced in the StrategySpec
# `assumptions` block – nothing silent)
# ---------------------------------------------------------------------------


@dataclass
class BacktestDefaults:
    # A1: active-liquidity share assumption. We model our fee share as
    #   share = our_position_value / (our_position_value + active_liquidity_quote)
    # using a *static* snapshot of pool active liquidity (quote-denominated).
    # CMC does not provide historical tick-level liquidity – this is the single
    # largest model assumption and is stress-tested at ±50% in sensitivity.
    active_liquidity_quote: float = 2_000_000.0
    share_cap: float = 0.25  # never assume we are more than 25% of active liq

    # A2: rebalance cost = swap fee + slippage applied to ~half the position
    # (the side that must be swapped back to ratio), plus fixed gas in USD.
    rebalance_cost_rate: float = 0.0015   # 15 bps on position value per rebalance
    gas_usd_per_rebalance: float = 0.60   # mint+burn+swap on BSC, conservative
    entry_cost_rate: float = 0.0010       # initial swap from 100% quote to LP mix

    # A3: in-bar time-in-range proxy = overlap of candle [low, high] with the
    # position range, as a fraction of the candle's price span.
    # A4: volume is quote-denominated 24h-style volume per bar from CMC OHLCV.
    min_bar_volume_quote: float = 0.0

    # engine
    bar_interval_hours: float = 1.0
    annualization_hours: float = 24 * 365


DEFAULTS = BacktestDefaults()

# ---------------------------------------------------------------------------
# Environment (.env is read by python-dotenv if installed; plain env otherwise)
# ---------------------------------------------------------------------------


def _maybe_load_dotenv() -> None:
    try:  # optional dependency
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()
    except Exception:
        pass


_maybe_load_dotenv()


@dataclass
class Env:
    cmc_api_key: str = field(default_factory=lambda: os.getenv("CMC_API_KEY", ""))
    twak_api_base: str = field(default_factory=lambda: os.getenv("TWAK_API_BASE", ""))
    twak_api_key: str = field(default_factory=lambda: os.getenv("TWAK_API_KEY", ""))
    llm_api_base: str = field(default_factory=lambda: os.getenv("LLM_API_BASE", ""))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "deepseek-chat"))
    # APEX / bnbagent (consumed by bnbagent SDK itself via its own env contract)
    network: str = field(default_factory=lambda: os.getenv("NETWORK", "bsc-testnet"))


ENV = Env()
