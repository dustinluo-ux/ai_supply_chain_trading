"""
Canonical target-weight pipeline: regime + spine (SignalEngine -> PolicyEngine -> PortfolioEngine).
Single place for building target weights; used by backtest and execution entrypoints.
Phase 3 (DECISIONS.md D021): optional ML blend when use_ml true — load model once, blend 0.7*base + 0.3*ML.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.data.csv_provider import find_csv_path, ensure_ohlcv

# Phase 3 ML: load once per process (fail-open if load fails)
_ML_MODEL_CACHE = None
_ML_PIPELINE_CACHE = None
_ML_MODEL_PATH_CACHED: str | None = None


def _news_features_for_date(ticker: str, as_of: pd.Timestamp, news_signals: dict) -> dict[str, float]:
    """Compute news-derived feature values (same logic as extract_features_for_date). Returns dict with news_supply, news_sentiment, sentiment_velocity, news_spike."""
    news_signals = news_signals or {}
    date_str = as_of.strftime("%Y-%m-%d") if isinstance(as_of, pd.Timestamp) else str(as_of)
    ticker_news = news_signals.get(ticker, {})
    news = ticker_news.get(date_str) or ticker_news.get(as_of) or {}
    if news is None:
        news = {}
    news_supply = float(news.get("supply_chain_score", news.get("supply_chain", 0.5)))
    news_sentiment = float(news.get("sentiment_score", news.get("sentiment", 0.5)))
    past_sentiment = None
    for offset in [5, 6, 7, 4, 3]:
        past_date = as_of - pd.Timedelta(days=offset)
        past_str = past_date.strftime("%Y-%m-%d")
        if past_str in ticker_news:
            past_news = ticker_news.get(past_str) or {}
            past_sentiment = float(past_news.get("sentiment_score", past_news.get("sentiment", 0.5)))
            break
    sentiment_velocity = (news_sentiment - past_sentiment) if past_sentiment is not None else 0.0
    supply_values = []
    for d in range(1, 21):
        back_str = (as_of - pd.Timedelta(days=d)).strftime("%Y-%m-%d")
        if back_str not in ticker_news:
            continue
        back_news = ticker_news.get(back_str) or {}
        supply_values.append(float(back_news.get("supply_chain_score", back_news.get("supply_chain", 0.5))))
    if len(supply_values) >= 5:
        mean_supply = float(np.mean(supply_values))
        news_spike = (news_supply / mean_supply) if mean_supply > 0 else 1.0
    else:
        news_spike = 1.0
    return {"news_supply": news_supply, "news_sentiment": news_sentiment, "sentiment_velocity": sentiment_velocity, "news_spike": news_spike}


def _build_features_from_precomputed(
    ticker: str,
    as_of: pd.Timestamp,
    precomputed_row: dict,
    news_signals: dict,
    feature_names: list[str],
) -> Optional[list]:
    """Build feature vector in feature_names order from precomputed indicator row + news. Returns None only if precomputed_row is empty/None (no technical data). Missing features are filled with 0.0."""
    if not precomputed_row:
        return None
    values: dict[str, float] = {}
    m5 = precomputed_row.get("momentum_5d_norm")
    m20 = precomputed_row.get("momentum_20d_norm")
    if m5 is not None and m20 is not None:
        values["momentum_avg"] = (float(m5) + float(m20)) / 2.0
    for key, v in precomputed_row.items():
        if v is not None and isinstance(key, str):
            try:
                values[key] = float(v)
            except (TypeError, ValueError):
                pass
    news_feats = _news_features_for_date(ticker, as_of, news_signals)
    values.update(news_feats)
    for name in feature_names:
        if name not in values:
            values[name] = 0.0
    try:
        return [values[name] for name in feature_names]
    except KeyError:
        return None


def apply_ml_blend(
    week_scores: dict[str, float],
    as_of: pd.Timestamp,
    prices_dict: dict,
    news_signals: dict,
    precomputed_indicators: Optional[dict[str, dict[str, float]]] = None,
    model_path_override: Optional[str] = None,
    use_ml_override: bool | None = None,
    ml_blend_weight_override: float | None = None,
) -> dict[str, float]:
    """
    If use_ml and model loaded, blend 0.7*week_scores + 0.3*ML; else return week_scores.
    precomputed_indicators: optional {ticker: {feature_name: float}} from signal_engine aux; avoids double calculate_all_indicators.
    model_path_override: if set, load this .pkl instead of the path in model_config.yaml (used by --track A/B).
    use_ml_override: if not None, overrides config use_ml (e.g. False for --no-ml in backtest).
    """
    global _ML_MODEL_CACHE, _ML_PIPELINE_CACHE, _ML_MODEL_PATH_CACHED
    _root = Path(__file__).resolve().parent.parent.parent
    _model_cfg_path = _root / "config" / "model_config.yaml"
    if not _model_cfg_path.exists():
        return week_scores
    import yaml as _yaml
    with open(_model_cfg_path, "r", encoding="utf-8") as _f:
        _model_cfg = _yaml.safe_load(_f)
    _use_ml = use_ml_override if use_ml_override is not None else _model_cfg.get("use_ml", False)
    if not _use_ml:
        return week_scores
    _ml_blend_weight = float(_model_cfg.get("models", {}).get("ml_blend_weight", _model_cfg.get("ml_blend_weight", 0.3)))
    if ml_blend_weight_override is not None:
        _ml_blend_weight = float(ml_blend_weight_override)
    # model_path_override (from --track A/B) takes priority over config
    if model_path_override:
        _path = Path(model_path_override)
    else:
        _path = _model_cfg.get("training", {}).get("model_path")
        if not _path:
            return week_scores
        _path = (_root / _path) if not Path(_path).is_absolute() else Path(_path)
    # Invalidate cache if the model path changed (e.g. switching tracks mid-process)
    if _ML_MODEL_PATH_CACHED is not None and str(_path) != _ML_MODEL_PATH_CACHED:
        _ML_MODEL_CACHE = None
        _ML_PIPELINE_CACHE = None
    if _ML_MODEL_CACHE is None:
        try:
            from src.models.model_factory import MODEL_REGISTRY
            from src.models.train_pipeline import ModelTrainingPipeline as _MLPipeline
            _active = _model_cfg.get("active_model", "ridge")
            _ML_MODEL_CACHE = MODEL_REGISTRY[_active].load_model(str(_path))
            _ML_PIPELINE_CACHE = _MLPipeline(str(_root / "config" / "model_config.yaml"))
            _ML_MODEL_PATH_CACHED = str(_path)
        except Exception as _e:
            logging.warning("ML model load failed (apply_ml_blend): %s", _e)
            return week_scores
    if _ML_MODEL_CACHE is None or _ML_PIPELINE_CACHE is None:
        return week_scores
    _news_signals = news_signals or {}
    _feature_names = getattr(_ML_PIPELINE_CACHE, "feature_names", [])
    _X_list, _ticker_list = [], []
    for _t in week_scores:
        _feats = None
        if precomputed_indicators and _t in precomputed_indicators and _feature_names:
            _feats = _build_features_from_precomputed(
                _t, as_of, precomputed_indicators[_t], _news_signals, _feature_names
            )
        if _feats is None and not precomputed_indicators:
            _feats = _ML_PIPELINE_CACHE.extract_features_for_date(_t, as_of, prices_dict, _news_signals)
        if _feats is not None:
            _X_list.append(_feats)
            _ticker_list.append(_t)
    if not _X_list:
        return week_scores
    _X = np.array(_X_list)
    _ml_raw = np.asarray(_ML_MODEL_CACHE.predict(np.nan_to_num(_X, nan=0.0))).ravel()
    _mn, _mx = float(_ml_raw.min()), float(_ml_raw.max())
    if _mx - _mn > 0:
        _ml_scaled = (_ml_raw - _mn) / (_mx - _mn)
    else:
        _ml_scaled = np.full_like(_ml_raw, 0.5)
    _ml_score = {_ticker_list[_i]: float(_ml_scaled[_i]) for _i in range(len(_ticker_list))}
    for _t in week_scores:
        if _t not in _ml_score:
            _ml_score[_t] = 0.5
    _base_weight = 1.0 - _ml_blend_weight
    _blended = {}
    for _t in week_scores:
        _blended[_t] = _base_weight * week_scores[_t] + _ml_blend_weight * _ml_score[_t]
        if _ml_score[_t] < 0.4 and week_scores[_t] > 0.6:
            _blended[_t] *= 0.5
    return _blended


BENCHMARK_TICKER = "SPY"
SMA_KILL_SWITCH_DAYS = 200
KILL_SWITCH_MODE = "cash"


def _spy_benchmark_series(data_dir: Path) -> Optional[tuple[pd.Series, pd.Series]]:
    """Load SPY; return (close, sma200) aligned to SPY index. None if SPY not found."""
    path = find_csv_path(data_dir, BENCHMARK_TICKER)
    if not path:
        return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=False)
        df.index = pd.to_datetime(df.index, format="mixed", dayfirst=True)
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
    llm_enabled: bool = True,
    return_aux: bool = False,
    use_ml_override: bool | None = None,
    score_floor: Optional[float] = None,
) -> pd.Series | tuple[pd.Series, dict]:
    """
    Canonical spine:
    SignalEngine -> PolicyEngine -> PortfolioEngine
    Returns pd.Series(intent.weights) indexed by full universe.
    If return_aux=True, returns (weights_series, aux) with aux: scores, vol_20d, vol_triggered.
    path: if "weekly" then intent mode is execution; else backtest (no path in context).
    """
    from src.signals.signal_engine import SignalEngine
    from src.core import PolicyEngine, PortfolioEngine

    signal_engine = SignalEngine()
    policy_engine = PolicyEngine()
    portfolio_engine = PortfolioEngine()

    if len(tickers) < top_n:
        out = pd.Series(0.0, index=tickers)
        if return_aux:
            return (out, {"scores": {}, "vol_20d": {}, "vol_triggered": {}})
        return out

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

    # news_dir from config if enabled and directory exists
    _news_dir = None
    try:
        import yaml
        _root = Path(__file__).resolve().parent.parent.parent
        _cfg_path = _root / "config" / "config.yaml"
        if _cfg_path.exists():
            with open(_cfg_path, "r", encoding="utf-8") as _f:
                _cfg = yaml.safe_load(_f)
            _news = _cfg.get("news", {})
            if _news.get("enabled", False):
                _path_str = _news.get("data_dir", "data/news")
                _full = (_root / _path_str) if not Path(_path_str).is_absolute() else Path(_path_str)
                if _full.is_dir():
                    _news_dir = _path_str if not Path(_path_str).is_absolute() else str(_full)
    except Exception:
        pass

    data_context = {
        "prices_dict": prices_dict,
        "tickers": tickers,
        "weight_mode": weight_mode,
        "regime_state": regime_state,
        "spy_above_sma200": spy_above_sma200 if weight_mode == "regime" and regime_state is None else None,
        "category_weights_override": None,
        "news_dir": _news_dir,
        "sector_sentiments_this_week": {},
        "signal_horizon_days_this_week": 5,
        "news_weight_used": 0.0,
        "ensure_ohlcv": ensure_ohlcv,
        "llm_enabled": llm_enabled,
    }
    week_scores, aux = signal_engine.generate(as_of, tickers, data_context)
    atr_norms = aux.get("atr_norms", {})

    # Phase 3 wiring (docs/ml_ic_diagnosis.md § Phase 3 Wiring Plan): ML blend when use_ml true
    scores_to_use = week_scores
    _root = Path(__file__).resolve().parent.parent.parent
    _model_cfg_path = _root / "config" / "model_config.yaml"
    if _model_cfg_path.exists():
        import yaml as _yaml
        with open(_model_cfg_path, "r", encoding="utf-8") as _f:
            _model_cfg = _yaml.safe_load(_f)
        _use_ml = use_ml_override if use_ml_override is not None else _model_cfg.get("use_ml", False)
        if _use_ml:
            _ml_bw = float(_model_cfg.get("models", {}).get("ml_blend_weight", _model_cfg.get("ml_blend_weight", 0.3)))
            global _ML_MODEL_CACHE, _ML_PIPELINE_CACHE
            if _ML_MODEL_CACHE is None:
                _path = _model_cfg.get("training", {}).get("model_path")
                if _path:
                    _path = (_root / _path) if not Path(_path).is_absolute() else Path(_path)
                    try:
                        from src.models.model_factory import MODEL_REGISTRY
                        from src.models.train_pipeline import ModelTrainingPipeline as _MLPipeline
                        _active = _model_cfg.get("active_model", "ridge")
                        _ML_MODEL_CACHE = MODEL_REGISTRY[_active].load_model(str(_path))
                        _ML_PIPELINE_CACHE = _MLPipeline(str(_root / "config" / "model_config.yaml"))
                    except Exception as _e:
                        logging.warning("ML model load failed (fail-open): %s", _e)
                        _ML_MODEL_CACHE = None
                        _ML_PIPELINE_CACHE = None
            if _ML_MODEL_CACHE is not None and _ML_PIPELINE_CACHE is not None:
                _news_signals = data_context.get("news_signals") or {}
                _X_list, _ticker_list = [], []
                for _t in week_scores:
                    _feats = _ML_PIPELINE_CACHE.extract_features_for_date(_t, as_of, prices_dict, _news_signals)
                    if _feats is not None:
                        _X_list.append(_feats)
                        _ticker_list.append(_t)
                if _X_list:
                    _X = np.array(_X_list)
                    _ml_raw = _ML_MODEL_CACHE.predict(_X)
                    _mn, _mx = float(_ml_raw.min()), float(_ml_raw.max())
                    if _mx - _mn > 0:
                        _ml_scaled = (_ml_raw - _mn) / (_mx - _mn)
                    else:
                        _ml_scaled = np.full_like(_ml_raw, 0.5)
                    _ml_score = {_ticker_list[_i]: float(_ml_scaled[_i]) for _i in range(len(_ticker_list))}
                    for _t in week_scores:
                        if _t not in _ml_score:
                            _ml_score[_t] = 0.5
                    _bw = 1.0 - _ml_bw
                    _blended = {}
                    for _t in week_scores:
                        _blended[_t] = _bw * week_scores[_t] + _ml_bw * _ml_score[_t]
                        if _ml_score[_t] < 0.4 and week_scores[_t] > 0.6:
                            _blended[_t] *= 0.5
                    scores_to_use = _blended

    # Task 6 (docs/ml_ic_diagnosis.md): volatility filter — scale score when 20d realized vol
    # exceeds percentile_threshold of 252d rolling vol history. Task 7: collect vol_20d, vol_triggered for aux.
    _vol_20d_dict: dict = {}
    _vol_triggered_dict: dict = {}
    _vol_cfg_path = _root / "config" / "technical_master_score.yaml"
    if _vol_cfg_path.exists():
        import yaml as _yaml_vol
        with open(_vol_cfg_path, "r", encoding="utf-8") as _f2:
            _vol_cfg = _yaml_vol.safe_load(_f2)
        _vf = _vol_cfg.get("volatility_filter") or {}
        if _vf.get("enabled", False):
            _lookback = int(_vf.get("lookback_days", 252))
            _pct = float(_vf.get("percentile_threshold", 95))
            _scale = float(_vf.get("scale_factor", 0.5))
            _scores_copy = dict(scores_to_use)
            for _t in list(_scores_copy.keys()):
                if _t not in prices_dict:
                    continue
                _df = prices_dict[_t]
                if _df.empty or "close" not in _df.columns:
                    continue
                _slice = _df[_df.index <= as_of]
                if _slice is None or len(_slice) < 60:
                    continue
                _close = _slice["close"] if isinstance(_slice["close"], pd.Series) else _slice.loc[:, "close"]
                _close = _close.sort_index()
                _log_ret = np.log(_close / _close.shift(1)).dropna()
                if len(_log_ret) < 20:
                    continue
                _vol_20d = _log_ret.rolling(20, min_periods=20).std() * np.sqrt(252)
                _vol_20d = _vol_20d.dropna()
                if len(_vol_20d) == 0:
                    continue
                _today_vol = float(_vol_20d.iloc[-1])
                _vol_20d_dict[_t] = _today_vol
                _history = _vol_20d.tail(_lookback)
                if len(_history) < 60:
                    _vol_triggered_dict[_t] = False
                    continue
                _threshold = float(np.percentile(_history, _pct))
                if _today_vol > _threshold:
                    _scores_copy[_t] *= _scale
                    _vol_triggered_dict[_t] = True
                    logging.warning(
                        "[VolFilter] %s vol=%.3f (p%.0f=%.3f) → score scaled by %.2f",
                        _t, _today_vol, _pct, _threshold, _scale,
                    )
                else:
                    _vol_triggered_dict[_t] = False
            scores_to_use = _scores_copy
    for _t in scores_to_use:
        _vol_20d_dict.setdefault(_t, None)
        _vol_triggered_dict.setdefault(_t, False)

    policy_context = {
        "regime_state": regime_state,
        "spy_below_sma200": spy_below_sma200,
        "sideways_risk_scale": sideways_risk_scale,
        "kill_switch_mode": KILL_SWITCH_MODE,
        "kill_switch_active": kill_switch_active,
    }
    gated_scores, _ = policy_engine.apply(as_of, scores_to_use, aux, policy_context)

    portfolio_context = {"top_n": top_n, "atr_norms": atr_norms, "tickers": tickers}
    if path is not None:
        portfolio_context["path"] = path
    if score_floor is not None:
        portfolio_context["score_floor"] = score_floor
    intent = portfolio_engine.build(as_of, gated_scores, portfolio_context)

    # Task 6 (task6_validation.md BUG 2): restrict to requested universe only. Propagation
    # may add tickers to scores/intent; only tickers in the input tickers param appear in output.
    requested_set = set(tickers)
    if not intent.tickers:
        out = pd.Series(0.0, index=list(tickers))
        if return_aux:
            return (out, {"scores": dict(scores_to_use), "vol_20d": _vol_20d_dict, "vol_triggered": _vol_triggered_dict})
        return out
    weights = {t: intent.weights.get(t, 0.0) for t in requested_set}
    for t in requested_set:
        if pd.isna(weights.get(t, 0.0)):
            weights[t] = 0.0
    total = sum(weights.values())
    if total > 0 and abs(total - 1.0) > 1e-9:
        for t in weights:
            weights[t] /= total
    weights_series = pd.Series(weights).reindex(list(tickers), fill_value=0.0)
    if return_aux:
        return (weights_series, {"scores": dict(scores_to_use), "vol_20d": _vol_20d_dict, "vol_triggered": _vol_triggered_dict})
    return weights_series
