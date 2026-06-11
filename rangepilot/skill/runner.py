"""RangePilot skill runner — the end-to-end pipeline behind every entry point
(CLI, APEX on_job, CMC-skill invocation).

Pipeline
--------
1. load OHLCV (CSV offline path, or CMC DEX historical via API key)
2. split IS / OOS  (default 70/30 by time; selection happens ONLY on IS)
3. evaluate the candidate grid on IS; keep candidates passing robustness gates
4. select best robust candidate by IS edge_vs_hodl (ties -> lower drawdown)
5. report the selected candidate's untouched OOS metrics (no reselection)
6. full-period backtest for the tearsheet
7. TWAK executability validation
8. assemble StrategySpec (+ canonical sha256) and artifacts

Negative results are shipped, not hidden: if nothing passes the gates the
spec is still produced with `selection.status = "no_robust_candidate"` and the
best-effort candidate clearly flagged non-robust.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..config import DEFAULTS, BacktestDefaults
from ..data.cmc_client import CMCClient, load_csv
from ..engine.lp_backtester import run_backtest, BacktestResult
from ..engine.strategies import candidate_grid, StrategyParams
from ..engine.sensitivity import robustness_report
from ..signals.regime import LocalComputedSignals
from ..spec.strategy_spec import build_spec, save_spec, data_manifest
from ..spec.validator import validate_spec_inputs
from ..report.tearsheet import render_tearsheet
from ..report.narrative import narrate


@dataclass
class GenerationRequest:
    pair: dict                      # {"base","quote","base_address","quote_address","pool_address"}
    capital_quote: float = 5000.0
    risk: str = "balanced"          # conservative | balanced | aggressive
    fee_tier: int = 2500
    csv_path: str | None = None     # offline path
    interval: str = "1h"
    bars: int = 24 * 150            # backfill depth when fetching live
    out_dir: str = "out"

    @classmethod
    def from_json(cls, text: str) -> "GenerationRequest":
        d = json.loads(text)
        return cls(**d)


@dataclass
class GenerationResult:
    spec: dict
    spec_path: str
    tearsheet_path: str
    narrative: str
    selected: StrategyParams
    is_result: BacktestResult
    oos_metrics: dict | None


def _load_data(req: GenerationRequest) -> tuple[pd.DataFrame, str | None]:
    if req.csv_path:
        return load_csv(req.csv_path), req.csv_path
    client = CMCClient()
    df = client.dex_ohlcv_historical(
        contract_address=req.pair.get("pool_address"),
        network_slug="bsc", interval=req.interval, count=req.bars)
    return df, None


def generate(req: GenerationRequest,
             cfg: BacktestDefaults = DEFAULTS) -> GenerationResult:
    out_dir = Path(req.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ohlcv, src_path = _load_data(req)
    if len(ohlcv) < 24 * 20:
        raise ValueError(f"need >= {24*20} bars for a meaningful IS/OOS study, "
                         f"got {len(ohlcv)}")

    split = int(len(ohlcv) * 0.7)
    is_df, oos_df = ohlcv.iloc[:split], ohlcv.iloc[split:]

    # --- candidate evaluation on IS only -----------------------------------
    rows = []
    for cand in candidate_grid(req.risk):
        r = run_backtest(is_df, cand, req.capital_quote, req.fee_tier, cfg=cfg)
        rows.append((cand, r))

    scored = []
    for cand, r in rows:
        rob = robustness_report(is_df, cand, req.capital_quote, req.fee_tier, cfg)
        scored.append({"cand": cand, "is": r, "rob": rob})

    robust = [s for s in scored if s["rob"]["robust"]]
    pool = robust if robust else scored
    pool.sort(key=lambda s: (-(s["is"].metrics["edge_vs_hodl_5050"] or -9),
                             abs(s["is"].metrics["max_drawdown"])))
    best = pool[0]
    selection_status = "robust_candidate_selected" if robust else "no_robust_candidate"

    # --- untouched OOS evaluation of the single selected candidate ----------
    oos_metrics = None
    if len(oos_df) >= 24 * 7:
        oos_metrics = run_backtest(oos_df, best["cand"], req.capital_quote,
                                   req.fee_tier, cfg=cfg).metrics

    # --- full-period run for the tearsheet ----------------------------------
    full = run_backtest(ohlcv, best["cand"], req.capital_quote, req.fee_tier, cfg=cfg)

    # --- TWAK executability validation ---------------------------------------
    width_sample = 0.05
    validation = validate_spec_inputs(pair=req.pair, fee_tier=req.fee_tier,
                                      sample_price=float(ohlcv["close"].iloc[-1]),
                                      sample_width=width_sample, cfg=cfg)

    # --- assemble spec --------------------------------------------------------
    lineage = {
        "ohlcv": data_manifest(src_path, ohlcv),
        "interval": req.interval,
        "regime_source": full.regime_source,
        "is_oos_split": {"is_bars": len(is_df), "oos_bars": len(oos_df), "ratio": 0.7},
        "selection": {
            "status": selection_status,
            "grid_size": len(scored),
            "robust_candidates": len(robust),
            "selected_family": best["cand"].family,
            "selected_k_sigma": best["cand"].k_sigma,
        },
    }
    spec = build_spec(pair=req.pair, capital_quote=req.capital_quote,
                      fee_tier=req.fee_tier, params=best["cand"],
                      backtest_metrics=best["is"].metrics,
                      oos_metrics=oos_metrics,
                      robustness=best["rob"],
                      regime_source=full.regime_source,
                      data_lineage=lineage,
                      twak_validation=validation, cfg=cfg)

    base = f"rangepilot_{req.pair.get('base','BASE')}_{req.pair.get('quote','QUOTE')}"
    spec_path = save_spec(spec, str(out_dir / f"{base}_spec.json"))
    tearsheet_path = render_tearsheet(full, spec, str(out_dir / f"{base}_tearsheet.png"))
    text = narrate(spec, full.metrics)
    (out_dir / f"{base}_report.md").write_text(text, encoding="utf-8")

    return GenerationResult(spec=spec, spec_path=spec_path,
                            tearsheet_path=tearsheet_path, narrative=text,
                            selected=best["cand"], is_result=best["is"],
                            oos_metrics=oos_metrics)
