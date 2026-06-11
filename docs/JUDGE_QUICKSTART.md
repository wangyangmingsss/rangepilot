# Judge Quickstart — 10 minutes

## Minute 0–2 · run it (offline, no keys, deterministic)

```bash
pip install -r requirements.txt
python tests/run_all.py        # 18/18: math, no-lookahead, pipeline, APEX handler
python scripts/run_demo.py     # full pipeline on the bundled labelled sample
```

## Minute 2–5 · read the deliverable

Open `examples/demo_output/rangepilot_WBNB_USDT_spec.json` and check, in
order:

1. `assumptions_and_disclosures` — A1–A4 spelled out, incl. the static
   fee-share assumption and the **no_alpha_claim**.
2. `backtest.robustness` — share ±50% grid, costs ×2 grid, k-plateau, and the
   four gates; `robust` may be `false` — negative results ship.
3. `data_lineage.selection` — grid size, robust-candidate count, IS-only
   selection; `backtest.out_of_sample` is untouched holdout.
4. `validation` — token risk reports (provider says `offline-heuristic-stub`
   on keyless runs — the stub never impersonates a live screen) and the
   TWAK-native vs generic-contract-call action audit.
5. `execution_mapping` — every rule mapped to a PancakeSwap V3 contract call.
6. `research_sha256` / `spec_sha256` — the first is run-stable (compare
   across machines; `reproduce.sh` checks it), the second hashes the full
   document incl. timestamp and is the APEX deliverable content hash.

Then open `examples/demo_output/rangepilot_WBNB_USDT_tearsheet.png`: price + live range bands +
rebalance/pause markers; fees vs costs; equity vs three benchmarks; drawdown.

## Minute 5–7 · verify the rigor claims

```bash
grep -rn "VERIFY-DAY1" rangepilot/ scripts/ | wc -l     # every unverified live field is flagged
python - <<'EOF'
# no-lookahead spot check (same assertion the suite runs)
import sys; sys.path.insert(0, ".")
from rangepilot.data.cmc_client import load_csv
from rangepilot.engine.lp_backtester import run_backtest
from rangepilot.engine.strategies import make_strategy
df = load_csv("data/sample/WBNB_USDT_1h_sample.csv")
p = make_strategy("regime_adaptive")
full = run_backtest(df, p, 5000, 2500)
half = run_backtest(df.iloc[:len(df)//2], p, 5000, 2500)
import numpy as np
a = full.equity.iloc[:len(half.equity)].to_numpy(); b = half.equity.to_numpy()
print("prefix-identical:", bool(np.allclose(a, b, rtol=1e-9)))
EOF
```

## Minute 7–10 · the on-chain layer (optional, BSC testnet)

```bash
pip install "bnbagent[server,ipfs]" uvicorn
cp .env.example .env             # WALLET_PASSWORD + STORAGE_API_KEY minimum
python -m rangepilot.cli serve-apex &
python scripts/apex_client_demo.py     # /status → /negotiate → job walkthrough
python scripts/register_erc8004.py     # gas-free identity registration
```

The job description **is** the request JSON (`examples/sample_job_request.json`);
the spec **is** the IPFS-pinned, hash-anchored, UMA-asserted deliverable.

## Where each scoring dimension lives

| Criterion | Look at |
|-----------|---------|
| Technical execution | `engine/` + `tests/run_all.py` (conservation, no-lookahead, fee scaling) |
| Originality | a market-making *structure* skill (no-alpha-claim) + research-with-a-receipt via APEX |
| Real-world relevance | IL is the #1 LP pain on BSC; specs arrive risk-screened and contract-mapped; any agent can hire it on-chain |
| Sponsor stack | `docs/SPONSOR_INTEGRATION.md` (incl. what we deliberately do not claim) |
