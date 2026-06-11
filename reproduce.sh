#!/usr/bin/env bash
# One-click reproducibility: tests -> deterministic demo -> artifact hashes.
# No network, no keys. Exit code 0 == everything reproduced.
set -euo pipefail
cd "$(dirname "$0")"

echo "== RangePilot reproduce =="
python3 --version

echo; echo "-- [1/3] test suite --"
python3 tests/run_all.py

echo; echo "-- [2/3] deterministic offline demo --"
python3 scripts/run_demo.py

echo; echo "-- [3/3] artifact hashes --"
SPEC="examples/demo_output/rangepilot_WBNB_USDT_spec.json"
python3 - <<'EOF'
import hashlib, json
p = "examples/demo_output/rangepilot_WBNB_USDT_spec.json"
spec = json.load(open(p))
print("spec file        :", p)
print("file sha256      :", hashlib.sha256(open(p,'rb').read()).hexdigest())
print("research_sha256  :", spec["research_sha256"], "(run-stable: compare across machines/runs)")
print("spec_sha256      :", spec["spec_sha256"], "(full-document hash; the APEX deliverable content hash — unique per delivery)")
print("data sha256      :", spec["data_lineage"]["ohlcv"]["sha256"], "(bundled sample CSV)")
print("robust           :", spec["backtest"]["robustness"]["robust"])
print("selection status :", spec["data_lineage"]["selection"]["status"])
EOF

echo; echo "Reproduce complete. Compare research_sha256 across machines/runs (spec_sha256 varies by design: it timestamps each delivery)."
