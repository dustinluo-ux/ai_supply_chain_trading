"""
Canonical target-weight pipeline: regime + spine (SignalEngine -> PolicyEngine -> PortfolioEngine).
Single place for building target weights; used by backtest and execution entrypoints.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from src.data.csv_provider import find_csv_path, ensure_ohlcv

BENCHMARK_TICKER = "SPY"
SMA_KILL_SWITCH_DAYS = 200
KILL_SWITCH_MODE = "cash"


def _spy_benchmark_series(data_dir: Path) -> Optional[tuple[pd.Series, pd.Series]]:
    """Load SPY; return (close, sma200) aligned to SPY index. None if SPY not found."""
    path = find_csv_path(data_dir, BENCHMARK_TICKER)
    if not path:
        return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True, dayfirst=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
        df.columns = [c.lower() for c in df.columns]
        if "close" not in df.columns or len(df) < SMA_KILL_SWITCH_DAYS:
            return None
        close = df["close"]
        sma = close.rolling(SMA_KILL_SWITCH_DAYS, min_periods=SMA_KILL_SWITCH_DAYS).mean()
        return (close, sma)
    except Exception:
        return None


def compute_target_weights(
    as_of: pd.Timestamp,
    tickers: list[str],
    prices_dict: dict[str, pd.DataFrame],
    data_dir: Optional[Path] = None,
    *,
    top_n: int = 3,
    sideways_risk_scale: float = 0.5,
    weight_mode: str = "fixed",
    path: Optional[str] = None,
) -> pd.Series:
    """
    Canonical spine:
    SignalEngine -> PolicyEngine -> PortfolioEngine
    Returns pd.Series(intent.weights) indexed by full universe.
    path: if "weekly" then intent mode is execution; else backtest (no path in context).
    """
    from src.signals.signal_engine import SignalEngine
    from src.core import PolicyEngine, PortfolioEngine

    signal_engine = SignalEngine()
    policy_engine = PolicyEngine()
    portfolio_engine = PortfolioEngine()

    if len(tickers) < top_n:
        return pd.Series(0.0, index=tickers)

    spy_bench = _spy_benchmark_series(data_dir) if data_dir else None
    kill_switch_active = spy_bench is not None
    spy_close_series = None
    spy_sma_series = None
    spy_close_native = None
    if spy_bench is not None:
        spy_close_series, spy_sma_series = spy_bench
        spy_close_native = spy_close_series.copy()

    regime_state = None
    spy_above_sma200 = None
    spy_below_sma200 = False
    if spy_close_native is not None:
        from src.signals.weight_model import get_regime_hmm

        regime_state, _ = get_regime_hmm(spy_close_native, as_of, min_obs=60, n_components=3)
        if regime_state is None and kill_switch_active and spy_close_series is not None and spy_sma_series is not None:
            up_to = spy_close_series.index[spy_close_series.index <= as_of]
            if len(up_to) > 0:
                last_d = up_to[-1]
                spy_cl = spy_close_series.loc[last_d]
                sma_val = spy_sma_series.loc[last_d] if last_d in spy_sma_series.index else None
                if pd.notna(spy_cl) and sma_val is not None and not pd.isna(sma_val):
                    spy_above_sma200 = bool(spy_cl >= sma_val)
                    regime_state = "BULL" if spy_above_sma200 else "BEAR"
        if kill_switch_active and spy_close_series is not None and spy_sma_series is not None:
            up_to = spy_close_series.index[spy_close_series.index <= as_of]
            if len(up_to) > 0:
                last_d = up_to[-1]
                spy_cl = spy_close_series.loc[last_d]
                sma_val = spy_sma_series.loc[last_d] if last_d in spy_sma_series.index else None
                if pd.notna(spy_cl) and sma_val is not None and not pd.isna(sma_val):
                    spy_below_sma200 = bool(spy_cl < sma_val)

    data_context = {
        "prices_dict": prices_dict,
        "tickers": tickers,
        "weight_mode": weight_mode,
        "regime_state": regime_state,
        "spy_above_sma200": spy_above_sma200 if weight_mode == "regime" and regime_state is None else None,
        "category_weights_override": None,
        "news_dir": None,
        "sector_sentiments_this_week": {},
        "signal_horizon_days_this_week": 5,
        "news_weight_used": 0.0,
        "ensure_ohlcv": ensure_ohlcv,
    }
    week_scores, aux = signal_engine.generate(as_of, tickers, data_context)
    atr_norms = aux.get("atr_norms", {})

    policy_context = {
        "regime_state": regime_state,
        "spy_below_sma200": spy_below_sma200,
        "sideways_risk_scale": sideways_risk_scale,
        "kill_switch_mode": KILL_SWITCH_MODE,
        "kill_switch_active": kill_switch_active,
    }
    gated_scores, _ = policy_engine.apply(as_of, week_scores, aux, policy_context)

    portfolio_context = {"top_n": top_n, "atr_norms": atr_norms, "tickers": tickers}
    if path is not None:
        portfolio_context["path"] = path
    intent = portfolio_engine.build(as_of, gated_scores, portfolio_context)

    universe = list(prices_dict.keys())
    if not intent.tickers:
        return pd.Series(0.0, index=universe)
    weights = {t: intent.weights.get(t, 0.0) for t in universe}
    for t in universe:
        if pd.isna(weights[t]):
            weights[t] = 0.0
    return pd.Series(weights).reindex(universe, fill_value=0.0)
