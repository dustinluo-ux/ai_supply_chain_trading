# src/risk/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
import pandas as pd


@dataclass(frozen=True)
class TargetPortfolio:
    """Output of Alpha Lane. Hedge-blind: always a 100% long book."""
    as_of: pd.Timestamp
    weights: dict[str, Decimal]        # ticker → weight; sum ≈ 1.0
    scores: dict[str, float]           # raw alpha scores, for audit
    construction_meta: dict            # top_n, layer weights, ml_blend, etc.


@dataclass(frozen=True)
class OverlayOrder:
    """A single short futures contract instruction."""
    symbol: str                        # e.g. "MNQ", "MES"
    contracts: int                     # negative = short
    notional_usd: Decimal
    reason: str                        # e.g. "beta_gap=0.30 × nav"


@dataclass(frozen=True)
class RiskConstraints:
    """Output of Risk Lane. Tells Planner how much of Alpha to express."""
    as_of: pd.Timestamp
    beta_cap: Decimal                  # 1.0 = full, 0.0 = flatten all
    position_scale: Decimal            # multiply all Alpha weights by this
    stop_loss_active: bool
    margin_headroom_pct: Decimal       # 1.0 = no constraint; <1.0 = margin tight
    audit_log: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FinalExecutionPlan:
    """Output of ExecutionPlanner. The only thing IBExecutor sees."""
    as_of: pd.Timestamp
    long_orders: dict[str, Decimal]    # ticker → final target weight (scaled)
    overlay_orders: list[OverlayOrder]
    audit_log: list[str] = field(default_factory=list)
