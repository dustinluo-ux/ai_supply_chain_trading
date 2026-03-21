from __future__ import annotations

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm


def get_put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes European put price per share."""
    S = float(S)
    K = float(K)
    T = float(T)
    r = float(r)
    sigma = float(sigma)
    if T <= 0.0 or sigma <= 0.0 or S <= 0.0 or K <= 0.0:
        return float(max(K - S, 0.0))
    d1 = (np.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    put = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return float(max(put, 0.0))


def find_target_delta_strike(S: float, T: float, r: float, sigma: float, target_delta: float = 0.20) -> float:
    """Find strike where |put delta| equals target_delta (e.g. 0.20 for 20-delta, 0.10 for 10-delta)."""
    S = float(S)
    T = float(T)
    r = float(r)
    sigma = float(sigma)
    target_delta = float(target_delta)
    if T <= 0.0 or sigma <= 0.0 or S <= 0.0:
        return float(S)

    def objective(K: float) -> float:
        d1 = (np.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * np.sqrt(T))
        put_delta = -norm.cdf(-d1)
        return put_delta + target_delta

    lo = S * 0.50
    hi = S * 0.999
    try:
        return float(brentq(objective, lo, hi, maxiter=200))
    except Exception:
        return float(S * (1.0 - target_delta))


# Keep original name as alias for backward compatibility
def find_20_delta_strike(S: float, T: float, r: float, sigma: float) -> float:
    return find_target_delta_strike(S, T, r, sigma, target_delta=0.20)


def estimate_smh_put_cost(
    S: float,
    vix_level: float,
    T: float = 45 / 365,
    r: float = 0.05,
    target_delta: float = 0.20,
) -> tuple[float, float, float]:
    """
    Estimate SMH put cost from VIX proxy volatility.
    sigma = (vix / 100) * 1.5, fallback sigma=0.35 for invalid VIX.
    target_delta: absolute put delta (e.g. 0.20 = 20-delta, 0.10 = 10-delta).
    """
    S = float(S)
    vix_level = float(vix_level) if vix_level is not None else np.nan
    if not np.isfinite(vix_level) or vix_level <= 0.0:
        sigma = 0.35
    else:
        sigma = float((vix_level / 100.0) * 1.5)
    K = find_target_delta_strike(S=S, T=T, r=r, sigma=sigma, target_delta=target_delta)
    put_price = get_put_price(S=S, K=K, T=T, r=r, sigma=sigma)
    return float(put_price), float(K), float(sigma)

