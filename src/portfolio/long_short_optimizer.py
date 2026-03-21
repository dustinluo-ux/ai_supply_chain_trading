"""
Track D — 130/30 Long/Short optimizer with volatility throttle and thesis monitor.

Spec: docs/LONG_SHORT_SPEC.md
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

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


def _compute_rolling_ic(
    scores_df: pd.DataFrame,
    prices_dict: dict,
    window: int = 60,
) -> float | None:
    """
    Rolling IC: for each of the last `window` dates, compute Spearman(score, next-day return);
    return mean IC if >= 10 valid dates else None.
    """
    try:
        slice_df = scores_df.tail(window)
        if slice_df.empty:
            logger.debug("[TRACK_D_IC] insufficient data")
            return None
        dates = slice_df.index.tolist()
        ic_list = []
        for i in range(len(dates) - 1):
            date_curr = dates[i]
            date_next = dates[i + 1]
            try:
                row = slice_df.loc[date_curr]
                scores_vals = []
                returns_vals = []
                for t in row.dropna().index:
                    if t not in prices_dict or prices_dict[t] is None or prices_dict[t].empty:
                        continue
                    df = prices_dict[t]
                    if "close" not in df.columns:
                        continue
                    close = df["close"]
                    if getattr(close, "ndim", 1) > 1:
                        close = close.iloc[:, 0]
                    close = close.reindex([date_curr, date_next])
                    close = close.dropna()
                    if len(close) < 2:
                        continue
                    try:
                        c_curr = float(close.loc[date_curr])
                        c_next = float(close.loc[date_next])
                    except (KeyError, TypeError):
                        continue
                    if c_curr is None or c_curr <= 0 or c_next is None:
                        continue
                    score_val = row.get(t)
                    if pd.isna(score_val):
                        continue
                    next_ret = (c_next / c_curr) - 1.0
                    scores_vals.append(float(score_val))
                    returns_vals.append(next_ret)
                if len(scores_vals) < 5 or len(returns_vals) < 5:
                    continue
                r, _ = spearmanr(scores_vals, returns_vals)
                if r is not None and np.isfinite(r):
                    ic_list.append(float(r))
            except Exception as e:
                logger.debug("[TRACK_D_IC] date %s: %s", date_curr, e)
                continue
        if len(ic_list) < 10:
            logger.info("[TRACK_D_IC] insufficient data")
            return None
        mean_ic = float(np.mean(ic_list))
        logger.info("[TRACK_D_IC] rolling_ic=%.4f n_dates=%d", mean_ic, len(ic_list))
        return mean_ic
    except Exception as e:
        logger.exception("[TRACK_D_IC] %s", e)
        return None


def _determine_fsm_state(
    thesis_result: dict,
    rolling_ic: float | None,
    current_drawdown: float,
    regime_status: dict,
    config: dict,
) -> dict[str, str]:
    """FSM priority hierarchy (expert-revised 2026-03-21):
      1. State B  (Bull Hedge):   rho >= 0.50 AND SPY > 200-SMA → zero single-name shorts, SMH ETF hedge
      2. State A- (Short-Light):  rho in [0.45, 0.50) → single-name shorts capped at -1% per name
      3. State C  (Long-Only):    rolling_IC < 0 AND drawdown > 1.5 × design_max_drawdown
      4. State A  (Normal):       default — full short book active
    Hysteresis: B exits at rho < 0.45 (5pp buffer); C exits at IC >= 0.03.
    Returns dict with 'state', 'reason', and 'trigger' keys.
    """
    rho = thesis_result.get("rho")
    # SPY > 200-SMA is the operational proxy for "SMH in bull regime"
    spy_below_sma = regime_status.get("spy_below_sma", regime_status.get("spy_below_sma200", False)) is True
    smh_in_bull = not spy_below_sma

    design_max_dd = config.get("design_max_drawdown", 0.15)
    fsm_history = config.get("fsm_state_history", [])
    prev_state = fsm_history[-1] if fsm_history else "A"

    # --- Priority 1: State B — full bull hedge (rho >= 0.50, lowered from 0.60) ---
    b_triggered = rho is not None and rho >= 0.50 and smh_in_bull

    # --- Priority 2: State A- — short-light band (0.45 <= rho < 0.50) ---
    a_minus_triggered = rho is not None and 0.45 <= rho < 0.50

    # --- Priority 3: State C — alpha model fundamentally broken ---
    # Only fires when IC is negative AND drawdown exceeds 1.5 × design threshold
    c_triggered = (
        rolling_ic is not None
        and rolling_ic < 0.0
        and abs(current_drawdown) > 1.5 * design_max_dd
    )

    # --- Determine proposed state (priority order: B > A- > C > A) ---
    if b_triggered:
        proposed = "B"
        reason = f"rho={rho:.3f}>=0.50 AND bull_regime (SPY>200-SMA)"
        trigger = "sector_correlation+SMH_bull"
    elif a_minus_triggered:
        proposed = "A-"
        reason = f"rho={rho:.3f} in [0.45,0.50) — short-light band"
        trigger = "short_light_band"
    elif c_triggered:
        proposed = "C"
        reason = f"IC={rolling_ic:.4f}<0 AND dd={current_drawdown:.3f}>1.5x{design_max_dd:.2f}"
        trigger = "IC_negative+drawdown"
    else:
        proposed = "A"
        reason = "normal"
        trigger = "none"

    # --- Hysteresis: buffer thresholds before exiting B or C ---
    if prev_state == "B" and proposed != "B":
        # Exit B only when rho drops clearly below entry threshold (5pp buffer below 0.50)
        if rho is not None and rho >= 0.45:
            return {
                "state": "B",
                "reason": f"hysteresis: rho={rho:.3f} within exit buffer (need <0.45)",
                "trigger": "hysteresis_B",
            }
    if prev_state == "C" and proposed != "C":
        # Exit C only when IC is clearly positive (3pp buffer — relaxed from 0.01 to prevent lock-in)
        if rolling_ic is not None and rolling_ic < 0.03:
            return {
                "state": "C",
                "reason": f"hysteresis: IC={rolling_ic:.4f} within exit buffer (need >=0.03)",
                "trigger": "hysteresis_C",
            }

    return {"state": proposed, "reason": reason, "trigger": trigger}


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


def get_short_exposure(
    short_candidates: list,
    scores: pd.Series,
    prices_dict: dict,
    rho: float | None,
    top_n: int,
    dispersion_anchor: float = 0.40,
) -> float:
    """
    Returns S in [0.0, 0.30] — the dynamic short sleeve size.
    Correlation gate: rho > 0.70 → 0.0. Else scale by cross-sectional dispersion of short candidates.
    """
    if rho is not None and rho > 0.70:
        return 0.0
    vols = []
    for t in short_candidates:
        if t not in prices_dict or prices_dict[t] is None or prices_dict[t].empty:
            continue
        df = prices_dict[t]
        if "close" not in df.columns:
            continue
        close = df["close"]
        if hasattr(close, "iloc") and getattr(close, "ndim", 1) > 1:
            close = close.iloc[:, 0]
        ret = close.pct_change(fill_method=None).dropna()
        if len(ret) < 10:
            continue
        tail = ret.tail(20)
        ann_vol = float(tail.std()) * ANNUALIZATION_FACTOR
        vols.append(ann_vol)
    sector_dispersion = float(np.mean(vols)) if vols else 0.0
    S = 0.30 * min(sector_dispersion / dispersion_anchor, 1.0)
    return float(np.clip(S, 0.0, 0.30))


def get_leverage_multiplier_v2(
    target_vol: float,
    portfolio_returns: pd.Series,
    vix_z: float,
    max_leverage: float = 1.6,
) -> float:
    """
    Same logic as get_leverage_multiplier; caller can pass adjusted ceiling (e.g. 1.6 / (1.0 + S))
    when shorts are active so gross cap 1.6 is shared between long and short.
    """
    return get_leverage_multiplier(target_vol, portfolio_returns, vix_z, max_leverage)


def rebalance_alpha_sleeve(
    scores: pd.Series,
    scores_df: pd.DataFrame,
    prices_dict: dict,
    regime_status: dict,
    config: dict,
) -> tuple[pd.Series, str]:
    """
    Orchestrator for Dynamic Alpha-Sleeve. Dynamic short size S from dispersion and correlation;
    long book L = 1.0 base, short book S in [0, 0.30]. Effective multiplier ceiling shared when S > 0.
    - S = 0, multiplier = 1.6 → pure leveraged long-only (bull momentum regime)
    - S = 0.30, multiplier ≈ 1.23 → full 130/30 equivalent (high-dispersion neutral/bear regime)
    - S = 0, multiplier = 0.1 → near-cash (VIX emergency)
    """
    target_vol = config.get("target_vol", 0.15)
    max_leverage = config.get("max_leverage", 1.6)
    top_n = config.get("top_n", 15)
    bottom_n = config.get("bottom_n", 8)
    max_position = config.get("max_position", 0.10)
    dispersion_anchor = config.get("dispersion_anchor", 0.40)

    scores_clean = scores.dropna()
    if scores_clean.empty:
        return pd.Series(dtype=float), "A"
    sorted_tickers = scores_clean.sort_values(ascending=False)
    long_candidates = sorted_tickers.head(top_n).index.tolist()
    short_candidates = sorted_tickers.tail(bottom_n).index.tolist()

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

    # Step 1: thesis integrity
    thesis_result = check_thesis_integrity(scores_df, top_n, bottom_n, window=60)
    rho = thesis_result["rho"]

    # Step 2: rolling IC
    rolling_ic = _compute_rolling_ic(scores_df, prices_dict, window=60)

    # Step 2b: current drawdown from portfolio returns (used by State C threshold)
    _dd_ret = portfolio_returns.dropna()
    if len(_dd_ret) >= 5:
        _cum = (1 + _dd_ret).cumprod()
        _peak = _cum.cummax()
        current_drawdown = float(((_cum - _peak) / _peak).iloc[-1])
    else:
        current_drawdown = 0.0

    # Step 3: FSM state
    fsm = _determine_fsm_state(thesis_result, rolling_ic, current_drawdown, regime_status, config)
    logger.info(
        "[TRACK_D_FSM] state=%s | trigger=%s | reason=%s | ic=%.4f | dd=%.3f | rho=%s",
        fsm["state"], fsm.get("trigger", "?"), fsm["reason"],
        rolling_ic if rolling_ic is not None else float("nan"),
        current_drawdown,
        f"{rho:.3f}" if rho is not None else "None",
    )
    # Side-channel: expose FSM result for aggregator audit (live execution path)
    config["_last_fsm_trigger"] = fsm.get("trigger", "none")
    config["_last_fsm_state"] = fsm.get("state", "A")
    config["_last_fsm_reason"] = fsm.get("reason", "")

    # Step 4: leverage multiplier (A/A-: 1.6/(1+S); B/C: max_leverage)
    S = get_short_exposure(short_candidates, scores, prices_dict, rho, top_n, dispersion_anchor=dispersion_anchor)
    if fsm["state"] in ("A", "A-"):
        effective_max_lev = (1.6 / (1.0 + S)) if S > 0 else 1.6
    else:
        effective_max_lev = max_leverage
    multiplier = get_leverage_multiplier_v2(target_vol, portfolio_returns, vix_z, max_leverage=effective_max_lev)

    # Step 5: long book (HRP unchanged)
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

    weights = {}
    for t in long_candidates:
        weights[t] = long_weights[t] * multiplier

    # Step 6: short weights by FSM state
    short_light_cap = config.get("short_light_cap", 0.12)
    a_minus_per_name_cap = config.get("a_minus_per_name_cap", 0.01)  # 1% per name cap for Short-Light
    if fsm["state"] == "A":
        if S > 0 and short_candidates:
            for t in short_candidates:
                weights[t] = -(S / len(short_candidates)) * multiplier
        else:
            for t in short_candidates:
                weights[t] = 0.0
        target_short_sum = -S * multiplier if S > 0 else 0.0
    elif fsm["state"] == "A-":
        # Short-Light: retain single-name shorts but cap each at -1% per name
        if S > 0 and short_candidates:
            for t in short_candidates:
                raw = -(S / len(short_candidates)) * multiplier
                weights[t] = max(raw, -a_minus_per_name_cap)  # cap: weight must not exceed -1%
        else:
            for t in short_candidates:
                weights[t] = 0.0
        target_short_sum = -min(S * multiplier, a_minus_per_name_cap * len(short_candidates)) if S > 0 else 0.0
        logger.info("[TRACK_D_FSM] State A-: short book capped at %.1f%% per name", a_minus_per_name_cap * 100)
    elif fsm["state"] == "B":
        for t in short_candidates:
            weights[t] = 0.0
        if "SMH" in prices_dict and prices_dict["SMH"] is not None and not prices_dict["SMH"].empty:
            weights["SMH"] = -short_light_cap
        else:
            logger.warning("[TRACK_D_FSM] State B: SMH not in prices_dict, skipping SMH short")
        target_short_sum = -short_light_cap
    else:
        # State C: long-only, all shorts zeroed
        for t in short_candidates:
            weights[t] = 0.0
        target_short_sum = 0.0

    target_long_sum = 1.0 * multiplier

    # Step 7: position caps, gross cap 1.6, net sanity
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

    if target_short_sum < 0 and fsm["state"] == "A":
        short_tickers = [t for t in short_candidates if t in weights]
        if short_tickers:
            while True:
                clipped = [t for t in short_tickers if t in weights and weights[t] < -max_position]
                if not clipped:
                    break
                unclipped = [t for t in short_tickers if t in weights and weights[t] > -max_position]
                if not unclipped:
                    break
                excess = sum(weights[t] + max_position for t in clipped)
                for t in clipped:
                    weights[t] = -max_position
                for t in unclipped:
                    weights[t] += excess / len(unclipped)
            short_sum = sum(weights.get(t, 0) for t in short_tickers)
            if short_sum < 0:
                scale = target_short_sum / short_sum
                for t in short_tickers:
                    if t in weights:
                        weights[t] *= scale

    gross = sum(abs(weights[t]) for t in weights)
    if gross > 1.6 and gross > 0:
        scale = 1.6 / gross
        for t in list(weights.keys()):
            weights[t] *= scale
    net = sum(weights.values())
    if multiplier > 0 and (net < 0.9 * multiplier or net > 1.1 * multiplier):
        logger.warning("rebalance_alpha_sleeve: sum(weights)=%s outside [0.9, 1.1] * multiplier=%s", net, multiplier)

    # Step 8: thesis_collapse alert (independent of FSM)
    if thesis_result["thesis_alert"]:
        from src.monitoring.telegram_alerts import send_alert
        send_alert("thesis_collapse", {"rho": thesis_result["rho"], "reason": thesis_result["alert_reason"]})

    # Step 9
    return pd.Series(weights), str(fsm.get("state", "A"))
