"""
Pod Ballast: defensive/hedged sleeve. Continuous stress from ballast_weight:
stress=0 -> pure long book; stress=1 -> 50% cash (implicit), 30% low-vol longs, 20% SMH short.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANNUALIZATION = 252 ** 0.5


class PodBallast:
    """Defensive sleeve. stress_factor from ballast_weight interpolates long-only vs defensive (cash + low-vol + SMH short)."""

    def generate_weights(
        self,
        scores: pd.Series,
        prices_dict: dict,
        regime_status: dict,
        config: dict,
    ) -> pd.Series:
        bottom_n_defensive = config.get("bottom_n_defensive", 5)
        top_n_ballast = config.get("top_n_ballast", 8)

        # Fallback: empty scores or prices -> equal-weight top_n or empty
        scores_clean = scores.dropna() if scores is not None else pd.Series(dtype=float)
        if scores_clean.empty or not prices_dict:
            if scores_clean.empty:
                return pd.Series(dtype=float)
            top = scores_clean.sort_values(ascending=False).head(top_n_ballast).index.tolist()
            if not top:
                return pd.Series(dtype=float)
            n = len(top)
            return pd.Series({t: 1.0 / n for t in top})

        # Continuous stress from ballast_weight (injected by run_execution Task 2)
        ballast_weight = float(config.get("ballast_weight", 0.20))
        ballast_weight = max(0.20, min(0.50, ballast_weight))
        stress_factor = (ballast_weight - 0.20) / 0.30  # 0 at 0.20, 0.5 at 0.35, 1.0 at 0.50

        cash_weight = stress_factor * 0.50
        smh_short_weight = stress_factor * 0.20 if stress_factor > 0.10 else 0.0
        long_book_weight = 1.0 - cash_weight - smh_short_weight

        # Long book: low-vol selection (same logic as former BEAR branch)
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

        n_def = len(defensive_tickers)
        weights = {}
        for t in defensive_tickers:
            weights[t] = long_book_weight / n_def

        # SMH short only if material
        if smh_short_weight > 0.01 and "SMH" in prices_dict and prices_dict["SMH"] is not None and not prices_dict["SMH"].empty:
            weights["SMH"] = -smh_short_weight

        # Cash is implicit (not added to Series); aggregator does not get a CASH ticker.
        return pd.Series(weights)
