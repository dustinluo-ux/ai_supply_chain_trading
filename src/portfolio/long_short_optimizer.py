"""
Track D — 130/30 Long/Short optimizer with volatility throttle and thesis monitor.

Spec: docs/LONG_SHORT_SPEC.md
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import pearsonr

logger = logging.getLogger(__name__)

ANNUALIZATION_FACTOR = 252 ** 0.5  # sqrt(252) for daily returns to annualized vol


def get_leverage_multiplier(
    target_vol: float,
    portfolio_returns: pd.Series,
    vix_z: float,
    max_leverage: float,
) -> float:
    """
    Returns a leverage scaler in [0.0, max_leverage] based on realised portfolio
    volatility and VIX stress level.
    """
    ret = portfolio_returns.dropna()
    if len(ret) < 10:
        return 1.0
    if vix_z > 2.0:
        return 0.1
    tail = ret.tail(20)
    realised_vol = float(tail.std()) * ANNUALIZATION_FACTOR
    if realised_vol <= 0:
        raw = 0.0
    else:
        raw = min(target_vol / realised_vol, max_leverage)
    return float(np.clip(raw, 0.0, max_leverage))


def check_thesis_integrity(
    scores_df: pd.DataFrame,
    top_n: int,
    bottom_n: int,
    window: int = 60,
) -> dict[str, Any]:
    """
    Detects whether the long and short baskets are becoming correlated
    (long/short edge collapsing). Returns rho, thesis_alert, alert_reason.
    """
    slice_df = scores_df.tail(window)
    if len(slice_df) < 30:
        return {"rho": None, "thesis_alert": False, "alert_reason": "insufficient data"}
    L_list = []
    S_list = []
    for _date, row in slice_df.iterrows():
        row_clean = row.dropna()
        if len(row_clean) < top_n + bottom_n:
            row_clean = row.fillna(0.5)
        else:
            row_clean = row_clean
        sorted_tickers = row_clean.sort_values(ascending=False)
        long_tickers = sorted_tickers.head(top_n).index.tolist()
        short_tickers = sorted_tickers.tail(bottom_n).index.tolist()
        L_list.append(row_clean.reindex(long_tickers).fillna(0.5).mean())
        S_list.append(row_clean.reindex(short_tickers).fillna(0.5).mean())
    L = pd.Series(L_list)
    S = pd.Series(S_list)
    if len(L) < 30 or L.isna().all() or S.isna().all():
        return {"rho": None, "thesis_alert": False, "alert_reason": "insufficient data"}
    use_L = L.tail(60)
    use_S = S.tail(60)
    valid = use_L.notna() & use_S.notna()
    use_L = use_L.loc[valid]
    use_S = use_S.loc[valid]
    if len(use_L) < 30:
        return {"rho": None, "thesis_alert": False, "alert_reason": "insufficient data"}
    rho, _ = pearsonr(use_L, use_S)
    if np.isnan(rho):
        rho = None
        thesis_alert = False
        alert_reason = "correlation undefined"
    else:
        thesis_alert = float(rho) > 0.8
        alert_reason = "correlation above 0.8" if thesis_alert else "ok"
    return {"rho": float(rho) if rho is not None else None, "thesis_alert": thesis_alert, "alert_reason": alert_reason}


def build_long_short_weights(
    scores: pd.Series,
    prices_dict: dict,
    top_n: int,
    bottom_n: int,
    multiplier: float,
    thesis_alert: bool,
    max_position: float = 0.05,
) -> pd.Series:
    """
    Builds the 130/30 weight vector: HRP long side (sum 1.30), equal-weight short (sum -0.30),
    with multiplier, thesis reduction, and max-position cap.
    """
    scores_clean = scores.dropna()
    if scores_clean.empty:
        return pd.Series(dtype=float)
    tickers = scores_clean.index.tolist()
    if len(tickers) < top_n + bottom_n:
        return pd.Series(0.0, index=tickers)
    sorted_tickers = scores_clean.sort_values(ascending=False)
    long_candidates = sorted_tickers.head(top_n).index.tolist()
    short_candidates = sorted_tickers.tail(bottom_n).index.tolist()

    lookback_days = 60
    min_obs = 30
    returns_dict = {}
    for t in long_candidates:
        if t not in prices_dict or prices_dict[t] is None or prices_dict[t].empty:
            continue
        df = prices_dict[t]
        close = df["close"]
        if hasattr(close, "iloc") and getattr(close, "ndim", 1) > 1:
            close = close.iloc[:, 0]
        ret = close.pct_change(fill_method=None).dropna()
        if len(ret) < min_obs:
            continue
        ret = ret.iloc[-lookback_days:]
        returns_dict[t] = ret

    if len(returns_dict) < 2:
        long_weights = {t: 1.0 / len(long_candidates) for t in long_candidates}
    else:
        try:
            returns_df = pd.concat(returns_dict, axis=1, join="outer")
            valid_counts = returns_df.notna().sum()
            keep = valid_counts >= min_obs
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
                long_weights = {t: hrp_weights.get(t, 0.0) for t in long_candidates}
                total = sum(long_weights.values())
                if total <= 0:
                    long_weights = {t: 1.0 / len(long_candidates) for t in long_candidates}
                else:
                    long_weights = {t: long_weights[t] / total for t in long_candidates}
        except Exception:
            long_weights = {t: 1.0 / len(long_candidates) for t in long_candidates}

    long_scale = 1.30
    short_scale = -0.30
    weights = {}
    for t in long_candidates:
        weights[t] = long_weights[t] * long_scale
    for t in short_candidates:
        weights[t] = short_scale / bottom_n

    if thesis_alert:
        for t in long_candidates:
            weights[t] *= 0.65
        for t in short_candidates:
            weights[t] *= 0.15

    for t in list(weights.keys()):
        weights[t] *= multiplier

    target_long_sum = (0.65 if thesis_alert else 1.30) * multiplier
    target_short_sum = (-0.15 if thesis_alert else -0.30) * multiplier

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
    long_sum = sum(weights.get(t, 0) for t in long_candidates)
    if long_sum > 0 and long_candidates:
        scale = target_long_sum / long_sum
        for t in long_candidates:
            if t in weights:
                weights[t] *= scale

    while True:
        clipped = [t for t in short_candidates if t in weights and weights[t] < -max_position]
        if not clipped:
            break
        unclipped = [t for t in short_candidates if t in weights and weights[t] > -max_position]
        if not unclipped:
            break
        excess = sum(weights[t] + max_position for t in clipped)
        for t in clipped:
            weights[t] = -max_position
        for t in unclipped:
            weights[t] += excess / len(unclipped)
    short_sum = sum(weights.get(t, 0) for t in short_candidates)
    if short_sum < 0 and short_candidates:
        scale = target_short_sum / short_sum
        for t in short_candidates:
            if t in weights:
                weights[t] *= scale

    gross = sum(abs(weights[t]) for t in weights)
    cap_gross = 1.6 * multiplier
    if gross > cap_gross and gross > 0:
        scale = cap_gross / gross
        for t in list(weights.keys()):
            weights[t] *= scale

    net = sum(weights.values())
    if net < 0.9 or net > 1.1:
        logger.warning("rebalance_long_short: sum(weights)=%s outside [0.9, 1.1]", net)

    return pd.Series(weights)


def rebalance_long_short(
    scores: pd.Series,
    scores_df: pd.DataFrame,
    prices_dict: dict,
    regime_status: dict,
    config: dict,
) -> pd.Series:
    """
    Orchestrator: get_leverage_multiplier → check_thesis_integrity → build_long_short_weights.
    Sends Telegram alert when thesis_alert is True.
    """
    target_vol = config.get("target_vol", 0.15)
    max_leverage = config.get("max_leverage", 1.6)
    top_n = config.get("top_n", 15)
    bottom_n = config.get("bottom_n", 8)
    max_position = config.get("max_position", 0.05)

    scores_clean = scores.dropna()
    if scores_clean.empty:
        return pd.Series(dtype=float)
    sorted_tickers = scores_clean.sort_values(ascending=False)
    long_candidates = sorted_tickers.head(top_n).index.tolist()

    portfolio_returns = pd.Series(dtype=float)
    prior_weights = config.get("prior_weights")
    if prior_weights is not None and isinstance(prior_weights, (dict, pd.Series)):
        w = prior_weights if isinstance(prior_weights, dict) else prior_weights.to_dict()
        tickers_with_data = [t for t in w if t in prices_dict and prices_dict[t] is not None and not prices_dict[t].empty]
        if tickers_with_data:
            rets = []
            for t in tickers_with_data:
                df = prices_dict[t]
                close = df["close"]
                if getattr(close, "ndim", 1) > 1:
                    close = close.iloc[:, 0]
                rets.append(close.pct_change(fill_method=None))
            if rets:
                ret_df = pd.concat(rets, axis=1, join="outer")
                ret_df.columns = tickers_with_data[: ret_df.shape[1]]
                weights_vec = np.array([w.get(t, 0) for t in ret_df.columns])
                if weights_vec.size == ret_df.shape[1]:
                    portfolio_returns = (ret_df * weights_vec).sum(axis=1)
    if portfolio_returns.empty or len(portfolio_returns.dropna()) < 10:
        rets = []
        for t in long_candidates:
            if t not in prices_dict or prices_dict[t] is None or prices_dict[t].empty:
                continue
            df = prices_dict[t]
            close = df["close"]
            if getattr(close, "ndim", 1) > 1:
                close = close.iloc[:, 0]
            rets.append(close.pct_change(fill_method=None))
        if rets:
            ret_df = pd.concat(rets, axis=1, join="outer")
            portfolio_returns = ret_df.mean(axis=1)
        else:
            portfolio_returns = pd.Series(dtype=float)

    vix_z = 0.0
    if "vix_z" in regime_status:
        v = regime_status["vix_z"]
        if isinstance(v, (int, float)) and not (isinstance(v, bool)):
            vix_z = float(v)
    if vix_z == 0.0 and "vix" in regime_status:
        vix_val = regime_status["vix"]
        if isinstance(vix_val, (int, float)) and not (isinstance(vix_val, bool)):
            vix_series = regime_status.get("vix_series")
            if vix_series is not None and len(vix_series) >= 20:
                arr = np.asarray(vix_series[-20:], dtype=float)
                m, s = arr.mean(), arr.std()
                if s > 0:
                    vix_z = (float(vix_val) - m) / s

    multiplier = get_leverage_multiplier(target_vol, portfolio_returns, vix_z, max_leverage)
    thesis_result = check_thesis_integrity(scores_df, top_n, bottom_n, window=60)
    if thesis_result["thesis_alert"]:
        from src.monitoring.telegram_alerts import send_alert
        send_alert("thesis_collapse", {"rho": thesis_result["rho"], "reason": thesis_result["alert_reason"]})
    weights = build_long_short_weights(
        scores, prices_dict, top_n, bottom_n, multiplier, thesis_result["thesis_alert"], max_position
    )
    return weights
