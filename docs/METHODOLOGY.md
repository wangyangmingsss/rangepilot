# RangePilot Methodology

Track 2's brief is "think quant research". This document is the research
contract: the model, every assumption, the anti-overfitting discipline, and
the limits. Anything not written here is not claimed.

## 1. Problem statement

A concentrated-liquidity position on PancakeSwap V3 earns trading fees while
the price stays inside its range and bleeds impermanent loss (IL) when the
price trends away. RangePilot searches for **range-policy parameters** —
width as a function of volatility regime, rebalancing triggers, stand-aside
rules — that maximize risk-adjusted *structural* P&L:

```
net P&L = fees earned − IL vs HODL − rebalance/entry costs − gas
```

This is **not** a price-prediction problem and we make **no alpha claim**.
The acceptance bar is honest robustness, not a flattering Sharpe.

## 2. Position model (Uniswap V3 / PancakeSwap V3 math)

Conventions: token0 = base, token1 = quote, price P = quote per base.
For a position over `[Pa, Pb]` with liquidity `L`, at spot `P` with
`s = √clamp(P, Pa, Pb)`, `sa = √Pa`, `sb = √Pb`:

```
amount0 = L · (sb − s) / (s · sb)
amount1 = L · (s − sa)
V(P)    = amount0 · P + amount1
```

Sizing inverts this: deploying capital `W` (quote) at `P0` gives
`L = W / (u0·P0 + u1)` where `(u0, u1)` are unit amounts. IL vs HODL is
`V(P) − (a0_entry·P + a1_entry)` — always ≤ 0 absent fees, which test
`amm_il_zero_at_entry_negative_elsewhere` asserts. Ranges are snapped to the
fee tier's tick grid (`aligned_range`), lower tick down / upper tick up, so
the constructed range always contains the requested one.

Implementation: `rangepilot/engine/amm_math.py`. PancakeSwap V3 is a Uniswap
V3 fork with identical position math; fee tiers / tick spacings differ and
live in `config.FEE_TIERS` (100→1, 500→10, 2500→50, 10000→200).

## 3. Fee model and the four disclosed assumptions

Per bar `t`, a position open since an earlier bar accrues:

```
fee_t = volume_quote_t · fee_rate · share · overlap_t
```

**A1 — fee share (the single largest assumption).** No public API — CMC
included — provides *historical tick-level* liquidity, so the in-range
liquidity competing with us cannot be reconstructed point-in-time. We model

```
share = V_position / (V_position + ALQ),   share ≤ share_cap (25%)
```

with `ALQ` (active liquidity, quote-denominated) a **static snapshot
parameter** (default $2M). Mitigations: (i) ×0.5/×1.0/×1.5 stress grid in
every spec (`robustness.share_sensitivity`); (ii) a robustness **gate** that
fails the candidate if APR collapses below −5% at the worst multiplier;
(iii) before live use, calibrate `ALQ` from the pool's current state and
re-run — the spec records the value used.

**A2 — costs.** Rebalance = 15 bps on position value + $0.60 fixed gas
(BSC, conservative); entry = 10 bps. Stress grid ×0.5/×1.0/×2.0 with a gate.

**A3 — in-bar time-in-range.** Within a bar we cannot observe the path, so
`overlap_t = |[low,high] ∩ [Pa,Pb]| / |[low,high]|` proxies the in-range
fraction. Linear-in-price; degenerate bars handled explicitly.

**A4 — volume.** Quote-denominated per-bar volume from CMC DEX OHLCV; a
`min_bar_volume_quote` haircut is available (default 0).

All four are reproduced verbatim in every spec's
`assumptions_and_disclosures` block.

## 4. Backtest discipline (no-lookahead)

- Decisions at bar *i* use information up to and including bar *i*'s close;
  positions opened at bar *i* start accruing fees at bar *i+1*.
