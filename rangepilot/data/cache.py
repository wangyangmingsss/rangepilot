"""Tiny JSON disk cache for API payloads (keeps Day-1 iteration cheap and
makes every backfill reproducible: cached payloads can be committed for the
judges' one-click repro)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class DiskCache:
    def __init__(self, root: str = ".cmc_cache"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key) -> Path:
        h = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:24]
        return self.root / f"{h}.json"

    def get(self, key):
        p = self._path(key)
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                return None
        return None

    def put(self, key, payload) -> None:
        self._path(key).write_text(json.dumps(payload))
