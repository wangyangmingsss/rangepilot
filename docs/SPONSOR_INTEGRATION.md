# Sponsor Integration & Evidence Map

How each sponsor capability is used, where the code lives, and what a judge
can verify in two minutes. We state plainly what is native, what is adapted,
and what still needs Day-1 wiring — overstating sponsor integration would be
the fastest way to lose credibility with the people who built these tools.

---

## L1 · CoinMarketCap Agent Hub — data & signal

**Used for**

1. **Backtest fuel** — `/v4/dex/pairs/ohlcv/historical` (the endpoint CMC
   documents as built for backfilling charts and backtesting strategies) is
   the primary OHLCV source for PancakeSwap pairs.
   Code: `rangepilot/data/cmc_client.py` (`dex_ohlcv_historical`,
   shape-tolerant `normalize_ohlcv`, disk cache, plan-gate-aware errors).
2. **Regime brain** — Hub pre-computed indicators (market regime / liquidity
   / risk flags) drive generation-time range width and stand-aside via
   `CMCHubSignals`. Until the exact tool fields are pinned (Day-1 task T2),
   it degrades **loudly** to the local engine and the spec records
   `regime_source = cmc-hub-degraded-to-local`.
   Code: `rangepilot/signals/regime.py`, `cmc_client.fetch_hub_indicators`.
3. **x402 keyless path (optional, as the track lists it)** — pay-per-request
   wrapper for agents without API keys.
   Code: `rangepilot/data/x402_client.py`; smoke test T5.
4. **Skill-format delivery** — the whole capability ships as an
   openCMC-convention skill card: `skills/rangepilot-strategy/SKILL.md`
   (folder + SKILL.md, copy-into-skills-directory installation, same pattern
   as the official `cmc-mcp` / `cmc-x402` skills). Marketplace-ready; listing
   itself is CMC's call.

**Two-minute verification**: open the skill card; run
`python scripts/run_demo.py`; open the generated spec's `data_lineage` and
`assumptions_and_disclosures`.

**Day-1 wiring left**: T1 exact v4 DEX param names (adapt via `extra_params`,
no code change needed); T2 Hub indicator field mapping.

---

## L2 · Trust Wallet Agent Kit — safety & executability

**Used for**

1. **Pre-trade token risk screen** — every base/quote address is screened
   before a pool can enter a strategy universe (market-making into a
   honeypot is donating money — LPs are *more* exposed than traders).
   A `high` verdict **blocks** the spec.
   Code: `rangepilot/twak/risk_screen.py` (live client behind
   `TWAK_API_BASE`/`TWAK_API_KEY`; otherwise an explicitly-labelled offline
   stub that returns `unknown` so the spec never pretends a real screen ran).
2. **Executability audit** — the validator classifies every execution action:
   swap legs (rebalance-to-ratio, exit-to-quote) are **TWAK-native**
   (agent-wallet autonomous mode within user caps); position mint/burn are
   **generic contract calls** routed through WalletConnect proposal for user
   approval or an external executor. This separation is written into both the
   spec's `execution_mapping.executor_note` and
   `validation.action_mapping_audit`.
   Code: `rangepilot/spec/validator.py`.

**What we deliberately do *not* claim**: that TWAK natively mints V3
positions. It doesn't; the spec says so. The honest framing is "execution
safety moved up into the research stage": a spec arrives pre-screened, with
each action labelled by custody path, before anyone signs anything.

**Two-minute verification**: open any generated spec →
`validation.token_risk_reports` (provider field shows stub vs live) and
`validation.action_mapping_audit`.

**Day-1 wiring left**: T3 exact security-endpoint path/schema from
portal.trustwallet.com.

---

## L3 · BNB AI Agent SDK — on-chain identity & hireable research

The SDK's actual capabilities are **ERC-8004 identity** and **APEX commerce**
(ERC-8183 escrow + UMA OOv3 evaluation). It has no trading primitives — and
that is exactly why a *research* skill is its natural showcase:

1. **ERC-8004 identity** — RangePilot registers as a discoverable on-chain
   agent (gas-free on BSC testnet via the MegaFuel paymaster).
   Code: `scripts/register_erc8004.py`.
2. **APEX hireable agent** — `create_apex_app(on_job=handle_job)`: a client
   agent negotiates a price, creates and funds an ERC-8183 job whose
   description is the request JSON, POSTs `/job/execute`; the handler runs
   the full pipeline; the SDK uploads the spec to IPFS, anchors its content
   hash on-chain, the UMA evaluator asserts, the 30-minute liveness window
   passes, escrow settles. **The StrategySpec's sha256 doubles as the
   on-chain deliverable hash — quantitative research with a receipt.**
   Code: `rangepilot/apex/handler.py` (job-description contract documented in
   the module docstring), `rangepilot/apex/server.py`,
   `scripts/apex_client_demo.py`.
3. **PancakeSwap venue mapping** — the spec's `execution_mapping` targets
   PancakeSwap V3 contracts on BSC **directly** (NonfungiblePositionManager /
   SwapRouter), correctly attributed to the venue rather than to the SDK.

**Two-minute verification (testnet)**: `python -m rangepilot.cli serve-apex`,
then `python scripts/apex_client_demo.py` against it; or read
`apex/handler.py` top-of-file contract.

**Constraints stated up front**: bsc-testnet only (SDK status today);
IPFS storage (`STORAGE_PROVIDER=ipfs`) required for evaluator-verifiable
deliverables; faucets for tBNB and the U payment token are linked in the
preparation guide.

---

## Cross-cutting honesty markers a judge can grep

```
grep -rn "VERIFY-DAY1" rangepilot/ scripts/      # every unverified live field (4)
grep -rn "offline-heuristic-stub" rangepilot/    # the labelled TWAK fallback
grep -n  "degraded-to-local" rangepilot/signals/regime.py
```
