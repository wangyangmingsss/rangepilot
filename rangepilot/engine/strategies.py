"""RangePilot strategy families.

A strategy is *parameters*, not code: the backtester executes a generic
range-policy loop, and each family below just decides
  (a) range half-width as a function of regime,
  (b) when to rebalance,
  (c) when to stand aside (pause) entirely.

Families
--------
S1  static_range      width = k * sigma (entry snapshot), rebalance on exit
S2  regime_adaptive   width multiplier per vol regime, rebalance on exit
S3  stress_pause      S2 + fully exit to quote during trend_stress / high vol

Risk profiles map user intent -> default parameterization.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

REBALANCE_TRIGGERS = ("range_exit", "edge_band")


@dataclass
class StrategyParams:
    family: str                       # "static_range" | "regime_adaptive" | "stress_pause"
    k_sigma: float = 1.5              # half-width = k * sigma_horizon
    horizon_hours: float = 72.0       # vol horizon used to size the range
    regime_width_mult: dict = field(default_factory=lambda: {"low": 0.8, "mid": 1.0, "high": 1.5})
    rebalance_trigger: str = "range_exit"
    edge_band: float = 0.0            # for edge_band trigger: rebalance when price within
                                      # `edge_band` fraction of a range edge
    cooldown_bars: int = 6            # min bars between rebalances
    pause_in_stress: bool = False     # S3: exit to quote when trend_stress
    pause_in_high_vol: bool = False   # S3 optional: also pause in "high" regime
    max_rebalances_per_day: int = 8

    def to_dict(self) -> dict:
        return asdict(self)


RISK_PROFILES = {
    # wider ranges, fewer touches
    "conservative": dict(k_sigma=2.2, cooldown_bars=12, edge_band=0.0,
                         regime_width_mult={"low": 1.0, "mid": 1.3, "high": 1.8}),
    "balanced": dict(k_sigma=1.5, cooldown_bars=6,
                     regime_width_mult={"low": 0.8, "mid": 1.0, "high": 1.5}),
    # tighter ranges, more fees, more rebalancing
    "aggressive": dict(k_sigma=1.0, cooldown_bars=3,
                       regime_width_mult={"low": 0.6, "mid": 0.85, "high": 1.2}),
}


def make_strategy(family: str, risk: str = "balanced", **overrides) -> StrategyParams:
    if family not in ("static_range", "regime_adaptive", "stress_pause"):
        raise ValueError(f"unknown family: {family}")
    if risk not in RISK_PROFILES:
        raise ValueError(f"unknown risk profile: {risk}")
    base = dict(RISK_PROFILES[risk])
    base.update(overrides)
    params = StrategyParams(family=family, **base)
    if family == "static_range":
        params.regime_width_mult = {"low": 1.0, "mid": 1.0, "high": 1.0}
        params.pause_in_stress = False
        params.pause_in_high_vol = False
    elif family == "regime_adaptive":
        params.pause_in_stress = False
        params.pause_in_high_vol = False
    elif family == "stress_pause":
        params.pause_in_stress = True
    return params


def candidate_grid(risk: str = "balanced") -> list[StrategyParams]:
    """Default candidate set evaluated by the generator: 3 families x k grid.

    A plateau across neighbouring k values (not a single spike) is required
    before a candidate can be selected — anti-overfitting discipline.
    """
    ks = {"conservative": (1.8, 2.2, 2.6),
          "balanced": (1.2, 1.5, 1.9),
          "aggressive": (0.8, 1.0, 1.3)}[risk]
    out: list[StrategyParams] = []
    for fam in ("static_range", "regime_adaptive", "stress_pause"):
        for k in ks:
            out.append(make_strategy(fam, risk, k_sigma=k))
    return out
