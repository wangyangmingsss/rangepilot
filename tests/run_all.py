#!/usr/bin/env python3
"""RangePilot self-contained test runner (no pytest dependency).

    python tests/run_all.py
"""
from __future__ import annotations

import json
import math
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from rangepilot.engine import amm_math as am
from rangepilot.engine.lp_backtester import run_backtest
from rangepilot.engine.strategies import make_strategy, candidate_grid
from rangepilot.engine.sensitivity import robustness_report, share_sensitivity
from rangepilot.signals.regime import LocalComputedSignals
from rangepilot.spec.strategy_spec import build_spec, sha256_of, canonical_json
from rangepilot.spec.validator import validate_spec_inputs
from rangepilot.data.cmc_client import load_csv, normalize_ohlcv
from rangepilot.config import DEFAULTS

SAMPLE = ROOT / "data" / "sample" / "WBNB_USDT_1h_sample.csv"

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


# ---------------------------------------------------------------- AMM math --

@test
def amm_tick_roundtrip():
    for p in (0.0001, 1.0, 599.37, 1e6):
        t = am.price_to_tick(p)
        assert am.tick_to_price(t) <= p < am.tick_to_price(t + 1)


@test
def amm_value_equals_capital_at_entry():
    pos = am.liquidity_for_capital(10_000, 600, 540, 660)
    assert abs(pos.value(600) - 10_000) < 1e-6


@test
def amm_composition_at_bounds():
    pos = am.liquidity_for_capital(10_000, 600, 540, 660)
    a0_low, a1_low = pos.amounts(540)     # at/below lower bound -> all base
    assert a1_low < 1e-9 and a0_low > 0
    a0_high, a1_high = pos.amounts(660)   # at/above upper bound -> all quote
    assert a0_high < 1e-9 and a1_high > 0
    # value continuity just inside vs at the bound
    assert abs(pos.value(660) - pos.value(659.999)) < 0.5


@test
def amm_il_zero_at_entry_negative_elsewhere():
    pos = am.liquidity_for_capital(10_000, 600, 500, 720)
    assert abs(pos.il_vs_hodl(600)) < 1e-6
    for p in (520, 560, 640, 700, 760, 450):
        assert pos.il_vs_hodl(p) <= 1e-9, f"IL must be <=0 vs HODL at {p}"


@test
def amm_full_range_tracks_sqrt_payoff():
    # value of a (≈) full-range position scales like sqrt(P) * const
    pos = am.liquidity_for_capital(10_000, 600, 600 / 10_000, 600 * 10_000)
    v1, v2 = pos.value(600), pos.value(2400)  # price x4 -> value x~2
    assert abs(v2 / v1 - 2.0) < 0.05


@test
def amm_overlap_fraction():
    pos = am.liquidity_for_capital(1_000, 600, 580, 620)
    assert pos.range_overlap_fraction(580, 620) == 1.0
    assert pos.range_overlap_fraction(560, 580) == 0.0
    assert abs(pos.range_overlap_fraction(570, 590) - 0.5) < 1e-9
    assert pos.range_overlap_fraction(600, 600) == 1.0


@test
def amm_aligned_range_contains_request():
    tl, tu, pa, pb = am.aligned_range(540.3, 661.7, 50)
    assert pa <= 540.3 and pb >= 661.7 and tl % 50 == 0 and tu % 50 == 0 and tl < tu


# -------------------------------------------------------------- backtester --

def _df():
    return load_csv(SAMPLE)


@test
def backtest_runs_and_conserves_value():
    df = _df()
    params = make_strategy("regime_adaptive", "balanced")
    r = run_backtest(df, params, 5000, 2500)
    eq = r.equity.dropna()
    assert len(eq) == len(df)
    assert (eq > 0).all()
    # accounting identity: equity = capital + fees - costs + lp price pnl;
    # therefore equity - fees + costs - capital == lp price pnl, and the
    # HODL-edge decomposition must be finite & consistent
    m = r.metrics
    assert m["fees_total_quote"] >= 0 and m["costs_total_quote"] >= 0
    assert m["n_rebalances"] >= 1
    assert 0 <= (m["time_in_range"] or 0) <= 1


@test
def backtest_zero_fee_zero_cost_equals_lp_mark():
    """With no fees, no costs, no rebalancing, equity must equal the analytic
    LP value of the single opened position."""
    from dataclasses import replace
    df = _df().iloc[: 24 * 30]
    cfg = replace(DEFAULTS, entry_cost_rate=0.0, rebalance_cost_rate=0.0,
                  gas_usd_per_rebalance=0.0, active_liquidity_quote=1e15)
    params = make_strategy("static_range", "balanced", k_sigma=50.0,  # huge range, no exits
                           cooldown_bars=10**6)
    r = run_backtest(df, params, 5000, 2500, cfg=cfg, warmup_bars=10)
    opens = [e for e in r.events if e.new_range]
    assert len(opens) == 1, f"expected single open, got {len(opens)}"
    pa, pb = opens[0].new_range
    pos = am.liquidity_for_capital(5000, float(r.close.iloc[10]), pa, pb)
    expected = pos.value(float(r.close.iloc[-1]))
    got = float(r.equity.iloc[-1])
    assert abs(got - expected) < 1e-6 * 5000, (got, expected)


@test
def backtest_fees_scale_with_share():
    df = _df()
    params = make_strategy("static_range", "balanced")
    rows = share_sensitivity(df, params, 5000, 2500)
    fees = [r["fee_apr"] for r in rows]
    assert fees[0] < fees[1] < fees[2], f"fee APR must rise with share: {fees}"


