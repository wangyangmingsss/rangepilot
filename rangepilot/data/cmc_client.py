"""CoinMarketCap data layer.

Three access paths, one normalized output (a pandas OHLCV frame with columns
open/high/low/close/volume_quote and a UTC DatetimeIndex):

* REST with API key      — primary for backfills (`/v4/dex/pairs/ohlcv/historical`,
                           documented by CMC as built for backtesting).
* x402 pay-per-request   — optional keyless path (see x402_client.py).
* Local CSV              — offline/reproducibility channel; the bundled demo
                           and the test suite run entirely on CSVs.

[VERIFY-DAY1] The exact v4 DEX param names (network slug vs id, pair vs
contract address, interval enum) are confirmed by scripts/day1_smoke_tests.py,
which prints raw payloads; `extra_params` lets you adapt without code changes.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from ..config import CMC_REST_BASE, CMC_ENDPOINTS, ENV
from .cache import DiskCache


class CMCError(RuntimeError):
    pass


class CMCClient:
    def __init__(self, api_key: str | None = None, cache_dir: str = ".cmc_cache",
                 timeout: int = 30, min_interval_s: float = 0.7):
        self.api_key = api_key or ENV.cmc_api_key
        self.cache = DiskCache(cache_dir)
        self.timeout = timeout
        self.min_interval_s = min_interval_s
        self._last_call = 0.0

    # -- low level -----------------------------------------------------------
    def _get(self, path: str, params: dict) -> dict:
        if not self.api_key:
            raise CMCError("CMC_API_KEY not set (offline mode: use load_csv)")
        wait = self.min_interval_s - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{CMC_REST_BASE}{path}?{qs}"
        req = urllib.request.Request(url, headers={
            "X-CMC_PRO_API_KEY": self.api_key,
            "Accept": "application/json",
        })
        self._last_call = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:  # plan gating shows up here (401/403/429)
            body = e.read().decode(errors="replace")[:500]
            raise CMCError(f"HTTP {e.code} on {path}: {body}") from e
        status = payload.get("status", {})
        if status.get("error_code") not in (0, None):
            raise CMCError(f"CMC error {status.get('error_code')}: {status.get('error_message')}")
        return payload

    # -- DEX OHLCV -------------------------------------------------------------
    def dex_ohlcv_historical(self, *, contract_address: str | None = None,
                             pair_id: str | None = None,
                             network_slug: str = "bsc",
                             interval: str = "1h",
                             time_start: str | None = None,
                             time_end: str | None = None,
                             count: int | None = 500,
                             extra_params: dict | None = None,
                             use_cache: bool = True) -> pd.DataFrame:
        params = {"contract_address": contract_address, "pair_id": pair_id,
                  "network_slug": network_slug, "interval": interval,
                  "time_start": time_start, "time_end": time_end, "count": count}
        if extra_params:
            params.update(extra_params)
        cache_key = ("dex_ohlcv", json.dumps(params, sort_keys=True))
        if use_cache:
            hit = self.cache.get(cache_key)
            if hit is not None:
                return normalize_ohlcv(hit)
        payload = self._get(CMC_ENDPOINTS["dex_ohlcv_historical"], params)
        self.cache.put(cache_key, payload)
        return normalize_ohlcv(payload)

    def dex_quotes_latest(self, *, contract_address: str,
                          network_slug: str = "bsc",
                          extra_params: dict | None = None) -> dict:
        params = {"contract_address": contract_address, "network_slug": network_slug}
        if extra_params:
            params.update(extra_params)
        return self._get(CMC_ENDPOINTS["dex_quotes_latest"], params)

    # -- Hub pre-computed indicators ------------------------------------------
    def fetch_hub_indicators(self) -> dict:
        """[VERIFY-DAY1] Map the Hub's pre-computed indicators (market regime /
        liquidity / risk flags) into {"market_regime": .., "risk_flag": ..}.
        The MCP tool surface is the canonical path; this REST placeholder keeps
        the interface stable until Day-1 verification pins the exact source.
        """
        raise CMCError("Hub indicators not wired yet — run day1_smoke_tests and "
                       "fill rangepilot/data/cmc_client.py::fetch_hub_indicators")


# -- normalization -------------------------------------------------------------

CANDIDATE_KEYS = {
    "open": ("open",), "high": ("high",), "low": ("low",), "close": ("close",),
    "volume_quote": ("volume", "volume_24h", "volume_quote", "quote_volume"),
    "ts": ("time_open", "timestamp", "time", "time_close"),
}


def normalize_ohlcv(payload: dict) -> pd.DataFrame:
    """Best-effort normalization of CMC v4 DEX OHLCV payload shapes."""
    data = payload.get("data", payload)
    quotes = None
    if isinstance(data, dict):
        for key in ("quotes", "ohlcv", "items"):
            if key in data:
                quotes = data[key]
                break
        if quotes is None and len(data) == 1:
            inner = next(iter(data.values()))
            if isinstance(inner, dict):
                quotes = inner.get("quotes") or inner.get("ohlcv")
            elif isinstance(inner, list):
                quotes = inner
    elif isinstance(data, list):
        quotes = data
    if not quotes:
        raise CMCError("could not locate OHLCV array in payload — inspect raw "
                       "response via day1_smoke_tests")

    rows = []
    for q in quotes:
        flat = dict(q)
        if isinstance(q.get("quote"), dict):  # nested quote.USD style
            inner = q["quote"]
            inner = inner.get("USD", inner)
            flat.update(inner)
        row = {}
        for col, keys in CANDIDATE_KEYS.items():
            for k in keys:
                if k in flat and flat[k] is not None:
                    row[col] = flat[k]
                    break
        rows.append(row)
    df = pd.DataFrame(rows)
    if "ts" not in df.columns:
        raise CMCError("no timestamp field recognized in OHLCV payload")
    df["ts"] = pd.to_datetime(df["ts"], utc=True, format="mixed")
    df = df.set_index("ts").sort_index()
    for c in ("open", "high", "low", "close", "volume_quote"):
        if c not in df.columns:
            raise CMCError(f"OHLCV payload missing '{c}' after normalization")
        df[c] = df[c].astype(float)
    return df[["open", "high", "low", "close", "volume_quote"]]


def load_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    ts_col = "ts" if "ts" in df.columns else df.columns[0]
    df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
    df = df.set_index(ts_col).sort_index()
    need = ["open", "high", "low", "close", "volume_quote"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing columns {missing}")
    return df[need].astype(float)
