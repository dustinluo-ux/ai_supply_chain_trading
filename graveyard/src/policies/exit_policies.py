"""
Exit Policies - Trailing stops and threshold-based exits
Ported from wealth_signal_mvp_v1/core/policies/exit_policies.py
"""
import pandas as pd
from typing import Optional


class FixedThresholdPolicy:
    """Horizon-style fixed threshold mapper. Turns predicted values into discrete signals (+1, 0, -1)."""

    def __init__(self, upper: float, lower: float, regime_series: Optional[pd.Series] = None):
        self.upper = upper
        self.lower = lower
        self.regime_series = regime_series

    def apply(self, predicted_series: pd.Series) -> pd.Series:
        signals = pd.Series(0, index=predicted_series.index)
        signals[predicted_series >= self.upper] = 1
        signals[predicted_series <= self.lower] = -1
        if self.regime_series is not None:
            aligned = self.regime_series.reindex(signals.index).fillna(1)
            signals = signals * aligned
        return signals


class TrailingStopPolicy:
    """Stateful policy: enters when prediction > threshold, exits when trailing stop or time stop hit."""

    def __init__(self, trail_pct: float = 0.05, time_stop: Optional[int] = None, entry_threshold: float = 0.0):
        self.trail_pct = trail_pct
        self.time_stop = time_stop
        self.entry_threshold = entry_threshold

    def apply(self, predicted_series: pd.Series, price: pd.Series) -> pd.Series:
        predicted_series = predicted_series.reindex(price.index).ffill()
        pos = pd.Series(0, index=price.index)
        in_pos = False
        entry_idx = None
        peak_price = None
        for t, dt in enumerate(price.index):
            px = price.iloc[t]
            pred_val = predicted_series.iloc[t]
            if not in_pos:
                if pred_val > self.entry_threshold:
                    in_pos = True
                    entry_idx = t
                    peak_price = px
                    pos.iloc[t] = 1
                else:
                    pos.iloc[t] = 0
            else:
                if peak_price is None:
                    peak_price = px
                peak_price = max(peak_price, px)
                dd = (px / peak_price) - 1.0
                time_up = self.time_stop is not None and (t - entry_idx) >= self.time_stop
                if dd <= -self.trail_pct or time_up:
                    in_pos = False
                    entry_idx = None
                    peak_price = None
                    pos.iloc[t] = 0
                else:
                    pos.iloc[t] = 1
        return pos
