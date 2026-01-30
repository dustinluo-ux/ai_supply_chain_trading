"""
Dynamic weighting: Rolling (PyPortfolioOpt EfficientFrontier/HRP), Regime (hmmlearn HMM), ML (Random Forest + TimeSeriesSplit).
All weight calculations use only data from T-1 or earlier to prevent look-ahead bias.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Optional: PyPortfolioOpt for rolling mode
try:
    from pypfopt.expected_returns import mean_historical_return
    from pypfopt.risk_models import CovarianceShrinkage
    from pypfopt.efficient_frontier import EfficientFrontier
    from pypfopt.hierarchical_portfolio import HRPOpt
    HAS_PYPFOPT = True
except ImportError:
    HAS_PYPFOPT = False

# Optional: hmmlearn for regime detection
try:
    from hmmlearn import hmm
    HAS_HMMLEARN = True
except ImportError:
    HAS_HMMLEARN = False

# Optional: sklearn for ML mode
try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import TimeSeriesSplit, cross_val_score
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

CAT_NAMES = ["trend", "momentum", "volume", "volatility"]
WEIGHT_FLOOR = 0.10   # no category below 10%
WEIGHT_CEIL = 0.50   # no category above 50%


def get_optimized_weights(
    history_df: pd.DataFrame,
    lookback_days: int = 60,
    forward_days: int = 5,
    method: str = "max_sharpe",
) -> dict[str, float]:
    """
    Rolling weight optimization using PyPortfolioOpt.

    Builds a "category strategy returns" matrix: each column is one category; each row
    is a period; value = sign(category_score - 0.5) * forward_ret. Uses only data in
    history_df (caller must pass data up to T-1 to avoid look-ahead).

    method: "max_sharpe" (EfficientFrontier) or "hrp" (Hierarchical Risk Parity).
    """
    required = ["trend", "momentum", "volume", "volatility", "forward_ret"]
    if not all(c in history_df.columns for c in required):
        return {c: 0.25 for c in CAT_NAMES}
    df = history_df.dropna(subset=["forward_ret"]).tail(lookback_days)
    if len(df) < 10:
        return {c: 0.25 for c in CAT_NAMES}

    # Category strategy returns: excess = sign(score - 0.5) * forward_ret per category
    returns_dict: dict[str, list[float]] = {c: [] for c in CAT_NAMES}
    for _, row in df.iterrows():
        fwd = row["forward_ret"]
        for c in CAT_NAMES:
            s = row[c]
            excess = (1.0 if (s > 0.5) else -1.0) * fwd
            returns_dict[c].append(excess)
    returns_df = pd.DataFrame(returns_dict, columns=CAT_NAMES)

    if not HAS_PYPFOPT:
        # Fallback: equal weight
        return {c: 0.25 for c in CAT_NAMES}

    try:
        if method == "hrp":
            hrp = HRPOpt(returns=returns_df)
            hrp.optimize(linkage_method="ward")
            weights = hrp.clean_weights()
            # HRP has no built-in bounds: clip to [WEIGHT_FLOOR, WEIGHT_CEIL] and renormalize
            out = {}
            for c in CAT_NAMES:
                w = max(WEIGHT_FLOOR, min(WEIGHT_CEIL, float(weights.get(c, 0.0))))
                out[c] = w
            total = sum(out.values()) or 1.0
            if total <= 0:
                return {c: 0.25 for c in CAT_NAMES}
            return {c: out[c] / total for c in CAT_NAMES}
        else:
            mu = mean_historical_return(returns_df)
            S = CovarianceShrinkage(returns_df).ledoit_wolf()
            ef = EfficientFrontier(mu, S, weight_bounds=(WEIGHT_FLOOR, WEIGHT_CEIL))
            ef.max_sharpe()
            weights = ef.clean_weights()
        out = {}
        for c in CAT_NAMES:
            w = weights.get(c, 0.0)
            out[c] = max(0.0, float(w))
        total = sum(out.values()) or 1.0
        if total <= 0:
            return {c: 0.25 for c in CAT_NAMES}
        return {c: out[c] / total for c in CAT_NAMES}
    except Exception:
        return {c: 0.25 for c in CAT_NAMES}


REGIME_STATES = ("BULL", "BEAR", "SIDEWAYS")


def get_regime_hmm(
    close_series: pd.Series,
    as_of_date: pd.Timestamp,
    min_obs: int = 60,
    n_components: int = 3,
) -> tuple[str | None, dict[str, Any] | None]:
    """
    3-State Regime Engine (hmmlearn GaussianHMM).

    BULL: high mean returns, low volatility → use BULL_WEIGHTS.
    BEAR: negative mean, high volatility → DEFENSIVE_WEIGHTS; CASH_OUT if SPY < 200-SMA.
    SIDEWAYS: mean near zero, moderate volatility → reduce position size by 50%.

    Fits n_components=3 HMM on returns up to as_of_date (no look-ahead). Maps states by
    mean return: highest mean = BULL, lowest = BEAR, middle = SIDEWAYS. Returns
    (state_label, info) where state_label in ("BULL", "BEAR", "SIDEWAYS"); info has
    state, mu, sigma. Fallback: if HMM fails to converge, returns (None, None) so
    caller can use SPY vs 200-SMA binary.
    """
    if not HAS_HMMLEARN:
        return (None, None)
    series = close_series[close_series.index <= as_of_date].dropna().sort_index()
    if len(series) < min_obs:
        return (None, None)
    returns = series.pct_change().dropna()
    if len(returns) < min_obs - 1:
        return (None, None)
    X = returns.values.reshape(-1, 1)
    try:
        model = hmm.GaussianHMM(n_components=n_components, covariance_type="full", random_state=42, n_iter=100)
        model.fit(X)
        states = model.predict(X)
        last_state = int(states[-1])
        means = model.means_.ravel()
        sigmas = np.array([float(np.sqrt(np.maximum(model.covars_[k].ravel()[0], 1e-12))) for k in range(n_components)])
        # Map: highest mean = BULL, lowest = BEAR, middle = SIDEWAYS
        order = np.argsort(means)[::-1]
        state_to_label = {}
        state_to_label[int(order[0])] = "BULL"
        state_to_label[int(order[-1])] = "BEAR"
        for i in range(1, n_components - 1):
            state_to_label[int(order[i])] = "SIDEWAYS"
        if n_components == 2:
            state_to_label[int(order[1])] = "BEAR"
        state_label = state_to_label.get(last_state, "SIDEWAYS" if n_components == 3 else "BEAR")
        mu = float(means[last_state])
        sigma = float(sigmas[last_state])
        # Transition matrix (Persistence Check): row/col order BULL, BEAR, SIDEWAYS for logs
        transmat = model.transmat_
        label_order = [int(order[0]), int(order[-1]), int(order[1])] if n_components == 3 else [int(order[0]), int(order[1])]
        if n_components == 3:
            transmat_display = transmat[np.ix_(label_order, label_order)]
            info = {"state": state_label, "mu": mu, "sigma": sigma, "transmat": transmat_display.tolist(), "transmat_labels": ["BULL", "BEAR", "SIDEWAYS"]}
        else:
            info = {"state": state_label, "mu": mu, "sigma": sigma, "transmat": transmat.tolist(), "transmat_labels": ["BULL", "BEAR"]}
        return (state_label, info)
    except Exception:
        return (None, None)


def get_ml_weights(
    history_df: pd.DataFrame,
    lookback_days: int = 60,
    n_splits: int = 5,
) -> tuple[dict[str, float] | None, float | None]:
    """
    ML-based dynamic weighting: Random Forest predicts next-day return from 4 category
    sub-scores; feature importances become category weights. Uses TimeSeriesSplit for
    cross-validation. Returns (weights, cv_r2); if CV R² is negative, returns (None, cv_r2)
    so caller falls back to fixed weights (no look-ahead).
    """
    if not HAS_SKLEARN:
        return ({c: 0.25 for c in CAT_NAMES}, None)
    required = ["trend", "momentum", "volume", "volatility", "next_ret"]
    if not all(c in history_df.columns for c in required):
        return (None, None)
    df = history_df.dropna(subset=["next_ret"]).tail(lookback_days)
    if len(df) < 20:
        return (None, None)
    X = df[CAT_NAMES].values
    y = df["next_ret"].values
    n_splits_use = min(n_splits, max(2, len(df) // 20))
    tscv = TimeSeriesSplit(n_splits=n_splits_use)
    model = RandomForestRegressor(
        n_estimators=50, max_depth=4, random_state=42, min_samples_leaf=5
    )
    try:
        scores = cross_val_score(model, X, y, cv=tscv, scoring="r2")
        cv_r2 = float(np.mean(scores)) if len(scores) else None
        if cv_r2 is not None and cv_r2 < 0:
            return (None, cv_r2)
        importances_list: list[np.ndarray] = []
        for train_idx, _ in tscv.split(X):
            if len(train_idx) < 10:
                continue
            m = RandomForestRegressor(
                n_estimators=50, max_depth=4, random_state=42, min_samples_leaf=5
            )
            m.fit(X[train_idx], y[train_idx])
            importances_list.append(m.feature_importances_)
        if not importances_list:
            model.fit(X, y)
            imp = model.feature_importances_
        else:
            imp = np.mean(importances_list, axis=0)
        total = float(np.sum(imp)) or 1.0
        weights = {c: float(imp[i]) / total for i, c in enumerate(CAT_NAMES)}
        return (weights, cv_r2)
    except Exception:
        return (None, None)


# Default news weight when AdaptiveSelector has insufficient history
DEFAULT_NEWS_WEIGHT = 0.20
ADAPTIVE_LOOKBACK_OCCURRENCES = 3


def _default_regime_ledger_path() -> Path:
    from src.signals.performance_logger import _default_ledger_path
    return _default_ledger_path()


class AdaptiveSelector:
    """
    Reads the performance CSV and returns the news weight that performed best
    during the last N occurrences of the current regime (Technical vs News blend).
    Supports regime_ledger.csv for audit_past_performance (memory / Historical Amnesia prevention).
    """

    def __init__(
        self,
        csv_path: str | Path,
        lookback_occurrences: int = ADAPTIVE_LOOKBACK_OCCURRENCES,
        ledger_path: str | Path | None = None,
    ):
        self.csv_path = Path(csv_path)
        self.lookback_occurrences = lookback_occurrences
        self.ledger_path = Path(ledger_path) if ledger_path is not None else _default_regime_ledger_path()

    def get_optimal_weights(self, current_regime: str | None) -> float:
        """
        Return the news_weight (0–1) that performed best during the last
        lookback_occurrences (default 3) of current_regime. If regime is None
        or fewer than 3 occurrences exist, return DEFAULT_NEWS_WEIGHT.
        """
        if not current_regime or not self.csv_path.exists():
            return DEFAULT_NEWS_WEIGHT
        try:
            df = pd.read_csv(self.csv_path, encoding="utf-8")
        except Exception:
            return DEFAULT_NEWS_WEIGHT
        if df.empty or "regime" not in df.columns or "return" not in df.columns or "news_weight_used" not in df.columns:
            return DEFAULT_NEWS_WEIGHT
        regime_rows = df[df["regime"].astype(str).str.strip() == str(current_regime).strip()]
        if len(regime_rows) < self.lookback_occurrences:
            return DEFAULT_NEWS_WEIGHT
        last_n = regime_rows.tail(self.lookback_occurrences)
        # Best = highest average return when that news_weight was used
        best_weight = DEFAULT_NEWS_WEIGHT
        best_avg_return = float("-inf")
        for nw in last_n["news_weight_used"].unique():
            subset = last_n[last_n["news_weight_used"] == nw]
            avg_ret = subset["return"].mean()
            if avg_ret > best_avg_return:
                best_avg_return = avg_ret
                best_weight = float(nw)
        return max(0.0, min(1.0, best_weight))

    def audit_past_performance(
        self,
        current_regime: str | None,
        current_strategy_id: str | None = None,
        current_sortino: float | None = None,
    ) -> None:
        """
        Scan regime_ledger.csv for current_regime; compute average Sortino per Strategy_ID.
        Log a Memory Alert to console: last time in this regime, which strategy had which Sortino,
        and suggest switch if another strategy had higher Sortino than current.
        """
        if not current_regime or not self.ledger_path.exists():
            return
        try:
            df = pd.read_csv(self.ledger_path, encoding="utf-8")
        except Exception:
            return
        required = ["Regime", "Strategy_ID", "Return"]
        if not all(c in df.columns for c in required):
            return
        regime_str = str(current_regime).strip()
        regime_rows = df[df["Regime"].astype(str).str.strip() == regime_str]
        if regime_rows.empty:
            return
        from src.signals.metrics import calculate_regime_sortino
        sortino_by_strategy: dict[str, float] = {}
        for sid in regime_rows["Strategy_ID"].unique():
            sid = str(sid).strip()
            subset = regime_rows[regime_rows["Strategy_ID"].astype(str).str.strip() == sid]
            rets = subset["Return"].dropna().values
            if len(rets) < 1:
                continue
            sortino_by_strategy[sid] = calculate_regime_sortino(rets, risk_free_rate=0.0)
        if not sortino_by_strategy:
            return
        best_sid = max(sortino_by_strategy, key=sortino_by_strategy.get)
        best_sortino = sortino_by_strategy[best_sid]
        msg = f"[MEMORY] Last time in {regime_str}, {best_sid} had a Sortino of {best_sortino:.2f}."
        if current_strategy_id is not None and current_sortino is not None:
            cur_sid = str(current_strategy_id).strip()
            msg += f" Current Strategy Sortino: {current_sortino:.2f}."
            if best_sid != cur_sid and best_sortino > current_sortino:
                msg += " Suggesting switch..."
        print(msg, flush=True)


# Strategy ID format: nw{news_weight}_h{horizon}_r{risk} or nw{news_weight}_r{risk}
WINNING_PROFILE_LOOKBACK = 4
MIN_REGIME_OCCURRENCES_FOR_SELECTOR = 2


def parse_strategy_id(strategy_id: str) -> dict[str, float]:
    """
    Parse Strategy_ID (e.g. nw0.3_h5_r1.0 or nw0.3_r0.5) into news_weight, signal_horizon_days, sideways_risk_scale.
    """
    out = {"news_weight": DEFAULT_NEWS_WEIGHT, "signal_horizon_days": 5.0, "sideways_risk_scale": 0.5}
    s = str(strategy_id).strip()
    import re
    # nw0.3 or nw0.30
    m = re.search(r"nw([\d.]+)", s, re.I)
    if m:
        try:
            out["news_weight"] = float(m.group(1))
        except ValueError:
            pass
    m = re.search(r"_h(\d+)", s, re.I)
    if m:
        try:
            out["signal_horizon_days"] = float(m.group(1))
        except ValueError:
            pass
    m = re.search(r"_r([\d.]+)", s, re.I)
    if m:
        try:
            out["sideways_risk_scale"] = float(m.group(1))
        except ValueError:
            pass
    return out


class StrategySelector:
    """
    Dynamic Selector: connects HMM regime detection to strategy execution via real-time
    ledger lookup. get_winning_profile(regime) returns the Strategy_ID with highest
    win rate (tie-break: lowest Max_Drawdown) over the last N regime occurrences.
    """

    def __init__(self, ledger_path: str | Path | None = None):
        self.ledger_path = Path(ledger_path) if ledger_path is not None else _default_regime_ledger_path()

    def get_winning_profile(self, current_regime: str | None) -> dict[str, Any] | None:
        """
        Load regime_ledger.csv; filter for last 4 occurrences of current_regime.
        For each unique Strategy_ID compute Win Rate and Profit Factor; select the one
        with highest win rate (tie-break: lowest Max_Drawdown).
        If ledger has fewer than 2 occurrences of regime, or winning profile has negative
        Sharpe, return None (fallback to config defaults).
        """
        if not current_regime or not self.ledger_path.exists():
            return None
        try:
            df = pd.read_csv(self.ledger_path, encoding="utf-8")
        except Exception:
            return None
        required = ["Regime", "Strategy_ID", "Return", "Max_Drawdown"]
        if not all(c in df.columns for c in required):
            return None
        regime_str = str(current_regime).strip()
        regime_rows = df[df["Regime"].astype(str).str.strip() == regime_str]
        if len(regime_rows) < MIN_REGIME_OCCURRENCES_FOR_SELECTOR:
            return None
        last_n = regime_rows.tail(WINNING_PROFILE_LOOKBACK)
        # Win rate and profit factor per Strategy_ID
        best_sid = None
        best_win_rate = -1.0
        best_drawdown = 0.0  # least negative (max)
        best_profit_factor = -1.0
        best_rets: np.ndarray | None = None
        for sid in last_n["Strategy_ID"].unique():
            sid = str(sid).strip()
            subset = last_n[last_n["Strategy_ID"].astype(str).str.strip() == sid]
            rets = subset["Return"].dropna().values
            if len(rets) < 1:
                continue
            wins = rets[rets > 0]
            losses = rets[rets < 0]
            win_rate = float(np.mean(rets > 0)) if len(rets) else 0.0
            gross_loss = float(np.abs(np.sum(losses))) if len(losses) else 1e-8
            gross_profit = float(np.sum(wins)) if len(wins) else 0.0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else (10.0 if gross_profit > 0 else 0.0)
            avg_dd = float(subset["Max_Drawdown"].mean())
            # Tie-break: higher win rate first; then lowest Max_Drawdown (least negative = max)
            if win_rate > best_win_rate or (win_rate == best_win_rate and avg_dd > best_drawdown):
                best_win_rate = win_rate
                best_drawdown = avg_dd
                best_sid = sid
                best_profit_factor = profit_factor
                best_rets = rets
        if best_sid is None or best_rets is None:
            return None
        # Sharpe (annualized from weekly returns): mean*52 / (std*sqrt(52))
        ann_ret = float(np.mean(best_rets)) * 52
        ann_vol = float(np.std(best_rets)) * np.sqrt(52) if len(best_rets) > 1 and np.std(best_rets) > 0 else 1e-8
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
        if sharpe < 0:
            return None
        params = parse_strategy_id(best_sid)
        return {
            "strategy_id": best_sid,
            "win_rate": best_win_rate,
            "profit_factor": best_profit_factor,
            "sharpe": sharpe,
            "params": params,
        }
