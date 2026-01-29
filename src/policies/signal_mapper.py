"""
Signal Mapper - Convert continuous signals to discrete trades
Ported from wealth_signal_mvp_v1/core/policies/target_to_trade_mapper.py
"""
import pandas as pd
from typing import Optional
from src.utils.logger import setup_logger

logger = setup_logger()


def map_signals_to_trades(
    signal_series: pd.Series,
    upper_threshold: float = 0.02,
    lower_threshold: float = -0.02,
    regime_series: Optional[pd.Series] = None
) -> pd.Series:
    """
    Convert a continuous signal series into discrete trade actions,
    with optional macro regime suppression.

    Args:
        signal_series: Predicted returns (e.g., from model)
        upper_threshold: Signal above this → BUY (default: 0.02 = 2%)
        lower_threshold: Signal below this → SELL (default: -0.02 = -2%)
        regime_series: Optional regime labels (must align on index).
                      Suppresses trades in hostile regimes.

    Returns:
        Series: Trade actions: +1 (buy), -1 (sell), 0 (hold or suppressed)
    """
    if not isinstance(signal_series, pd.Series):
        raise ValueError("Input must be a pandas Series")

    def decide(signal):
        if signal >= upper_threshold:
            return 1  # Buy
        elif signal <= lower_threshold:
            return -1  # Sell
        else:
            return 0   # Hold

    trades = signal_series.apply(decide).rename("trade_signal")

    if regime_series is not None:
        # Apply regime-based suppression
        hostile = ["recession", "volatile", "unknown"]
        trades = trades.copy()
        for dt in trades.index:
            if dt in regime_series.index:
                regime = regime_series.loc[dt]
                if regime in hostile:
                    trades.loc[dt] = 0
                    logger.debug(f"Trade suppressed at {dt} due to {regime} regime")

    return trades