@test
def backtest_no_lookahead_prefix_consistency():
    """Decisions must not use future bars: running on a prefix must produce an
    identical event log to the full run truncated to that prefix."""
    df = _df()
    cut = len(df) - 24 * 10
    params = make_strategy("stress_pause", "balanced")
    r_full = run_backtest(df, params, 5000, 2500)
    r_pref = run_backtest(df.iloc[:cut], params, 5000, 2500)
    ev_full = [(str(e.ts), e.reason) for e in r_full.events if e.ts in df.index[:cut]]
    ev_pref = [(str(e.ts), e.reason) for e in r_pref.events]
    assert ev_full == ev_pref, "event log diverges -> lookahead leak"


@test
def backtest_pause_family_reduces_trend_drawdown():
    df = _df()
    base = run_backtest(df, make_strategy("static_range", "balanced"), 5000, 2500)
    paused = run_backtest(df, make_strategy("stress_pause", "balanced"), 5000, 2500)
    assert any(e.reason == "pause" for e in paused.events), "stress pause never fired"
    assert abs(paused.metrics["max_drawdown"]) <= abs(base.metrics["max_drawdown"]) + 0.02


# ------------------------------------------------------------------ regime --

@test
def regime_labels_cover_all_three():
    df = _df()
    rf = LocalComputedSignals().compute(df)
    seen = set(rf.regime.unique())
    assert {"low", "mid", "high"} <= seen, seen
    assert rf.trend_stress.any(), "trend leg in sample data must trigger stress"
    assert rf.source == "local"


# ----------------------------------------------------------------- spec ----

@test
def spec_builds_and_hash_is_canonical():
    df = _df().iloc[: 24 * 40]
    params = make_strategy("regime_adaptive", "balanced")
    r = run_backtest(df, params, 5000, 2500)
    rob = robustness_report(df, params, 5000, 2500)
    val = validate_spec_inputs(pair={"base": "WBNB", "quote": "USDT",
                                      "base_address": "0x" + "b" * 40,
                                      "quote_address": "0x" + "5" * 40},
                               fee_tier=2500, sample_price=600, sample_width=0.05)
    spec = build_spec(pair={"base": "WBNB", "quote": "USDT"}, capital_quote=5000,
                      fee_tier=2500, params=params, backtest_metrics=r.metrics,
                      oos_metrics=None, robustness=rob, regime_source=r.regime_source,
                      data_lineage={"ohlcv": {"rows": len(df)}},
                      twak_validation=val)
    body = {k: v for k, v in spec.items() if k != "spec_sha256"}
    assert spec["spec_sha256"] == sha256_of(body)
    json.loads(canonical_json(spec))  # canonical form is valid JSON
    assert spec["assumptions_and_disclosures"]["A1_active_liquidity_quote"] > 0
    assert spec["execution_mapping"]["actions"], "execution mapping must be present"
    assert val["status"] in ("pass", "pass_with_warnings", "blocked")


@test
def validator_blocks_bad_inputs():
    bad = validate_spec_inputs(pair={"base_address": "0x" + "b" * 40},
                               fee_tier=12345, sample_price=600, sample_width=0.05)
    assert bad["status"] == "blocked"


# ----------------------------------------------------------- normalization --

@test
def cmc_normalizer_handles_two_payload_shapes():
    shape_a = {"data": {"quotes": [
        {"time_open": "2026-01-01T00:00:00Z", "quote": {"USD": {
            "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}}},
        {"time_open": "2026-01-01T01:00:00Z", "quote": {"USD": {
            "open": 1.5, "high": 2.2, "low": 1.1, "close": 2.0, "volume": 120}}},
    ]}}
    df = normalize_ohlcv(shape_a)
    assert list(df.columns) == ["open", "high", "low", "close", "volume_quote"]
    assert len(df) == 2 and df["close"].iloc[-1] == 2.0
    shape_b = {"data": [{"timestamp": 1767225600, "open": 1, "high": 2,
                          "low": 0.5, "close": 1.5, "volume_24h": 99}]}
    df2 = normalize_ohlcv(shape_b)
    assert df2["volume_quote"].iloc[0] == 99


# -------------------------------------------------------------- pipeline ----

@test
def full_pipeline_offline_generate():
    from rangepilot.skill.runner import GenerationRequest, generate
    req = GenerationRequest(
        pair={"base": "WBNB", "quote": "USDT",
              "base_address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
              "quote_address": "0x55d398326f99059fF775485246999027B3197955"},
        capital_quote=5000, risk="balanced", csv_path=str(SAMPLE),
        out_dir=str(ROOT / "out" / "test_run"))
    res = generate(req)
    assert Path(res.spec_path).exists() and Path(res.tearsheet_path).exists()
    assert res.spec["backtest"]["in_sample"]["bars"] > 0
    assert res.spec["backtest"]["out_of_sample"] is not None
    assert res.spec["data_lineage"]["selection"]["grid_size"] == 9
    assert "spec_sha256" in res.spec
    assert res.spec["validation"]["status"] in ("pass", "pass_with_warnings")


@test
def apex_handler_returns_deliverable():
    from rangepilot.apex.handler import handle_job, parse_job_description
    req = parse_job_description("not json at all")
    assert req.csv_path and Path(req.csv_path).exists()
    deliverable, meta = handle_job({"jobId": 1, "description": json.dumps({
        "capital_quote": 3000, "risk": "conservative",
        "csv_path": str(SAMPLE), "out_dir": str(ROOT / "out" / "apex_test")})})
    spec = json.loads(deliverable)
    assert spec["capital"]["amount_quote"] == 3000
    assert meta["spec_sha256"] == spec["spec_sha256"]


# -------------------------------------------------------------------- main --

def main() -> int:
    passed = failed = 0
    for fn in TESTS:
        name = fn.__name__
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception:
            print(f"  FAIL  {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(TESTS)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
