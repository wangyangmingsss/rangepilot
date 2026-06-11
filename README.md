# RangePilot

**A CMC Skill that generates safety-screened, contract-mapped, backtestable
market-making strategies for PancakeSwap V3 on BNB Chain — and serves them as
an on-chain hireable agent (ERC-8004 + APEX) on BSC testnet.**

Built for **BNB Hack: AI Trading Agents — Track 2 (Strategy Skills)**.
Track 2 in one line: *ship a backtestable spec, not a live agent — think quant
research.* RangePilot ships exactly that, plus the rails to be hired for it
on-chain.

---

## What it does (60 seconds)

```
"WBNB/USDT, 5000 USDT, balanced risk"
        │
        ▼
┌─ L1 DATA & SIGNAL ──────────── CMC Agent Hub ────────────────────────────┐
│ DEX historical OHLCV (built for backtesting) + Hub pre-computed regime / │
│ liquidity / risk signals (graceful, disclosed fallback to local engine)  │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌─ RESEARCH ENGINE ────────────────────────────────────────────────────────┐
│ 9-candidate grid (3 families × 3 widths) → IS/OOS split (select on IS    │
│ only) → robustness gates: A1 share ±50%, costs ×2, k-plateau → honest    │
│ negative results allowed → 4-panel tearsheet                             │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌─ L2 SAFETY (Trust Wallet Agent Kit) ─────────────────────────────────────┐
│ token risk screen before any pool enters the universe + executability    │
│ audit: which actions are TWAK-native (swap legs) vs generic contract     │
│ calls (mint/burn → WalletConnect proposal)                               │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
                      StrategySpec (canonical JSON + sha256)
                                   │
┌─ L3 ON-CHAIN AGENT (BNB AI Agent SDK, BSC testnet) ──────────────────────┐
│ ERC-8004 identity (gas-free via MegaFuel) + APEX server: a client agent  │
│ negotiates → funds ERC-8183 escrow → POSTs /job/execute → this repo      │
│ generates the spec → SDK pins it to IPFS, anchors the content hash       │
│ on-chain, UMA asserts, escrow settles. Research with a receipt.          │
└──────────────────────────────────────────────────────────────────────────┘
```

**No-alpha claim.** RangePilot does not predict prices. It optimizes a payoff
*structure* — fee income vs impermanent loss across volatility regimes — and
stress-tests every assumption it makes. See `docs/METHODOLOGY.md`.

## Judge quickstart (offline, deterministic, no keys)

```bash
pip install -r requirements.txt
python tests/run_all.py          # 18 tests: math, no-lookahead, pipeline, APEX handler
python scripts/run_demo.py       # full pipeline on the bundled seed-fixed sample
bash reproduce.sh                # verify deterministic double hashes
```

Artifacts land in `examples/demo_output/`:
`*_spec.json` (the deliverable), `*_tearsheet.png` (4-panel visual),
`*_report.md` (numbers-traceable narrative). Ten-minute walkthrough:
`docs/JUDGE_QUICKSTART.md`.

---

## ✅ Proof of Execution & DoraHacks Evidence

This repository has passed all offline verification and **full on-chain APEX lifecycle tests**. Key artifacts for judges:

### 1. Deterministic Reproducibility
- `research_sha256`: `f36e09205ea12ca53bf05a2014d8c2a3b1efcb39432403a64239e96d37972e30` (run-stable across machines)
- `spec_sha256`: `95b0e59105e8556faa594fb4c8d4ad3e64fb42b93adc6ef8642064f0dcdd59f1` (delivery anchor)
- Run `bash reproduce.sh` to verify locally.

