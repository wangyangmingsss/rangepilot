#!/usr/bin/env python3
"""One-click offline demo (no network, no API keys, deterministic).

    python scripts/run_demo.py

Runs the full RangePilot pipeline on the bundled seed-fixed sample market and
writes the three judge-facing artifacts to examples/demo_output/:
  * rangepilot_WBNB_USDT_spec.json   — the StrategySpec deliverable
  * rangepilot_WBNB_USDT_tearsheet.png
  * rangepilot_WBNB_USDT_report.md
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rangepilot.skill.runner import GenerationRequest, generate  # noqa: E402


def main() -> int:
    sample = ROOT / "data" / "sample" / "WBNB_USDT_1h_sample.csv"
    if not sample.exists():
        print("sample data missing — run: python scripts/gen_sample_data.py")
        return 1
    req = GenerationRequest(
        pair={"base": "WBNB", "quote": "USDT",
              "base_address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
              "quote_address": "0x55d398326f99059fF775485246999027B3197955",
              "pool_address": None},
        capital_quote=5000.0,
        risk="balanced",
        fee_tier=2500,
        csv_path=str(sample),
        out_dir=str(ROOT / "examples" / "demo_output"),
    )
    res = generate(req)
    print(json.dumps({
        "spec": res.spec_path,
        "tearsheet": res.tearsheet_path,
        "selected": {"family": res.selected.family, "k_sigma": res.selected.k_sigma},
        "is_metrics": res.is_result.metrics,
        "oos_metrics": res.oos_metrics,
        "robust": res.spec["backtest"]["robustness"]["robust"],
        "validation": res.spec["validation"]["status"],
        "spec_sha256": res.spec["spec_sha256"],
    }, indent=2))
    print("\nDemo artifacts written to examples/demo_output/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
