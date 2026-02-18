"""
ATR-based position sizing (Stage 4).

Formula: Position $ = (Equity * risk_pct) / (ATR * atr_multiplier)
Weight = (risk_pct * price) / (ATR * atr_multiplier), then normalized to sum = target_exposure.

Config: config/trading_config.yaml → position_sizing.risk_pct, position_sizing.atr_multiplier.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Defaults if config missing (per trading_config.yaml)
DEFAULT_RISK_PCT = 0.02
DEFAULT_ATR_MULTIPLIER = 2.0


def compute_atr_series(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    True Range then ATR(period). Returns series aligned to close index.
    """
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=1).mean()
    return atr


def compute_weights(
    tickers: list[str],
    atr_per_share: dict[str, float],
    prices: dict[str, float],
    risk_pct: float = DEFAULT_RISK_PCT,
    atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
    target_exposure: float = 1.0,
) -> dict[str, float]:
    """
    ATR-based position weights: weight_i ∝ (risk_pct * price_i) / (ATR_i * atr_multiplier).

    Normalized so sum(weights) = target_exposure. Missing ATR or price use floor to avoid div-by-zero.

    Args:
        tickers: Ordered list of tickers to size.
        atr_per_share: Ticker -> ATR in dollars per share (as of rebalance).
        prices: Ticker -> price per share (as of rebalance).
        risk_pct: Fraction of equity risked per position (e.g. 0.02 = 2%).
        atr_multiplier: Stop distance in ATRs.
        target_exposure: Sum of weights (1.0 = full invest, 0.0 = cash).

    Returns:
        dict ticker -> weight, sum = target_exposure. All tickers in universe get a key (0 if not in tickers).
    """
    if not tickers or target_exposure <= 0:
        return {t: 0.0 for t in tickers}

    denom_mult = max(atr_multiplier, 1e-8)
    raw_weights: list[tuple[str, float]] = []
    for t in tickers:
        atr = atr_per_share.get(t) or 0.0
        price = prices.get(t) or 0.0
        if price <= 0:
            continue
        atr_safe = max(atr, 1e-8)
        # weight ∝ (risk_pct * price) / (ATR * atr_multiplier)
        w = (risk_pct * price) / (atr_safe * denom_mult)
        if w > 0:
            raw_weights.append((t, w))

    if not raw_weights:
        return {t: 0.0 for t in tickers}

    total = sum(w for _, w in raw_weights)
    if total <= 0:
        return {t: 0.0 for t in tickers}

    scale = target_exposure / total
    weights = {t: (w * scale) for t, w in raw_weights}
    for t in tickers:
        weights.setdefault(t, 0.0)
    return weights


def get_sizing_params_from_config(config: Any) -> tuple[float, float]:
    """
    Read risk_pct and atr_multiplier from ConfigManager or dict.

    Returns (risk_pct, atr_multiplier). Uses defaults if key missing.
    """
    try:
        risk = float(config.get_param("trading_config.position_sizing.risk_pct", DEFAULT_RISK_PCT))
    except (AttributeError, KeyError, TypeError):
        risk = DEFAULT_RISK_PCT
    try:
        mult = float(config.get_param("trading_config.position_sizing.atr_multiplier", DEFAULT_ATR_MULTIPLIER))
    except (AttributeError, KeyError, TypeError):
        mult = DEFAULT_ATR_MULTIPLIER
    return risk, mult
