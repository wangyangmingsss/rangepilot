# RangePilot strategy report — WBNB/USDT

**Venue**: PancakeSwap V3 on BSC, fee tier 0.25% (tick spacing 50).
**Family**: `regime_adaptive`, k_sigma=1.9, regime source: local.
**Selection**: no_robust_candidate out of a 9-candidate grid (0 passed all robustness gates). Selection used in-sample data only; out-of-sample is reported untouched.

## Full-period results
- net return -9.87% (APR -26.48%), fee APR +127.97%, max drawdown -40.27%
- time in range 0.9984, rebalances 6, edge vs HODL 50/50 -1.75%

## Out-of-sample (selected candidate, untouched)
- net -33.74%, APR -342.13%, maxDD -41.36%, edge vs HODL -6.43%

## Robustness gates
- PASS — survives_share_minus50
- PASS — survives_cost_x2
- PASS — drawdown_under_35pct
- FAIL — k_plateau_ok

## Honest assumptions (stress-tested)
- A1 static active-liquidity 2000000 quote units; share sensitivity x0.5/x1.0/x1.5 attached in spec.
- A2 rebalance cost 15 bps + $0.60 gas per event; cost sensitivity x0.5/x1.0/x2.0 attached.
- No directional alpha is claimed: RangePilot optimizes the fees-vs-IL payoff structure.

Spec sha256: `95b0e59105e8556faa594fb4c8d4ad3e64fb42b93adc6ef8642064f0dcdd59f1` (this hash is the APEX deliverable anchor).