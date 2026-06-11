"""Trust Wallet Agent Kit (TWAK) integration — the safety/executability layer.

Two pieces:
1. Token risk screening before any pool enters a strategy universe
   (market-making into a honeypot is donating money).
2. An *executability report* embedded in every spec: which spec actions map to
   TWAK-native skills (swaps / automations) vs generic contract calls that
   need WalletConnect proposal or an external executor.

Honesty note: the exact TWAK security/risk-scoring HTTP contract must be wired
on Day 1 from https://portal.trustwallet.com (TWAK exposes MCP + REST).
Until TWAK_API_BASE / TWAK_API_KEY are configured, screening degrades to an
explicitly-labelled offline heuristic stub so the pipeline never silently
pretends a real screen happened.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, asdict

from ..config import ENV


@dataclass
class RiskReport:
    token_address: str
    provider: str  # "twak" | "offline-heuristic-stub"
    risk_level: str  # "low" | "medium" | "high" | "unknown"
    flags: list
    raw: dict

    def to_dict(self) -> dict:
        return asdict(self)


class TWAKRiskClient:
    """Live client. [VERIFY-DAY1] endpoint path & schema from the TWAK portal."""

    def __init__(
        self, base: str | None = None, api_key: str | None = None, timeout: int = 15
    ):
        self.base = (base or ENV.twak_api_base).rstrip("/")
        self.api_key = api_key or ENV.twak_api_key
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.base and self.api_key)

    def screen_token(self, token_address: str, chain_id: int = 56) -> RiskReport:
        if not self.configured:
            raise RuntimeError("TWAK not configured (set TWAK_API_BASE / TWAK_API_KEY)")
        url = f"{self.base}/v1/security/token-risk?chain_id={chain_id}&address={token_address}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                data = json.loads(resp.read().decode())
            level = str(
                data.get("risk_level", data.get("riskLevel", "unknown"))
            ).lower()
            flags = data.get("flags", data.get("riskFactors", []))
            return RiskReport(token_address, "twak", level, list(flags), data)
        except Exception as e:
            # Graceful degradation to offline stub on HTTP 403/500 or network errors
            return RiskReport(
                token_address,
                "twak-offline-fallback",
                "unknown",
                [f"API error: {e}", "fallback to offline heuristic"],
                {
                    "note": "TWAK API failed; degraded to offline stub for pipeline continuity"
                },
            )


class OfflineHeuristicScreen:
    """Explicitly-labelled stub for offline demos.

    It does NOT detect honeypots. It only sanity-checks address shape and lets
    the pipeline run end-to-end with `risk_level="unknown"` so the spec's
    validation block truthfully says no real screen was performed.
    """

    provider = "offline-heuristic-stub"

    def screen_token(self, token_address: str, chain_id: int = 56) -> RiskReport:
        ok = (
            isinstance(token_address, str)
            and token_address.startswith("0x")
            and len(token_address) == 42
        )
        flags = [] if ok else ["malformed_address"]
        return RiskReport(
            token_address,
            self.provider,
            "unknown" if ok else "high",
            flags,
            {"note": "offline stub — run live TWAK screen before execution"},
        )


def get_screener():
    live = TWAKRiskClient()
    return live if live.configured else OfflineHeuristicScreen()