### 2. Full APEX On-Chain Lifecycle (BSC Testnet)
We have successfully executed the complete ERC-8183 client hiring workflow:
- **Step A: Agent Identity Registration**
  - `agentId`: `1360`
  - Registration Tx: [`0x831fee562cef5e8ed131db90f092e513daa9b9538742b8baa2525d84a02956ab`](https://testnet.bscscan.com/tx/0x831fee562cef5e8ed131db90f092e513daa9b9538742b8baa2525d84a02956ab)
- **Step B: Client Job Creation & Funding (Job #146)**
  - Client Address: `0xc842e355Fc93C43e39e0856572bB04cD1ae92eC4`
  - Actions: `createJob` → `registerJob` → `setBudget` → `approve` → `fund` (1.0 U Token escrowed)
- **Step C: Agent Execution & On-Chain Submission**
  - Provider Address: `0x6d662707910440FBe94F13bfC103e61018b77808`
  - Action: RangePilot engine generated the strategy spec and anchored its hash on-chain via `submit`.
  - **🏆 Submission Tx**: [`0x87cb63bebd960d6336d68bc8adaa1ee200567be03b92c02d86ce47742c68c6a1`](https://testnet.bscscan.com/tx/0x87cb63bebd960d6336d68bc8adaa1ee200567be03b92c02d86ce47742c68c6a1)
  - Delivered Spec SHA256: `4eccb43f8e7365a47dbf4b5f748f1519322b468c5a8491b30c26e0b354151695`

### 3. Day-1 Smoke Test Status
- T0=GO (offline engine), T1=NO-GO (CMC HTTP 500, gracefully degraded to CSV fallback as designed), T2/T3=ADAPT (TWAK fallback active), T4/T5=SKIP.

> **Note on `robust=false`**: The bundled demo intentionally yields a `robust=false` result. This is a designed, honest negative result where the gatekeeper correctly rejects an In-Sample (IS) peak, and the Out-of-Sample (OOS) metrics prove the rejection was justified. This is a core feature of our risk management, not a bug.

> The bundled CSV is **synthetic** (seed-fixed regime-switching GBM, generated
> by `scripts/gen_sample_data.py`) so the engine is reproducible offline and
> honest about it. Live runs pull real PancakeSwap pair history from CMC
> (`/v4/dex/pairs/ohlcv/historical`).

## Live paths

```bash
cp .env.example .env                       # fill what you have (see docs/PREPARATION)
python scripts/day1_smoke_tests.py         # T0..T5 go/no-go for every integration
python -m rangepilot.cli generate --pool 0x<pcs_v3_pool> --bars 3600   # live data run
python -m rangepilot.cli serve-apex        # hireable agent (bsc-testnet)
python scripts/apex_client_demo.py         # client-side hiring walkthrough
python scripts/register_erc8004.py         # on-chain identity (gas-free, testnet)
```

## Honest assumptions (the headline ones)

| # | Assumption | Mitigation |
|---|------------|-----------|
| A1 | Fee share uses a **static** active-liquidity snapshot (no historical tick-level liquidity exists in any public API) | stress-tested at ×0.5/×1.0/×1.5; `share_cap` = 25%; gate fails the spec if APR collapses |
| A2 | Rebalance cost = 15 bps + $0.60 gas (BSC, conservative) | stress-tested at ×0.5/×1.0/×2.0 |
| A3 | In-bar time-in-range ≈ candle `[low,high]` overlap with the range | disclosed in every spec |
| A4 | Volume = per-bar quote volume from CMC DEX OHLCV | disclosed in every spec |

Every spec carries these in `assumptions_and_disclosures`, plus the selection
audit trail (`data_lineage.selection`) and the robustness verdict. A strategy
that fails the gates is still delivered — flagged `robust=false` — because
negative results are results.

## Sponsor capabilities used

| Layer | What | Where |
|-------|------|-------|
| **CMC Agent Hub** (L1) | DEX historical OHLCV for backtests; Hub pre-computed indicators as the regime brain (disclosed local fallback); optional x402 keyless pay-per-request; shipped in the openCMC skill format | `rangepilot/data/`, `rangepilot/signals/`, `skills/rangepilot-strategy/` |
| **Trust Wallet Agent Kit** (L2) | pre-trade token risk screening; executability audit separating TWAK-native swap legs from generic mint/burn contract calls | `rangepilot/twak/`, `rangepilot/spec/validator.py` |
| **BNB AI Agent SDK** (L3) | ERC-8004 on-chain identity + APEX (ERC-8183 escrow + UMA evaluation): RangePilot is a hireable research agent on BSC testnet | `rangepilot/apex/`, `scripts/register_erc8004.py` |

Full evidence map per special prize: `docs/SPONSOR_INTEGRATION.md`.

## Repository layout

```
rangepilot/            the package
  data/                CMC REST client + x402 wrapper + disk cache + CSV loader
  signals/             regime layer (local engine + CMC Hub provider w/ fallback)
  engine/              V3 math, LP backtester, strategy families, sensitivity
  spec/                StrategySpec builder + executability validator
  twak/                Trust Wallet risk screen (live client + labelled stub)
  apex/                bnbagent on_job handler + server entrypoint
  report/              tearsheet (matplotlib) + numbers-traceable narrative
  skill/               the end-to-end pipeline (runner) behind every entrypoint
  cli.py               generate / backtest / serve-apex / smoke-test
skills/rangepilot-strategy/SKILL.md    openCMC-format skill card
scripts/               demo, sample-data generator, smoke tests, ERC-8004, client demo
tests/run_all.py       zero-dependency test suite (pytest-compatible style)
docs/                  methodology, architecture, sponsor evidence, judge guide
data/sample/           seed-fixed synthetic market (labelled)
examples/              sample APEX job request + generated demo artifacts
```

## Status & limitations

- BSC **testnet** for everything on-chain (the bnbagent SDK supports testnet
  only today; Track 2 requires no live execution).
- `[VERIFY-DAY1]` markers (4) flag every live-API field that must be confirmed
  against current docs before live-data claims; `scripts/day1_smoke_tests.py`
  is the checklist runner.
- Research tooling, not financial advice. Specs are simulations under
  disclosed assumptions; do not sign anything against an unvalidated spec.

MIT licensed. See `docs/` for everything else.
