"""
Pod Ballast: defensive/hedged sleeve. BEAR → 50% cash, 30% defensive longs, 20% SMH short.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANNUALIZATION = 252 ** 0.5


class PodBallast:
    """Defensive sleeve. BEAR: 50% cash, 30% low-vol longs, 20% SMH short. Non-BEAR: equal-weight top_n."""

    def generate_weights(
        self,
        scores: pd.Series,
        prices_dict: dict,
        regime_status: dict,
        config: dict,
    ) -> pd.Series:
        is_bear = (
            regime_status.get("regime") == "EMERGENCY"
            or regime_status.get("spy_below_sma", False) is True
        )
        bottom_n_defensive = config.get("bottom_n_defensive", 5)
        top_n_ballast = config.get("top_n_ballast", 8)

        if is_bear:
            vol_20d = {}
            for t in scores.index:
                if t not in prices_dict or prices_dict[t] is None or prices_dict[t].empty:
                    continue
                df = prices_dict[t]
                if "close" not in df.columns:
                    continue
                close = df["close"]
                if getattr(close, "ndim", 1) > 1:
                    close = close.iloc[:, 0]
                ret = close.pct_change(fill_method=None).dropna()
                if len(ret) < 10:
                    continue
                ret = ret.iloc[-20:]
                vol_20d[t] = float(ret.std() * ANNUALIZATION)
            defensive_tickers = sorted(vol_20d.keys(), key=lambda x: vol_20d[x])[:bottom_n_defensive]
            if not defensive_tickers:
                defensive_tickers = scores.index.tolist()[:bottom_n_defensive]
            if not defensive_tickers:
                defensive_tickers = list(scores.index)[:1]

            weights = {}
            n_def = len(defensive_tickers)
            for t in defensive_tickers:
                weights[t] = 0.30 / n_def

            if "SMH" in prices_dict and prices_dict["SMH"] is not None and not prices_dict["SMH"].empty:
                weights["SMH"] = -0.20
            # else: 20% stays as cash (implicit); long weights sum to 0.30, net = 0.10 or 0.30

            return pd.Series(weights)
        else:
            scores_clean = scores.dropna()
            if scores_clean.empty:
                return pd.Series(dtype=float)
            top = scores_clean.sort_values(ascending=False).head(top_n_ballast).index.tolist()
            if not top:
                return pd.Series(dtype=float)
            n = len(top)
            return pd.Series({t: 1.0 / n for t in top})
