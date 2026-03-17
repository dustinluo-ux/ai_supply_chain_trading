"""
Pod Core: long-only HRP + Alpha Tilt. Max gross 1.0.
Source: long-side logic from src/portfolio/long_short_optimizer.build_long_short_weights.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

EWMA_SPAN = 38  # lambda=0.94
VOL_FLOOR = 0.01
LOOKBACK_DAYS = 60
MIN_OBS = 30


class PodCore:
    """Long-only HRP + Alpha Tilt pod. Weights sum to 1.0."""

    def generate_weights(
        self,
        scores: pd.Series,
        prices_dict: dict,
        regime_status: dict,
        config: dict,
    ) -> pd.Series:
        top_n = config.get("top_n", 15)
        target_vol = config.get("target_vol", 0.15)
        max_position = config.get("max_position", 0.10)

        scores_clean = scores.dropna()
        if scores_clean.empty:
            return pd.Series(dtype=float)
        sorted_tickers = scores_clean.sort_values(ascending=False)
        long_candidates = sorted_tickers.head(top_n).index.tolist()
        if not long_candidates:
            return pd.Series(dtype=float)

        returns_dict = {}
        for t in long_candidates:
            if t not in prices_dict or prices_dict[t] is None or prices_dict[t].empty:
                continue
            df = prices_dict[t]
            if "close" not in df.columns:
                continue
            close = df["close"]
            if getattr(close, "ndim", 1) > 1:
                close = close.iloc[:, 0]
            ret = close.pct_change(fill_method=None).dropna()
            if len(ret) < MIN_OBS:
                continue
            ret = ret.iloc[-LOOKBACK_DAYS:]
            returns_dict[t] = ret

        if len(returns_dict) < 2:
            long_weights = {t: 1.0 / len(long_candidates) for t in long_candidates}
        else:
            try:
                returns_df = pd.concat(returns_dict, axis=1, join="outer")
                valid_counts = returns_df.notna().sum()
                keep = valid_counts >= MIN_OBS
                returns_df = returns_df.loc[:, keep]
                if returns_df.shape[1] < 2:
                    long_weights = {t: 1.0 / len(long_candidates) for t in long_candidates}
                else:
                    from pypfopt.hierarchical_portfolio import HRPOpt

                    hrp = HRPOpt(returns=returns_df)
                    hrp_result = hrp.optimize(linkage_method="ward")
                    hrp_weights = hrp_result.to_dict() if hasattr(hrp_result, "to_dict") else dict(hrp_result)
                    dropped = [t for t in long_candidates if t not in hrp_weights]
                    hrp_sum = sum(hrp_weights.values())
                    equal_share = (1.0 - hrp_sum) / len(dropped) if dropped else 0.0
                    for t in dropped:
                        hrp_weights[t] = equal_share
                    base = {t: hrp_weights.get(t, 0.0) for t in long_candidates}
                    total = sum(base.values())
                    if total <= 0:
                        long_weights = {t: 1.0 / len(long_candidates) for t in long_candidates}
                    else:
                        long_weights = {t: base[t] / total for t in long_candidates}

                    mean_score = float(np.mean([scores_clean.loc[t] for t in long_candidates]))
                    if mean_score <= 0:
                        mean_score = 1e-9
                    tilted = {t: long_weights[t] * (scores_clean.loc[t] / mean_score) for t in long_candidates}
                    total_tilted = sum(tilted.values())
                    if total_tilted <= 0:
                        long_weights = {t: 1.0 / len(long_candidates) for t in long_candidates}
                    else:
                        long_weights = {t: tilted[t] / total_tilted for t in long_candidates}
            except Exception:
                long_weights = {t: 1.0 / len(long_candidates) for t in long_candidates}

        weights = {t: long_weights[t] for t in long_candidates}

        portfolio_returns = pd.Series(dtype=float)
        rets_list = [returns_dict.get(t) for t in long_candidates if t in returns_dict]
        if len(rets_list) >= 2:
            try:
                ret_align = pd.concat(rets_list, axis=1, join="inner")
                portfolio_returns = ret_align.mean(axis=1)
            except Exception:
                pass
        if portfolio_returns.empty or len(portfolio_returns.dropna()) < 10:
            vol_scale = 1.0
        else:
            ewma_std = portfolio_returns.ewm(span=EWMA_SPAN, adjust=False).std()
            last_vol = float(ewma_std.iloc[-1]) if len(ewma_std) else VOL_FLOOR
            if last_vol != last_vol or last_vol <= 0:
                last_vol = VOL_FLOOR
            portfolio_vol = last_vol * (252 ** 0.5)
            portfolio_vol = max(portfolio_vol, VOL_FLOOR)
            vol_scale = target_vol / portfolio_vol
            vol_scale = float(np.clip(vol_scale, 0.5, 1.0))

        for t in weights:
            weights[t] *= vol_scale

        while True:
            clipped = [t for t in long_candidates if t in weights and weights[t] > max_position]
            if not clipped:
                break
            unclipped = [t for t in long_candidates if t in weights and weights[t] < max_position]
            if not unclipped:
                break
            excess = sum(weights[t] - max_position for t in clipped)
            for t in clipped:
                weights[t] = max_position
            for t in unclipped:
                weights[t] += excess / len(unclipped)

        total_w = sum(weights.values())
        if total_w > 0:
            for t in weights:
                weights[t] /= total_w

        return pd.Series(weights)
