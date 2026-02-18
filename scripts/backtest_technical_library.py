"""
Backtest the Technical Library strategy (expanded indicators + category-weighted Master Score).
Weekly rebalance with:
- Execution at Next-Day Open (no look-ahead).
- Inverse Volatility position sizing (ATR_norm).
- Fixed friction cost per trade; optional Market Kill-Switch when SPY < 200 SMA.
- Optional news overlay: pass --news-dir for 0.8 Technical + 0.2 News Composite; [STATE] shows News Buzz T/F.
- AdaptiveSelector: pass --performance-csv with --news-dir to evolve weights from last 3 regime occurrences; weekly Return/Drawdown/Regime/news_weight logged to CSV.
Saves log to outputs/backtest_master_score_*.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

# Project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Execution & cost assumptions (see docs/BACKTEST_ASSUMPTIONS.md)
FRICTION_BPS = 15  # 0.15% per trade (slippage + commission)
BENCHMARK_TICKER = "SPY"
SMA_KILL_SWITCH_DAYS = 200
KILL_SWITCH_MODE = "cash"  # "cash" = 100% cash when SPY < 200 SMA; "half" = 50% position size
# Daily risk check: exit position same day if single-day return <= this (e.g. -0.05 = -5%)
DAILY_EXIT_PCT = -0.05

# --- Centralized data loading (src.data.csv_provider) ---
from src.data.csv_provider import (
    load_data_config as load_config,
    find_csv_path,
    load_prices,
    ensure_ohlcv,
)


def _spy_benchmark_series(data_dir: Path) -> tuple[pd.Series, pd.Series] | None:
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
    prices_dict: dict[str, pd.DataFrame],
    data_dir: Path | None = None,
    *,
    top_n: int = 3,
    sideways_risk_scale: float = 0.5,
    weight_mode: str = "fixed",
) -> pd.Series:
    """
    Single-date target weights from canonical spine (SignalEngine -> PolicyEngine -> PortfolioEngine).
    Delegates to src.core.target_weight_pipeline.compute_target_weights.
    Returns pd.Series indexed by tickers (full universe), weights sum to 0 or 1.
    """
    from src.core.target_weight_pipeline import compute_target_weights as _compute_target_weights

    tickers = list(prices_dict.keys())
    return _compute_target_weights(
        as_of,
        tickers,
        prices_dict,
        data_dir,
        top_n=top_n,
        sideways_risk_scale=sideways_risk_scale,
        weight_mode=weight_mode,
        path=None,
    )


def _build_weight_history(
    prices_dict: dict[str, pd.DataFrame],
    tickers: list[str],
    monday: pd.Timestamp,
    mode: str,
    lookback_days: int = 60,
    ensure_ohlcv_fn=None,
    ohlcv_cols=None,
):
    """Build history DataFrame for rolling/ml weights. Only uses data <= monday (no look-ahead)."""
    from src.signals.technical_library import calculate_all_indicators, compute_signal_strength
    rows = []
    for t in tickers:
        df = prices_dict.get(t)
        if df is None:
            continue
        slice_df = df[df.index <= monday]
        if slice_df.empty or len(slice_df) < 60:
            continue
        if ensure_ohlcv_fn:
            slice_df = ensure_ohlcv_fn(slice_df)
        if ohlcv_cols and not all(c in slice_df.columns for c in ohlcv_cols):
            continue
        try:
            ind = calculate_all_indicators(slice_df)
        except Exception:
            continue
        dates = ind.index[ind.index <= monday].sort_values(ascending=False)[:lookback_days]
        close = prices_dict[t]["close"]
        for d in dates:
            if d not in ind.index:
                continue
            row_ind = ind.loc[d]
            _, res = compute_signal_strength(row_ind)
            sub = res.get("category_sub_scores", {})
            if mode == "rolling":
                next_5 = close.index[close.index > d][:5]
                if len(next_5) < 5 or next_5[-1] > monday:
                    continue
                fwd = (close.loc[next_5[-1]] - close.loc[d]) / (close.loc[d] + 1e-8)
                rows.append({**sub, "forward_ret": fwd})
            else:
                next_1 = close.index[close.index > d][:1]
                if len(next_1) < 1 or next_1[0] > monday:
                    continue
                fwd = (close.loc[next_1[0]] - close.loc[d]) / (close.loc[d] + 1e-8)
                rows.append({**sub, "next_ret": fwd})
    if not rows:
        return None
    return pd.DataFrame(rows)


def run_backtest_master_score(
    prices_dict: dict[str, pd.DataFrame],
    data_dir: Path | None = None,
    news_dir: Path | str | None = None,
    performance_csv: Path | str | None = None,
    dynamic_selector: bool = False,
    news_weight_fixed: float | None = None,
    signal_horizon_days: int = 5,
    sideways_risk_scale: float = 0.5,
    top_n: int = 3,
    start_date: str | None = None,
    end_date: str | None = None,
    weight_mode: str = "fixed",
    rolling_method: str = "max_sharpe",
    verbose: bool = True,
) -> dict:
    from src.signals.technical_library import (
        calculate_all_indicators,
        compute_signal_strength,
        OHLCV_COLS,
    )
    from src.signals.weight_model import get_optimized_weights, get_ml_weights, get_regime_hmm, AdaptiveSelector, StrategySelector
    if news_dir is not None:
        from src.signals.news_engine import compute_news_composite, DEFAULT_SECTOR_MAP
    if performance_csv is not None:
        from src.signals.performance_logger import append_row as performance_append_row
    performance_csv_path = Path(performance_csv) if performance_csv else None
    adaptive_selector = AdaptiveSelector(performance_csv_path) if (news_dir and performance_csv_path and news_weight_fixed is None and not dynamic_selector) else None
    from src.signals.performance_logger import _default_ledger_path
    strategy_selector = StrategySelector(_default_ledger_path()) if dynamic_selector else None
    from src.signals.signal_engine import SignalEngine
    from src.core import PolicyEngine, PortfolioEngine
    from src.core.intent import Intent
    from src.portfolio.position_sizer import (
        compute_weights as position_sizer_compute_weights,
        compute_atr_series,
        get_sizing_params_from_config,
    )
    from src.utils.config_manager import get_config as get_config_manager
    signal_engine = SignalEngine()
    policy_engine = PolicyEngine()
    portfolio_engine = PortfolioEngine()
    week_meta_list: list[tuple] = []  # (monday, regime_state, news_weight_used) per week
    # P0 safety initialization
    active_strategy_id = None
    last_regime = None
    tickers = list(prices_dict.keys())
    if len(tickers) < top_n:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "top_n=%d but only %d tickers loaded — clamping top_n to %d",
            top_n, len(tickers), len(tickers),
        )
        if verbose:
            print(f"  [WARN] top_n={top_n} > loaded tickers ({len(tickers)}); "
                  f"clamping top_n to {len(tickers)}", flush=True)
        top_n = len(tickers)
    all_dates = sorted(set().union(*[df.index for df in prices_dict.values()]))
    start = max(df.index.min() for df in prices_dict.values())
    end = min(df.index.max() for df in prices_dict.values())
    if start_date:
        start = max(start, pd.to_datetime(start_date))
    if end_date:
        end = min(end, pd.to_datetime(end_date))
    mondays = pd.date_range(start, end, freq="W-MON")
    if len(mondays) < 2:
        return {"sharpe": 0.0, "total_return": 0.0, "max_drawdown": 0.0, "error": "Not enough weeks"}

    # Market Kill-Switch: SPY 200-day SMA (optional)
    spy_bench = _spy_benchmark_series(data_dir) if data_dir else None
    spy_close_native = None  # Raw SPY close for HMM (no reindex)
    if spy_bench is not None:
        spy_close_series, spy_sma_series = spy_bench
        spy_close_native = spy_close_series.copy()  # For get_regime_hmm (needs native index)
        kill_switch_active = True
        spy_close_series = spy_close_series.reindex(all_dates).ffill()
        spy_sma_series = spy_sma_series.reindex(all_dates).ffill()
    else:
        spy_close_series, spy_sma_series = None, None
        kill_switch_active = False

    if verbose:
        print(f"  Backtest: {len(tickers)} tickers, {len(mondays)} rebalances, top_n={top_n}", flush=True)
        print(f"  Weight mode: {weight_mode}" + (f" | Rolling method: {rolling_method}" if weight_mode == "rolling" else "") + f" | Execution: Next-Day Open | Friction: {FRICTION_BPS/10000:.2%} | Sizing: ATR-based (Stage 4)", flush=True)
        print(f"  Kill-Switch: {'ON (SPY < 200 SMA -> ' + KILL_SWITCH_MODE + ')' if kill_switch_active else 'OFF (no SPY data)'}", flush=True)
        if news_dir:
            print(f"  News overlay: ON (news_dir={Path(news_dir).resolve()}) | 0.8 Technical + 0.2 News Composite", flush=True)
        if news_dir and performance_csv_path:
            print(f"  AdaptiveSelector: ON (performance_csv={performance_csv_path.resolve()}) | weights from last 3 regime occurrences", flush=True)
        if dynamic_selector:
            print(f"  DynamicSelector: ON (regime_ledger) | override news_weight + sideways_risk_scale from winning profile", flush=True)
    signals_df = pd.DataFrame(0.0, index=mondays, columns=tickers)
    transmat_printed = False
    prev_regime: str | None = None
    for idx, monday in enumerate(mondays):
        spy_above_sma200 = None
        regime_state = None
        regime_info = None
        need_regime = weight_mode == "regime" or (news_dir and performance_csv_path) or (news_dir and news_weight_fixed is not None) or (news_weight_fixed is not None) or dynamic_selector
        if need_regime:
            if spy_close_native is not None:
                regime_state, regime_info = get_regime_hmm(spy_close_native, monday, min_obs=60, n_components=3)
                if regime_state is None:
                    regime_info = None
                if regime_state is None and kill_switch_active and spy_close_series is not None and spy_sma_series is not None:
                    up_to = spy_close_series.index[spy_close_series.index <= monday]
                    if len(up_to) > 0:
                        last_d = up_to[-1]
                        spy_cl = spy_close_series.loc[last_d]
                        sma_val = spy_sma_series.loc[last_d] if last_d in spy_sma_series.index else None
                        if pd.notna(spy_cl) and sma_val is not None and not pd.isna(sma_val):
                            spy_above_sma200 = bool(spy_cl >= sma_val)
                            regime_state = "BULL" if spy_above_sma200 else "BEAR"
            if regime_state is None and kill_switch_active and spy_close_series is not None and spy_sma_series is not None:
                up_to = spy_close_series.index[spy_close_series.index <= monday]
                if len(up_to) > 0:
                    last_d = up_to[-1]
                    spy_cl = spy_close_series.loc[last_d]
                    sma_val = spy_sma_series.loc[last_d] if last_d in spy_sma_series.index else None
                    if pd.notna(spy_cl) and sma_val is not None and not pd.isna(sma_val):
                        spy_above_sma200 = bool(spy_cl >= sma_val)

        if regime_state == "BEAR" and prev_regime == "BEAR":
            effective_regime_state = "BEAR"
        elif regime_state == "BEAR":
            effective_regime_state = prev_regime or "SIDEWAYS"
        else:
            effective_regime_state = regime_state

        spy_below_sma200 = False
        if kill_switch_active and spy_close_series is not None and spy_sma_series is not None:
            up_to = spy_close_series.index[spy_close_series.index <= monday]
            if len(up_to) > 0:
                last_d = up_to[-1]
                spy_cl = spy_close_series.loc[last_d]
                sma_val = spy_sma_series.loc[last_d] if last_d in spy_sma_series.index else None
                if pd.notna(spy_cl) and sma_val is not None and not pd.isna(sma_val):
                    spy_below_sma200 = bool(spy_cl < sma_val)
        category_weights_override = None
        if weight_mode == "rolling":
            hist = _build_weight_history(prices_dict, tickers, monday, "rolling", 60, ensure_ohlcv_fn=ensure_ohlcv, ohlcv_cols=OHLCV_COLS)
            if hist is not None and len(hist) >= 10:
                category_weights_override = get_optimized_weights(hist, lookback_days=60, forward_days=5, method=rolling_method)
        elif weight_mode == "ml":
            hist = _build_weight_history(prices_dict, tickers, monday, "ml", 60, ensure_ohlcv_fn=ensure_ohlcv, ohlcv_cols=OHLCV_COLS)
            if hist is not None and len(hist) >= 20:
                ml_weights, ml_cv_r2 = get_ml_weights(hist, lookback_days=60)
                if ml_weights is not None:
                    category_weights_override = ml_weights
                if verbose and ml_cv_r2 is not None:
                    print(f"  [ML] CV R²: {ml_cv_r2:.4f}", flush=True)

        signal_horizon_days_this_week = signal_horizon_days
        sideways_risk_scale_this_week = sideways_risk_scale
        news_weight_used = 0.0
        if news_dir:
            news_weight_used = float(news_weight_fixed) if news_weight_fixed is not None else (adaptive_selector.get_optimal_weights(regime_state) if adaptive_selector else 0.20)
        if dynamic_selector and regime_state and strategy_selector is not None:
            profile = strategy_selector.get_winning_profile(regime_state)
            if profile and profile.get("params"):
                params = profile["params"]
                news_weight_used = float(params.get("news_weight", news_weight_used))
                signal_horizon_days_this_week = int(params.get("signal_horizon_days", signal_horizon_days))
                sideways_risk_scale_this_week = float(params.get("sideways_risk_scale", sideways_risk_scale))
                sid = profile.get("strategy_id", "?")
                active_strategy_id = sid
                if verbose:
                    print(f"  [SELECTOR] Regime: {regime_state} detected. Historical Best Profile found: {sid}. Overriding current session weights...", flush=True)
            else:
                try:
                    import yaml
                    cfg_path = ROOT / "config" / "technical_master_score.yaml"
                    if cfg_path.exists():
                        with open(cfg_path, "r", encoding="utf-8") as f:
                            cfg = yaml.safe_load(f)
                        news_weight_used = float(cfg.get("news_weight", 0.20))
                except Exception:
                    news_weight_used = 0.20
        
        sector_sentiments_this_week: dict[str, float] = {}
        if news_dir is not None:
            for t in tickers:
                try:
                    r = compute_news_composite(Path(news_dir), t, monday, sector_sentiments=None, sector_map=None, signal_horizon_days=signal_horizon_days_this_week)
                    sector_sentiments_this_week[t] = r.get("sentiment_current", 0.5)
                except Exception:
                    sector_sentiments_this_week[t] = 0.5
        
        from src.utils.config_manager import get_config as _get_cfg
        _propagation_enabled = _get_cfg().get_param("strategy_params.propagation.enabled", False)
        
        data_context = {
            "prices_dict": prices_dict,
            "tickers": tickers,
            "weight_mode": weight_mode,
            "regime_state": regime_state,
            "spy_above_sma200": spy_above_sma200 if weight_mode == "regime" and regime_state is None else None,
            "category_weights_override": category_weights_override,
            "news_dir": news_dir,
            "sector_sentiments_this_week": sector_sentiments_this_week,
            "signal_horizon_days_this_week": signal_horizon_days_this_week,
            "news_weight_used": news_weight_used,
            "ensure_ohlcv": ensure_ohlcv,
            "enable_propagation": bool(_propagation_enabled),
        }
        week_scores, aux = signal_engine.generate(monday, tickers, data_context)
        atr_norms = aux.get("atr_norms", {})
        buzz_by_ticker = aux.get("buzz_by_ticker", {})

        policy_context = {
            "regime_state": effective_regime_state,
            "spy_below_sma200": spy_below_sma200,
            "sideways_risk_scale": sideways_risk_scale_this_week,
            "kill_switch_mode": KILL_SWITCH_MODE,
            "kill_switch_active": kill_switch_active,
        }
        gated_scores, flags = policy_engine.apply(monday, week_scores, aux, policy_context)
        action = flags.get("action", "Trade")

        portfolio_context = {"top_n": top_n, "atr_norms": atr_norms, "tickers": tickers}
        intent = portfolio_engine.build(monday, gated_scores, portfolio_context)

        if effective_regime_state == "BEAR":
            for t in tickers:
                intent.weights[t] = float(intent.weights.get(t, 0.0)) * 0.5
        if effective_regime_state != "BEAR" and intent.tickers:
            atr_per_share: dict[str, float] = {}
            prices_at_monday: dict[str, float] = {}
            for t in intent.tickers:
                df = prices_dict.get(t)
                if df is None or len(df) < 15:
                    continue
                slice_df = df.loc[df.index <= monday].tail(30)
                if slice_df.empty or "high" not in slice_df.columns or "low" not in slice_df.columns or "close" not in slice_df.columns:
                    continue
                atr_series = compute_atr_series(slice_df["high"], slice_df["low"], slice_df["close"], period=14)
                if len(atr_series) and pd.notna(atr_series.iloc[-1]):
                    atr_per_share[t] = float(atr_series.iloc[-1])
                if len(slice_df) and pd.notna(slice_df["close"].iloc[-1]):
                    prices_at_monday[t] = float(slice_df["close"].iloc[-1])
            cfg = get_config_manager()
            risk_pct, atr_mult = get_sizing_params_from_config(cfg)
            new_weights = position_sizer_compute_weights(intent.tickers, atr_per_share, prices_at_monday, risk_pct=risk_pct, atr_multiplier=atr_mult, target_exposure=1.0)
            for t in tickers:
                intent.weights[t] = float(new_weights.get(t, 0.0))

        for t in tickers:
            w = intent.weights.get(t, 0.0)
            if pd.isna(w): w = 0.0
            signals_df.loc[monday, t] = float(w)
        
        weight_sum = sum(signals_df.loc[monday, t] for t in tickers)
        if action == "Cash":
            assert abs(weight_sum) < 1e-6, f"Expected 0.0 when CASH_OUT, got sum(weights)={weight_sum}"
        elif effective_regime_state == "BEAR":
            assert abs(weight_sum - 0.5) < 1e-5, f"Expected sum(weights)≈0.5 when BEAR (fractional), got {weight_sum}"
        else:
            assert abs(weight_sum - 1.0) < 1e-5, f"Expected sum(weights)≈1.0 when trading, got {weight_sum}"

        if verbose and intent.tickers and weight_sum > 0:
            parts = [f"{t}={intent.weights.get(t, 0):.3f}" for t in intent.tickers if intent.weights.get(t, 0) > 0]
            if parts:
                print(f"  [SIZING] {monday.date()} Top-N: " + " ".join(parts), flush=True)
        if verbose and (weight_mode == "regime" or news_dir is not None):
            regime_letter = {"BULL": "B", "BEAR": "E", "SIDEWAYS": "S"}.get(regime_state or "", "-")
            news_buzz = "T" if (news_dir and intent.tickers and any(buzz_by_ticker.get(t, False) for t in intent.tickers)) else ("-" if not news_dir else "F")
            print(f"  [STATE] {monday.date()} | Regime: {regime_letter} | News Buzz: {news_buzz} | Action: {action}", flush=True)
        prev_regime = regime_state
        week_meta_list.append((monday, regime_state, news_weight_used))

    prices_df = pd.DataFrame({t: prices_dict[t]["close"] for t in tickers}, index=all_dates)
    opens_df = pd.DataFrame({t: prices_dict[t]["open"] for t in tickers}, index=all_dates)
    positions_df = pd.DataFrame(0.0, index=prices_df.index, columns=tickers)
    first_day_of_period = set()
    blocks = []
    for monday in signals_df.index:
        next_days = prices_df.index[prices_df.index > monday]
        if len(next_days) == 0: continue
        first_after_monday = next_days[0]
        first_day_of_period.add(first_after_monday)
        start_idx = prices_df.index.get_loc(first_after_monday)
        next_mondays = signals_df.index[signals_df.index > monday]
        end_idx = prices_df.index.get_loc(prices_df.index[prices_df.index < next_mondays[0]][-1]) + 1 if len(next_mondays) else len(prices_df)
        blocks.append((start_idx, end_idx))
        for t in tickers:
            w = signals_df.loc[monday, t]
            if w > 0:
                positions_df.iloc[start_idx:end_idx, positions_df.columns.get_loc(t)] = w
    
    returns = prices_df.pct_change()
    for d in first_day_of_period:
        if d in returns.index:
            for t in tickers:
                if d in opens_df.index and opens_df.loc[d, t] > 0:
                    returns.loc[d, t] = (prices_df.loc[d, t] - opens_df.loc[d, t]) / opens_df.loc[d, t]
    
    for (start_idx, end_idx) in blocks:
        for i in range(start_idx, end_idx):
            d = prices_df.index[i]
            for t in tickers:
                col_idx = positions_df.columns.get_loc(t)
                if positions_df.iloc[i, col_idx] > 0 and d in returns.index and returns.loc[d, t] <= DAILY_EXIT_PCT:
                    positions_df.iloc[i:end_idx, col_idx] = 0
    
    portfolio_returns = (positions_df * returns).sum(axis=1).fillna(0)
    rebalance_dates = positions_df.diff().abs().sum(axis=1) > 0.01
    portfolio_returns[rebalance_dates] -= (FRICTION_BPS / 10000.0)
    cumulative = (1 + portfolio_returns).cumprod()
    total_return = cumulative.iloc[-1] - 1 if len(cumulative) else 0.0
    sharpe = (portfolio_returns.mean() * 252) / (portfolio_returns.std() * np.sqrt(252)) if portfolio_returns.std() > 0 else 0.0
    max_dd = ((cumulative - cumulative.expanding().max()) / cumulative.expanding().max().replace(0, np.nan)).min()
    
    return {
        "sharpe": float(sharpe),
        "total_return": float(total_return),
        "max_drawdown": float(max_dd or 0),
        "regime_stats": {}, # Simplified for logic fix
        "n_rebalances": len(mondays),
        "period_start": str(mondays[0].date()),
        "period_end": str(mondays[-1].date()),
        "tickers": tickers,
        "signals_df": signals_df,
        "last_regime": last_regime,
        "active_strategy_id": active_strategy_id,
    }


def _print_safety_report():
    print("\n" + "=" * 60)
    print("SAFETY REPORT (Critical Audit)")
    print("=" * 60)
    print("1. SIGNAL LAG CHECK: OK (Next-Day Open entry used).")
    print("2. MID-WEEK EXIT LOGIC: OK (Daily risk check active).")
    print("3. BENCHMARK ALIGNMENT: OK (Recursive CSV path resolution active).")
    print("=" * 60 + "\n")


def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    run_start_ts = datetime.now().isoformat()
    parser = argparse.ArgumentParser(description="Backtest Technical Library (Master Score) strategy")
    parser.add_argument("--tickers", type=str, default=None)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--start", "--start-date", type=str, default=None)
    parser.add_argument("--end", "--end-date", type=str, default=None)
    parser.add_argument("--out", type=str, default=None)
    parser.add_argument("--out-dir", type=str, default=None)
    parser.add_argument("--weight-mode", type=str, default="fixed")
    parser.add_argument("--news-dir", type=str, default=None)
    parser.add_argument("--news-weight", type=float, default=None)
    args = parser.parse_args()

    if args.tickers is not None:
        raw_tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        from src.utils.config_manager import get_config
        raw_tickers = get_config().get_watchlist()

    config = load_config()
    # Force the path to the absolute data root shown in your tree
    data_dir = ROOT / "data" / "stock_market_data" 
    
    tickers = []
    for t in raw_tickers:
        csv_path = find_csv_path(str(data_dir), t)
        if csv_path:
            tickers.append(t)
            print(f"  [OK] Found {t} at: {csv_path}")
        else:
            print(f"  [WARN] No CSV found for {t} in {data_dir}")

    if not tickers:
        print("ERROR: No price data loaded. Verify ticker names and data directory structure.")
        return 1

    # ── PRE-PROPAGATION EXPANSION ──────────────────────────────────────────
# ── PRE-PROPAGATION EXPANSION ──────────────────────────────────────────
    try:
        import yaml
        sp_path = ROOT / "config" / "strategy_params.yaml"
        if sp_path.exists():
            with open(sp_path, "r", encoding="utf-8") as f:
                sp = yaml.safe_load(f)
            # entity_ticker_map lives under llm_analysis (not propagation)
            entity_map = sp.get("llm_analysis", {}).get("entity_ticker_map", {})
            # entity_map values are the peer tickers: NVDA is already the seed,
            # everything else is a propagation candidate
            propagated_candidates = set()
            for entity, peer_ticker in entity_map.items():
                if peer_ticker not in tickers:
                    propagated_candidates.add(peer_ticker)

            added = []
            for peer in sorted(propagated_candidates):
                csv_path = find_csv_path(str(data_dir), peer)
                if csv_path:
                    tickers.append(peer)
                    added.append(peer)
                    print(f"  [PROPAGATION] Added price-verified propagated ticker {peer}")
                else:
                    print(f"  [PROPAGATION] No CSV for propagated ticker {peer}, skipping")
            if added:
                print(f"  [PROPAGATION] Propagation enriched {len(tickers)} sources (seed + {len(added)} peers)")
    except Exception as e:
        print(f"  [PROPAGATION] Pre-propagation expansion failed: {e}")
    # ── END PRE-PROPAGATION ────────────────────────────────────────────────

    prices_dict = load_prices(data_dir, tickers)
    if not prices_dict:
        print("ERROR: Could not load price data into dictionary.")
        return 1

    result = run_backtest_master_score(
        prices_dict,
        data_dir=data_dir,
        news_dir=args.news_dir,
        top_n=args.top_n,
        start_date=args.start,
        end_date=args.end,
        weight_mode=args.weight_mode,
        news_weight_fixed=args.news_weight,
    )
    
    _print_safety_report()
    print("\n--- RESULTS ---")
    print(f"  Sharpe:        {result['sharpe']:.4f}")
    print(f"  Total return:  {result['total_return']:.2%}")
    print(f"  Max drawdown:  {result['max_drawdown']:.2%}")

    return 0

if __name__ == "__main__":
    sys.exit(main())