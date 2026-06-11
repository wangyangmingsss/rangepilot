---
name: rangepilot-strategy
description: Generate a safety-screened, backtestable PancakeSwap V3 market-making (concentrated-liquidity) strategy spec for any BSC pair from CoinMarketCap market data. Use when an agent or user asks for an LP/market-making strategy, optimal range widths, rebalancing rules, or a fees-vs-impermanent-loss study on BNB Chain. Returns a canonical StrategySpec JSON with backtest metrics, robustness gates, honest assumptions, and a contract-level execution mapping.
---

# RangePilot — Market-Making Strategy Generator (CMC Skill)

This skill follows the openCMC skill conventions
(`skills/<name>/SKILL.md`, copy the folder into your agent's skills
directory). It layers on top of CoinMarketCap data access (API key, MCP, or
x402) the way the official CMC skills do.

## What this skill does

Given a BSC pair, capital, and a risk profile, it:

1. pulls PancakeSwap pair history from CMC DEX OHLCV (or a provided CSV),
2. evaluates a 3-family × 3-width candidate grid under a no-lookahead LP
   backtest (fees vs impermanent loss vs costs),
3. selects on in-sample only, reports untouched out-of-sample metrics,
4. stress-tests the fee-share, cost, and width assumptions (robustness gates),
5. risk-screens the tokens (Trust Wallet Agent Kit when configured),
6. returns one canonical **StrategySpec JSON** (sha256-stable) plus a
   tearsheet PNG and a numbers-traceable report.

It optimizes payoff *structure* (fees vs IL across volatility regimes). It
does **not** claim directional price-prediction alpha, and it ships negative
results flagged `robust=false` rather than hiding them.

## When to use

- "Build me an LP / market-making strategy for <pair> on BNB Chain"
- "What range width and rebalancing rules should I use on PancakeSwap V3?"
- "Is LPing <pair> worth it after impermanent loss and gas?"
- An executor/trading agent needs a vetted, machine-readable range policy.

Do **not** use for directional trade signals, CEX strategies, or non-BSC
chains (v1 scope is PancakeSwap V3 on BSC).

## Inputs (request contract)

The skill takes a JSON request — an LLM agent should translate the user's
natural-language ask into this object (see `examples/sample_job_request.json`):

```json
{
  "pair": {
    "base": "WBNB", "quote": "USDT",
    "base_address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    "quote_address": "0x55d398326f99059fF775485246999027B3197955",
    "pool_address": "0x<pancakeswap_v3_pool>"
  },
  "capital_quote": 5000,
  "risk": "balanced",
  "fee_tier": 2500,
  "csv_path": null
}
```

`risk` ∈ conservative | balanced | aggressive. `fee_tier` ∈ 100/500/2500/10000
(PancakeSwap V3). `csv_path` set ⇒ fully offline run. `pool_address` set and
`csv_path` null ⇒ live CMC fetch (CMC_API_KEY required).

## How to run

```bash
# CLI
python -m rangepilot.cli generate --csv data/sample/WBNB_USDT_1h_sample.csv
python -m rangepilot.cli generate --pool 0x<pool> --bars 3600        # live

# Python
from rangepilot.skill.runner import GenerationRequest, generate
res = generate(GenerationRequest.from_json(open("request.json").read()))

# As an on-chain hireable agent (BSC testnet): put the request JSON in the
# ERC-8183 job description and POST /job/execute — see scripts/apex_client_demo.py
python -m rangepilot.cli serve-apex
```

## Environment

| Var | Needed for | Notes |
|-----|-----------|-------|
| `CMC_API_KEY` | live data | from pro.coinmarketcap.com |
| `TWAK_API_BASE`, `TWAK_API_KEY` | live token risk screen | portal.trustwallet.com; offline runs use a clearly-labelled stub |
| `X402_PRIVATE_KEY` | optional keyless data path | Base wallet holding a little USDC |
| bnbagent env (`WALLET_PASSWORD`, `STORAGE_API_KEY`, …) | APEX server | see `.env.example` |

No key at all ⇒ the skill still runs end-to-end on CSVs (deterministic demo).

## Output

`out/<pair>_spec.json` — StrategySpec v1.1: market, strategy params,
rebalance rules, risk controls, IS/OOS backtest + robustness report,
assumptions A1–A4, data lineage with selection audit, TWAK validation block,
PancakeSwap V3 execution mapping, canonical `spec_sha256`.
Plus `*_tearsheet.png` and `*_report.md`.

## Limits & honesty

Fee share uses a static active-liquidity snapshot (A1, ±50% stress-tested,
25% share cap); in-bar time-in-range is a candle-overlap proxy (A3); testnet
only for on-chain parts; every live-API field is `[VERIFY-DAY1]`-marked and
checked by `scripts/day1_smoke_tests.py`. Research output, not financial
advice.
