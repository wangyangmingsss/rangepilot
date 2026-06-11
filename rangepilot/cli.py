"""RangePilot CLI.

  python -m rangepilot.cli generate --csv data/sample/WBNB_USDT_1h_sample.csv \
      --base WBNB --quote USDT --capital 5000 --risk balanced
  python -m rangepilot.cli generate --pool 0x... --bars 3600        # live CMC fetch
  python -m rangepilot.cli backtest --csv ... --family stress_pause --k 1.5
  python -m rangepilot.cli serve-apex --port 8000
  python -m rangepilot.cli smoke-test
"""
from __future__ import annotations

import argparse
import json
import sys

from .skill.runner import GenerationRequest, generate
from .data.cmc_client import load_csv
from .engine.lp_backtester import run_backtest
from .engine.strategies import make_strategy


def _cmd_generate(a) -> int:
    pair = {"base": a.base, "quote": a.quote,
            "base_address": a.base_address, "quote_address": a.quote_address,
            "pool_address": a.pool}
    req = GenerationRequest(pair=pair, capital_quote=a.capital, risk=a.risk,
                            fee_tier=a.fee_tier, csv_path=a.csv,
                            bars=a.bars, out_dir=a.out)
    res = generate(req)
    print(json.dumps({
        "spec": res.spec_path,
        "tearsheet": res.tearsheet_path,
        "selected": {"family": res.selected.family, "k_sigma": res.selected.k_sigma},
        "is_metrics": res.is_result.metrics,
        "oos_metrics": res.oos_metrics,
        "robust": res.spec["backtest"]["robustness"]["robust"],
        "validation_status": res.spec["validation"]["status"],
        "spec_sha256": res.spec["spec_sha256"],
    }, indent=2))
    return 0


def _cmd_backtest(a) -> int:
    df = load_csv(a.csv)
    params = make_strategy(a.family, a.risk, k_sigma=a.k)
    r = run_backtest(df, params, a.capital, a.fee_tier)
    print(json.dumps(r.metrics, indent=2))
    return 0


def _cmd_serve(a) -> int:
    try:
        import uvicorn  # type: ignore
        from .apex.server import build_app
    except Exception as e:
        print(f"serve-apex needs: pip install \"bnbagent[server,ipfs]\" uvicorn ({e})")
        return 1
    uvicorn.run(build_app(), host="0.0.0.0", port=a.port)
    return 0


def _cmd_smoke(_a) -> int:
    from scripts import day1_smoke_tests  # type: ignore
    return day1_smoke_tests.main()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="rangepilot")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="full pipeline -> spec + tearsheet + report")
    g.add_argument("--csv"); g.add_argument("--pool")
    g.add_argument("--base", default="WBNB"); g.add_argument("--quote", default="USDT")
    g.add_argument("--base-address", default="0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")
    g.add_argument("--quote-address", default="0x55d398326f99059fF775485246999027B3197955")
    g.add_argument("--capital", type=float, default=5000)
    g.add_argument("--risk", default="balanced",
                   choices=["conservative", "balanced", "aggressive"])
    g.add_argument("--fee-tier", type=int, default=2500)
    g.add_argument("--bars", type=int, default=24 * 150)
    g.add_argument("--out", default="out")
    g.set_defaults(fn=_cmd_generate)

    b = sub.add_parser("backtest", help="single-strategy backtest on a CSV")
    b.add_argument("--csv", required=True)
    b.add_argument("--family", default="regime_adaptive",
                   choices=["static_range", "regime_adaptive", "stress_pause"])
    b.add_argument("--risk", default="balanced",
                   choices=["conservative", "balanced", "aggressive"])
    b.add_argument("--k", type=float, default=1.5)
    b.add_argument("--capital", type=float, default=5000)
    b.add_argument("--fee-tier", type=int, default=2500)
    b.set_defaults(fn=_cmd_backtest)

    s = sub.add_parser("serve-apex", help="run the APEX agent server")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=_cmd_serve)

    t = sub.add_parser("smoke-test", help="Day-1 go/no-go checks")
    t.set_defaults(fn=_cmd_smoke)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
