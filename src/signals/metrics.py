"""
Regime-aware risk/return metrics. Sortino ratio using downside deviation only
so BULL strategies are not throttled by upside volatility.
"""
from __future__ import annotations

from typing import Union

import numpy as np

ArrayLike = Union[list[float], np.ndarray]


def calculate_regime_sortino(
    returns: ArrayLike,
    risk_free_rate: float = 0.0,
) -> float:
    """
    Sortino ratio: (R_p - R_f) / sigma_d, where sigma_d is the downside deviation.

    Downside deviation penalizes only returns below the risk-free rate (or zero):
    sigma_d = sqrt(mean(min(r - R_f, 0)^2)).
    For BULL regimes this strictly ignores upside volatility so the Strategy Selector
    does not mistakenly throttle high-performing bull strategies.
    """
    arr = np.asarray(returns, dtype=float).ravel()
    if arr.size == 0:
        return 0.0
    r_p = float(np.mean(arr))
    excess = arr - risk_free_rate
    # Only downside: values below zero (excess return negative)
    downside = np.minimum(excess, 0.0)
    sq_downside = downside ** 2
    n = arr.size
    if n < 2:
        return 0.0
    sigma_d_sq = np.mean(sq_downside)
    if sigma_d_sq <= 0:
        # No downside volatility: return a high ratio (don't penalize upside)
        return 10.0 if (r_p - risk_free_rate) > 0 else 0.0
    sigma_d = float(np.sqrt(sigma_d_sq))
    if sigma_d <= 0:
        return 0.0
    sortino = (r_p - risk_free_rate) / sigma_d
    return float(sortino)
