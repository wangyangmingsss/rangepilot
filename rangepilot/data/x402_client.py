"""Optional x402 pay-per-request access (keyless; $0.01 USDC on Base per call).

Track 2 marks x402 as optional. We keep a thin, dependency-optional wrapper:
if the `x402` python package is installed and X402_PRIVATE_KEY is set, calls
route through the paid endpoint; otherwise CMCClient (API key) or CSVs are
used. The Day-1 smoke test exercises one paid call end-to-end so the demo can
show a self-funding data fetch.

[VERIFY-DAY1] confirm the exact x402 route list for v4 DEX endpoints; routes
known so far: dex search + pair quotes (per CMC AI-integration docs).
"""
from __future__ import annotations

import os


class X402NotAvailable(RuntimeError):
    pass


def fetch_via_x402(path: str, params: dict) -> dict:
    try:
        from x402.clients.requests import x402_requests  # type: ignore
        from eth_account import Account  # type: ignore
    except Exception as e:  # pragma: no cover
        raise X402NotAvailable(
            "pip install x402 eth-account, and set X402_PRIVATE_KEY (Base wallet "
            "holding a little USDC) to enable keyless pay-per-request access"
        ) from e
    pk = os.getenv("X402_PRIVATE_KEY", "")
    if not pk:
        raise X402NotAvailable("X402_PRIVATE_KEY not set")
    account = Account.from_key(pk)
    session = x402_requests(account)
    from ..config import CMC_X402_BASE
    resp = session.get(f"{CMC_X402_BASE}{path}", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()
