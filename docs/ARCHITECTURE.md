# Architecture

```
                          entrypoints
   ┌────────────┬─────────────────┬──────────────────┬──────────────┐
   │  CLI       │  Python API     │  APEX /job/exec  │  CMC skill   │
   │  cli.py    │  skill.runner   │  apex/handler    │  SKILL.md    │
   └─────┬──────┴────────┬────────┴────────┬─────────┴──────┬───────┘
         └───────────────┴───────► generate(GenerationRequest) ◄──────┘
                                   (skill/runner.py — the one pipeline)
                                            │
   ┌────────────────────────────────────────┼─────────────────────────────┐
   │ 1 load data        data/cmc_client  ───┤  CSV (offline) | CMC REST   │
   │                    data/x402_client    │  | x402 (optional)          │
   │ 2 regimes          signals/regime  ────┤  local engine | CMC Hub     │
   │                                        │  (loud fallback)            │
   │ 3 IS/OOS + grid    engine/strategies ──┤  3 families × 3 widths      │
   │ 4 backtests        engine/lp_backtester│  no-lookahead loop          │
   │                    engine/amm_math     │  V3 position math           │
   │ 5 robustness       engine/sensitivity ─┤  A1±50%, costs×2, k-plateau │
   │ 6 safety           twak/risk_screen ───┤  live TWAK | labelled stub  │
   │ 7 validation       spec/validator  ────┤  V1 screen V2 mapping V3    │
   │ 8 assemble         spec/strategy_spec ─┤  canonical JSON + sha256    │
   │ 9 artifacts        report/tearsheet ───┤  4-panel PNG                │
   │                    report/narrative ───┤  numbers-traceable text     │
   └─────────────────────────────────────────────────────────────────────┘
                                            │
              ┌─────────────────────────────┼──────────────────────────┐
              ▼                             ▼                          ▼
        out/*_spec.json              out/*_tearsheet.png        out/*_report.md
              │
              ▼ (when hired via APEX, bsc-testnet)
   bnbagent SDK: IPFS pin → content hash on-chain → UMA assertion → settle
```

## Module map

All paths below are under the `rangepilot/` Python package unless absolute.

| Path | Responsibility | Key invariants |
|------|----------------|----------------|
| `config.py` | every tunable + chain/venue/endpoint constants | all `[VERIFY-DAY1]` fields flagged; A1–A4 defaults documented inline |
| `rangepilot/data/cmc_client.py` | CMC REST, payload normalization, disk cache | shape-tolerant parser; plan-gates surface as readable errors |
| `rangepilot/data/x402_client.py` | optional keyless paid path | dependency-optional; never required |
| `rangepilot/data/cache.py` | JSON disk cache | keyed by canonical params |
| `signals/regime.py` | vol-regime + trend-stress | backward-looking only; Hub provider degrades loudly |
| `engine/amm_math.py` | V3 ticks, liquidity, amounts, IL, overlap | clamped at bounds; aligned ranges contain requests |
| `engine/strategies.py` | parameter families + risk profiles + grid | strategies are data, not code |
| `engine/lp_backtester.py` | the simulation loop | fees only on pre-existing positions; decisions at close; warmup |
| `engine/sensitivity.py` | stress grids + gates | gates strict; negative results allowed |
| `twak/risk_screen.py` | token safety | stub is labelled, never silent |
| `spec/strategy_spec.py` | the deliverable | canonical JSON; sha256 = APEX content-hash candidate |
| `spec/validator.py` | executability audit | high token risk blocks |
| `apex/handler.py` `apex/server.py` | hireable agent | SDK-optional imports; testnet contract documented |
| `report/*` | tearsheet + narrative | LLM optional, numbers traceable |
| `skill/runner.py` | the one pipeline | IS-only selection; OOS untouched |
| `cli.py` | generate / backtest / serve-apex / smoke-test | thin over runner |

## Design rules

1. **One pipeline, many doors.** CLI, Python, APEX, and the skill card all
   call the same `generate()`; there is no demo-only code path.
2. **Degrade loudly.** Every fallback (Hub→local, TWAK→stub, live→CSV) is
   recorded in the spec; nothing silently pretends.
3. **Spec is the product.** Everything else (tearsheet, report, APEX
   deliverable) derives from the canonical JSON; its sha256 is stable across
   re-serialization and is what gets anchored on-chain.
4. **Offline-first reproducibility.** No key, no network ⇒ full pipeline
   still runs deterministically on the labelled synthetic sample.
