"""
Intent: dataclass for execution (tickers, weights, mode).
Used by PortfolioEngine.build() and consumed by backtest (signals_df row)
or weekly rebalance (optimal_weights_series -> PositionManager).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Intent:
    """Target portfolio for a single rebalance date."""

    tickers: list[str]
    weights: dict[str, float]  # ticker -> weight (sum 1.0 when trading; 0.0 when CASH_OUT)
    mode: str  # "backtest" | "execution"
    metadata: Optional[dict] = None  # optional: regime_state, action, etc. for logging
