#!/usr/bin/env python3
"""Client-side walkthrough: hiring RangePilot as an on-chain APEX agent.

Two layers, honestly separated:

A) HTTP handshake (runs right now against a local server, no chain needed):
     GET  /health      — server alive
     GET  /status      — agent wallet, service price, payment token
     POST /negotiate   — propose terms, receive a price quote (hash-anchored)

B) On-chain lifecycle (BSC testnet; needs a funded client wallet):
     create_job -> set_budget(agreed price) -> approve U token -> fund
     -> POST /job/execute -> GET /job/{id}/response -> UMA liveness -> settle
   The on-chain half follows the bnbagent SDK's official `client-workflow`
   example; this script prints the exact next commands rather than half-
   reimplementing signed transactions. [VERIFY-DAY1: run end-to-end once]

Usage:
    # terminal 1
    python -m rangepilot.cli serve-apex --port 8000
    # terminal 2
    python scripts/apex_client_demo.py --base-url http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_REQUEST = ROOT / "examples" / "sample_job_request.json"


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as r:  # nosec B310
        return json.loads(r.read().decode())


def _post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310
        return json.loads(r.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    print("== A) HTTP handshake ==")
    try:
        print("/health  ->", json.dumps(_get(f"{base}/health"))[:200])
        status = _get(f"{base}/status")
        print("/status  ->", json.dumps(status, indent=2)[:600])
    except urllib.error.URLError as e:
        print(f"server not reachable at {base}: {e}\n"
              "start it with: python -m rangepilot.cli serve-apex --port 8000")
        return 1

    job_request = json.loads(SAMPLE_REQUEST.read_text())
    job_request.pop("_comment", None)
    negotiate_body = {
        "service_type": "strategy-spec-generation",
        "description": json.dumps(job_request),
        "quality_standards": "spec must include OOS metrics + robustness gates",
        "deliverables": "RangePilot StrategySpec JSON (canonical, sha256-anchored)",
    }
    try:
        quote = _post(f"{base}/negotiate", negotiate_body)
        print("/negotiate ->", json.dumps(quote, indent=2)[:800])
    except urllib.error.HTTPError as e:
        print(f"/negotiate returned HTTP {e.code}: {e.read().decode()[:300]}\n"
              "(schema may differ by SDK version — see bnbagent/apex/README.md)")

    print("\n== B) On-chain lifecycle (BSC testnet) — next commands ==")
    print(f"""
1. fund a CLIENT wallet:  tBNB  https://www.bnbchain.org/en/testnet-faucet
                          U     https://united-coin-u.github.io/u-faucet/
2. clone the SDK examples and run the official client workflow:
     git clone https://github.com/bnb-chain/bnbagent-sdk
     cd bnbagent-sdk/examples/client-workflow   # follow its README
   - provider address  = "agent" field from /status above
   - job description   = contents of examples/sample_job_request.json
   - budget            = service_price from /status (set_budget + approve + fund)
3. trigger execution:    POST {base}/job/execute   {{"jobId": <id>}}
4. fetch deliverable:    GET  {base}/job/<id>/response   (spec JSON; hash on-chain)
5. after the 30-min UMA liveness window, settle -> agent is paid from escrow.

The deliverable's `spec_sha256` equals the on-chain content hash: the research
artifact itself is escrow-verified. That is the whole point.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