- Regime inputs are rolling/backward-looking only; historical backtests
  **always** use the local regime engine on point-in-time OHLCV. CMC Hub
  pre-computed indicators are consumed at *generation time* (today's regime
  for today's width) — never to relabel history.
- Asserted by `backtest_no_lookahead_prefix_consistency`: truncating the
  future leaves the realized prefix of equity/decisions bit-identical.
- A warmup window (default min(n/5, 14d)) precedes any deployment; metrics
  start post-warmup.

## 5. Regime layer

Local engine: annualized realized vol over a 72-bar window → rolling
percentile (30d) → {low ≤ 33%, mid, high ≥ 66%}; `trend_stress` when
|EMA24/EMA168 − 1| ≥ 6% (strong trends are where passive LP bleeds fastest).
`CMCHubSignals` maps Hub indicators onto the same enum at generation time and
**degrades loudly**: any failure falls back to local and writes
`regime_source = cmc-hub-degraded-to-local` into the spec.

## 6. Strategy families (parameters, not code)

| Family | Width | Rebalance | Stand-aside |
|--------|-------|-----------|-------------|
| S1 static_range | k·σ(entry) | on range exit | never |
| S2 regime_adaptive | k·σ × regime multiplier | on exit / edge-band | never |
| S3 stress_pause | as S2 | as S2 | exits to quote during `trend_stress` (optionally high-vol) |

Risk profiles (conservative/balanced/aggressive) parameterize k, cooldowns,
and multipliers. Candidate grid = 3 families × 3 k-values.

## 7. Selection protocol & anti-overfitting gates

1. **IS/OOS split 70/30 by time.** The grid is evaluated and selected on IS
   only; the winner's OOS metrics are reported untouched (no reselection —
   `data_lineage.selection` is the audit trail).
2. **Robustness gates (all required for `robust=true`):**
   survives A1 ×0.5 (worst-share APR > −5%); survives costs ×2; max drawdown
   < 35%; **k-plateau** — the chosen k must sit on a performance plateau,
   not a lone spike (neighbours at k·(1±20%) must not collapse).
3. **Negative results ship.** If nothing passes, the spec is still produced
   with `selection.status = "no_robust_candidate"` and the best-effort
   candidate clearly flagged. Honest failure beats flattering noise.

## 8. Benchmarks & metrics

Benchmarks marked frictionless from the same start bar: HODL 50/50, 100%
quote, full-range LP (V2-like, with fees). Metrics: net return, APR, daily
Sharpe (annualized), max drawdown, fee APR, total costs, IL-vs-HODL price
effect, edge vs HODL 50/50, time-in-range, rebalance count.

## 9. Data lineage & reproducibility

Every spec embeds: source path + sha256 of the raw data file, row count and
date span, IS/OOS bar counts, selection audit, engine git commit, Python
version, and **two** canonical-JSON sha256 digests:

- `research_sha256` — hash of the research content only (excludes the
  volatile `generator` block: timestamp / commit / Python version). Two runs
  of the same study on the same data produce the **same** `research_sha256`;
  this is the reproducibility check (`reproduce.sh` compares it).
- `spec_sha256` — hash of the full document including the `generator` block.
  It differs across runs by design (it timestamps the act of generation) and
  is the content hash an APEX deliverable pins to IPFS and asserts on-chain.

The bundled sample market is **synthetic** (seed-fixed regime-switching GBM
with a trend leg; `scripts/gen_sample_data.py`) and labelled as such — it
validates the engine offline, it does not claim market performance. Offline
runs are deterministic: research content is bit-stable across runs
(identical `research_sha256` via `scripts/run_demo.py`), while `spec_sha256`
intentionally varies with the generation timestamp — verifiable research,
with the receipt separated from the run metadata.

## 10. Known limitations (read before quoting numbers)

1. A1 static-share is irreducible with public data; treat fee APRs as
   scenario outputs under the disclosed ALQ, not forecasts.
2. A3 overlap proxy ignores intra-bar path dependence; finer bars shrink the
   error (1h default).
3. No MEV/adverse-selection modelling; fee tiers assumed constant; pool
   migrations not modelled.
4. Single-pool, single-position policies in v1 (no multi-position ladders).
5. Synthetic sample ≠ market data; live conclusions require live pulls and a
   fresh robustness pass.
