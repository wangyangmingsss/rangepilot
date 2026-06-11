#!/usr/bin/env python3
"""Day-1 go/no-go smoke tests.

Run these BEFORE building anything on live integrations. Each test reports
GO / NO-GO / SKIP(unconfigured). The repo is designed so every SKIP has an
offline fallback, but the four [VERIFY-DAY1] markers in the codebase must be
resolved here before any live-data claims are made in the submission.

    python scripts/day1_smoke_tests.py            # or: python -m rangepilot.cli smoke-test

T0  offline engine integrity        (no network; must always be GO)
T1  CMC DEX historical OHLCV        (needs CMC_API_KEY)
T2  CMC Hub pre-computed indicators (needs CMC_API_KEY; expected NO-GO until
                                     fetch_hub_indicators is wired to the
                                     verified MCP/REST source)
T3  TWAK token risk screen          (needs TWAK_API_BASE + TWAK_API_KEY)
T4  bnbagent / APEX readiness       (needs `pip install "bnbagent[server,ipfs]"`
                                     + wallet env; checks imports & env only,
                                     never sends a transaction)
T5  x402 keyless path (optional)    (needs x402 + eth-account + X402_PRIVATE_KEY)
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GO, NOGO, SKIP = "GO    ", "NO-GO ", "SKIP  "
RESULTS: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str) -> None:
    RESULTS.append((status, name, detail))
    print(f"[{status}] {name}: {detail}")


def t0_offline_engine() -> None:
    try:
        from rangepilot.data.cmc_client import load_csv
        from rangepilot.engine.lp_backtester import run_backtest
        from rangepilot.engine.strategies import make_strategy
        from rangepilot.spec.strategy_spec import build_spec  # noqa: F401

        sample = ROOT / "data" / "sample" / "WBNB_USDT_1h_sample.csv"
        if not sample.exists():
            record(NOGO, "T0 offline engine",
                   "sample CSV missing — run scripts/gen_sample_data.py")
            return
        df = load_csv(sample).iloc[: 24 * 30]
        r = run_backtest(df, make_strategy("regime_adaptive"), 5000, 2500)
        record(GO, "T0 offline engine",
               f"backtest ok over {r.metrics['bars']} bars, "
               f"net_return={r.metrics['net_return']:+.4f}")
    except Exception as e:
        record(NOGO, "T0 offline engine", f"{e}\n{traceback.format_exc(limit=2)}")


def t1_cmc_dex_ohlcv() -> None:
    if not os.getenv("CMC_API_KEY"):
        record(SKIP, "T1 CMC DEX OHLCV", "CMC_API_KEY not set")
        return
    try:
        from rangepilot.data.cmc_client import CMCClient

        client = CMCClient()
        # WBNB/USDT is used as the default probe pair; replace pool address
        # after confirming the exact param contract from the raw payload below.
        probe = os.getenv("SMOKE_POOL_ADDRESS",
                          "0x36696169c63e42cd08ce11f5deebbcebae652050")  # PCS v3 WBNB/USDT 0.05% [VERIFY-DAY1]
        df = client.dex_ohlcv_historical(contract_address=probe,
                                         network_slug=os.getenv("SMOKE_NETWORK_SLUG", "bsc"),
                                         interval="1h", count=48, use_cache=False)
        record(GO, "T1 CMC DEX OHLCV",
               f"{len(df)} bars, {df.index[0]} -> {df.index[-1]}; "
               f"params accepted as configured")
    except Exception as e:
        record(NOGO, "T1 CMC DEX OHLCV",
               f"{e} | Action: inspect the raw error body above; adjust "
               f"network_slug / contract_address / interval via extra_params "
               f"in rangepilot/data/cmc_client.py (plan gating shows as 401/403).")


def t2_hub_indicators() -> None:
    if not os.getenv("CMC_API_KEY"):
        record(SKIP, "T2 Hub indicators", "CMC_API_KEY not set")
        return
    try:
        from rangepilot.data.cmc_client import CMCClient

        live = CMCClient().fetch_hub_indicators()
        record(GO, "T2 Hub indicators", f"fields: {sorted(live)}")
    except Exception as e:
        record(NOGO, "T2 Hub indicators",
               f"{e} | Expected until wired: connect the CMC MCP server "
               f"(https://mcp.coinmarketcap.com/mcp) from your agent runtime, list "
               f"its 12 tools, identify the regime/liquidity/risk-flag fields, then "
               f"implement fetch_hub_indicators(). Strategy generation degrades to "
               f"the local regime engine (recorded in spec.data_lineage) meanwhile.")


def t3_twak_screen() -> None:
    from rangepilot.twak.risk_screen import TWAKRiskClient

    client = TWAKRiskClient()
    if not client.configured:
        record(SKIP, "T3 TWAK risk screen",
               "TWAK_API_BASE / TWAK_API_KEY not set (get them from "
               "https://portal.trustwallet.com). Pipeline uses the labelled "
               "offline stub until then — spec.validation says so explicitly.")
        return
    try:
        rep = client.screen_token("0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")  # WBNB
        record(GO, "T3 TWAK risk screen",
               f"WBNB risk_level={rep.risk_level}, flags={rep.flags}")
    except Exception as e:
        record(NOGO, "T3 TWAK risk screen",
               f"{e} | Action: confirm the exact security/risk endpoint path & "
               f"schema in the TWAK portal docs and update "
               f"rangepilot/twak/risk_screen.py::TWAKRiskClient.screen_token.")


def t4_apex_readiness() -> None:
    try:
        import bnbagent  # type: ignore  # noqa: F401
        from bnbagent.apex.server import create_apex_app  # type: ignore  # noqa: F401
    except Exception as e:
        record(SKIP, "T4 bnbagent/APEX",
               f'not installed ({e}) — pip install "bnbagent[server,ipfs]"')
        return
    missing = [k for k in ("WALLET_PASSWORD",) if not os.getenv(k)]
    storage = os.getenv("STORAGE_PROVIDER", "local")
    notes = []
    if missing:
        notes.append(f"missing env: {missing}")
    if storage != "ipfs":
        notes.append("STORAGE_PROVIDER!=ipfs (local ok for dev; ipfs required "
                     "for evaluator-verifiable deliverables)")
    net = os.getenv("NETWORK", "bsc-testnet")
    if net != "bsc-testnet":
        notes.append(f"NETWORK={net} — SDK supports bsc-testnet only today")
    status = GO if not notes else NOGO
    record(status, "T4 bnbagent/APEX",
           "import ok; " + ("env ready (faucets: tBNB + U token, see docs)"
                            if not notes else "; ".join(notes)))


def t5_x402_optional() -> None:
    if not os.getenv("X402_PRIVATE_KEY"):
        record(SKIP, "T5 x402 (optional)", "X402_PRIVATE_KEY not set — optional path")
        return
    try:
        from rangepilot.data.x402_client import fetch_via_x402

        payload = fetch_via_x402("/x402/v1/dex/search",
                                 {"q": "WBNB", "network": "bsc"})
        record(GO, "T5 x402 (optional)", f"paid call ok, keys: {sorted(payload)[:5]}")
    except Exception as e:
        record(NOGO, "T5 x402 (optional)",
               f"{e} | Action: confirm the x402 route list & client library usage "
               f"in CMC x402 docs; a first 402 Payment-Required response that then "
               f"succeeds after payment handling is the documented success path.")


def main() -> int:
    print("RangePilot Day-1 smoke tests\n" + "=" * 60)
    t0_offline_engine()
    t1_cmc_dex_ohlcv()
    t2_hub_indicators()
    t3_twak_screen()
    t4_apex_readiness()
    t5_x402_optional()
    print("=" * 60)
    counts = {s: sum(1 for r in RESULTS if r[0] == s) for s in (GO, NOGO, SKIP)}
    print(f"GO={counts[GO]}  NO-GO={counts[NOGO]}  SKIP={counts[SKIP]}")
    print(json.dumps([{ "status": s.strip(), "test": n, "detail": d[:160]}
                      for s, n, d in RESULTS], indent=2, ensure_ascii=False))
    # Only T0 is a hard gate for the offline deliverable; live NO-GOs are the
    # Day-1 work queue, not build blockers.
    return 0 if all(r[0] != NOGO or not r[1].startswith("T0") for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
