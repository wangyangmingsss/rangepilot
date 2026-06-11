"""APEX job handler — turns RangePilot into an on-chain hireable agent.

How it plugs into the BNB AI Agent SDK (bnbagent):

    from bnbagent.apex.server import create_apex_app
    from rangepilot.apex.handler import handle_job
    app = create_apex_app(on_job=handle_job)

A client agent then: negotiates a price -> creates & funds an ERC-8183 job
with a JSON description -> POSTs /job/execute -> this handler runs the full
RangePilot pipeline -> the SDK uploads the returned spec JSON to IPFS, anchors
its content hash on-chain, the UMA evaluator asserts, and escrow settles.

Job description contract (the client puts this JSON in the job description):
{
  "pair": {"base": "WBNB", "quote": "USDT",
            "base_address": "0x...", "quote_address": "0x...",
            "pool_address": "0x..."},
  "capital_quote": 5000,
  "risk": "balanced",            # conservative | balanced | aggressive
  "fee_tier": 2500,
  "csv_path": null               # optional offline data path (demo/testnet runs)
}
Anything missing falls back to the bundled sample market so a testnet judge
can fund a job with a one-line description and still get a real deliverable.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..skill.runner import GenerationRequest, generate

SAMPLE_CSV = str(Path(__file__).resolve().parents[2] / "data" / "sample" /
                 "WBNB_USDT_1h_sample.csv")

DEFAULT_PAIR = {
    "base": "WBNB", "quote": "USDT",
    # canonical BSC token addresses [VERIFY-DAY1 before live screening]
    "base_address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    "quote_address": "0x55d398326f99059fF775485246999027B3197955",
    "pool_address": None,
}


def parse_job_description(description: str) -> GenerationRequest:
    try:
        d = json.loads(description)
        if not isinstance(d, dict):
            raise ValueError
    except Exception:
        d = {}
    pair = {**DEFAULT_PAIR, **(d.get("pair") or {})}
    csv_path = d.get("csv_path")
    if not csv_path and not d.get("pool_address") and not (d.get("pair") or {}).get("pool_address"):
        csv_path = SAMPLE_CSV  # guarantee a deliverable on testnet demos
    return GenerationRequest(
        pair=pair,
        capital_quote=float(d.get("capital_quote", 5000)),
        risk=str(d.get("risk", "balanced")),
        fee_tier=int(d.get("fee_tier", 2500)),
        csv_path=csv_path,
        out_dir=str(d.get("out_dir", "out/apex_jobs")),
    )


def handle_job(job: dict) -> tuple[str, dict]:
    """bnbagent `on_job` callback (sync signature with metadata).

    Returns (deliverable_string, metadata). The deliverable is the canonical
    spec JSON; bnbagent uploads it to IPFS and submits its content hash
    on-chain, auto-triggering the UMA assertion.
    """
    req = parse_job_description(job.get("description", "") or "")
    result = generate(req)
    deliverable = json.dumps(result.spec, indent=2, ensure_ascii=False)
    meta = {
        "skill": "rangepilot/strategy-generator",
        "spec_sha256": result.spec["spec_sha256"],
        "pair": f"{req.pair.get('base')}/{req.pair.get('quote')}",
        "family": result.selected.family,
        "robust": result.spec["backtest"]["robustness"]["robust"],
        "tearsheet_local_path": result.tearsheet_path,
    }
    return deliverable, meta
