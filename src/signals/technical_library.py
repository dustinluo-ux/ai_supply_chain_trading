"""
Professional-grade technical indicator library.
Uses pandas_ta for all calculations. Normalization: static for bounded (RSI, Stoch, WillR),
rolling min-max (252-day) for unbounded to prevent look-ahead bias.
Category-weighted Master Score: Trend 40%, Momentum 30%, Volume 20%, Volatility 10%
(weights and indicator→category mapping in config/technical_master_score.yaml).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

import numpy as _np
if not hasattr(_np, 'NaN'):
    _np.NaN = _np.nan  # numpy 2.x removed NaN; patch for pandas_ta compatibility

try:
    import pandas_ta as ta
except ImportError:
    raise ImportError("pandas_ta required. Install with: pip install pandas-ta")

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Standard OHLCV column names (lowercase)
OHLCV_COLS = ["open", "high", "low", "close", "volume"]

# Default config path (overridable)
DEFAULT_MASTER_SCORE_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "technical_master_score.yaml"


def _ensure_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure DataFrame has standard OHLCV columns (lowercase)."""
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    missing = [c for c in OHLCV_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"DataFrame missing required columns: {missing}. Found: {list(df.columns)}")
    return df


def _safe_series(series: pd.Series, index: pd.Index) -> pd.Series:
    """Reindex series to match index and fill NaN with 0 for raw (neutral)."""
    if series is None or (hasattr(series, "empty") and series.empty):
        return pd.Series(0.0, index=index)
    out = series.reindex(index).fillna(0.0)
    return out


def _safe_df_columns(df_out: Optional[pd.DataFrame], index: pd.Index) -> dict[str, pd.Series]:
    """Extract columns from a multi-column DataFrame result; reindex and fillna(0)."""
    if df_out is None or (hasattr(df_out, "empty") and df_out.empty):
        return {}
    out = {}
    for c in df_out.columns:
        out[c] = df_out[c].reindex(index).fillna(0.0)
    return out


def _rolling_minmax(series: pd.Series, window: int = 252) -> pd.Series:
    """
    Normalize unbounded series to 0-1 using rolling min-max over the past `window` observations.
    Prevents look-ahead bias: each value is scaled only against its past year of data.
    Inf/NaN replaced with 0.5 (neutral) after scaling.
    """
    s = series.replace([np.inf, -np.inf], np.nan)
    rolling_min = s.rolling(window=window, min_periods=1).min()
    rolling_max = s.rolling(window=window, min_periods=1).max()
    spread = rolling_max - rolling_min
    out = (s - rolling_min) / (spread + 1e-8)
    out = out.clip(0.0, 1.0).fillna(0.5)
    return out


_DEFAULT_WEIGHTS = {"trend": 0.40, "momentum": 0.30, "volume": 0.20, "volatility": 0.10}
_DEFAULT_CATEGORIES = {
    "trend": ["adx_norm", "macd_norm"],
    "momentum": ["rsi_norm", "willr_norm", "stoch_STOCHk_14_3_3_norm", "stoch_STOCHd_14_3_3_norm", "roc_norm", "cci_norm", "momentum_5d_norm", "momentum_20d_norm"],
    "volume": ["volume_ratio_norm", "cmf_norm", "obv_norm"],
    "volatility": ["atr_norm", "bb_position_norm"],
}


def load_master_score_config(config_path: Optional[Path] = None) -> dict[str, Any]:
    """
    Load Master Score config from config/technical_master_score.yaml.
    Returns dict with: category_weights, rolling_window, categories, weight_mode, BULL_WEIGHTS, BEAR_WEIGHTS, news_weight.
    """
    path = config_path or DEFAULT_MASTER_SCORE_CONFIG_PATH
    _defensive = {"trend": 0.20, "momentum": 0.10, "volume": 0.20, "volatility": 0.50}
    _sideways = {"trend": 0.25, "momentum": 0.25, "volume": 0.25, "volatility": 0.25}
    if not path.exists():
        return {
            "category_weights": _DEFAULT_WEIGHTS.copy(),
            "rolling_window": 252,
            "categories": _DEFAULT_CATEGORIES.copy(),
            "weight_mode": "fixed",
            "BULL_WEIGHTS": _DEFAULT_WEIGHTS.copy(),
            "DEFENSIVE_WEIGHTS": _defensive.copy(),
            "BEAR_WEIGHTS": _defensive.copy(),
            "SIDEWAYS_WEIGHTS": _sideways.copy(),
            "news_weight": 0.0,
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) if yaml else {}
        def_weights = data.get("DEFENSIVE_WEIGHTS", data.get("BEAR_WEIGHTS", _defensive))
        return {
            "category_weights": data.get("category_weights", _DEFAULT_WEIGHTS.copy()),
            "rolling_window": int(data.get("rolling_window", 252)),
            "categories": data.get("categories", _DEFAULT_CATEGORIES.copy()),
            "weight_mode": data.get("weight_mode", "fixed"),
            "BULL_WEIGHTS": data.get("BULL_WEIGHTS", _DEFAULT_WEIGHTS.copy()),
            "DEFENSIVE_WEIGHTS": def_weights.copy() if isinstance(def_weights, dict) else _defensive.copy(),
            "BEAR_WEIGHTS": data.get("BEAR_WEIGHTS", _defensive).copy(),
            "SIDEWAYS_WEIGHTS": data.get("SIDEWAYS_WEIGHTS", _sideways).copy(),
            "news_weight": float(data.get("news_weight", 0.0)),
        }
    except Exception as e:
        logger.warning("Could not load technical_master_score.yaml: %s; using defaults.", e)
        return {
            "category_weights": _DEFAULT_WEIGHTS.copy(),
            "rolling_window": 252,
            "categories": _DEFAULT_CATEGORIES.copy(),
            "weight_mode": "fixed",
            "BULL_WEIGHTS": _DEFAULT_WEIGHTS.copy(),
            "DEFENSIVE_WEIGHTS": _defensive.copy(),
            "BEAR_WEIGHTS": _defensive.copy(),
            "SIDEWAYS_WEIGHTS": _sideways.copy(),
            "news_weight": 0.0,
        }


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ingest a standard OHLCV DataFrame; return OHLCV + all indicators + normalized columns.

    Uses pandas_ta for: Trend (MACD, ADX, PSAR, Aroon), Volatility (BB, ATR, Keltner),
    Momentum (Stochastic, CCI, Williams %R, ROC, RSI(14), momentum 5d/20d), Volume (OBV, CMF, VWAP, volume ratio),
    Moving Averages (EMA, SMA golden cross). All indicator columns are then normalized (0-1)
    for combination into a Master Score. NaN from look-back periods are filled with 0.5 (neutral).

    Args:
        df: DataFrame with columns open, high, low, close, volume (index = datetime).

    Returns:
        DataFrame with original OHLCV plus raw indicator columns and *_norm columns.
    """
    df = _ensure_ohlcv(df)
    idx = df.index
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

    out = df[OHLCV_COLS].copy()

    # ---- Trend ---- (P0: RSI, ADX, MACD active; others commented)
    try:
        macd = ta.macd(c, fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            for col in macd.columns:
                out[f"macd_{col}"] = _safe_series(macd[col], idx)
    except Exception as e:
        logger.debug("MACD: %s", e)
    try:
        adx = ta.adx(h, l, c, length=14)
        if adx is not None:
            if isinstance(adx, pd.DataFrame):
                for col in adx.columns:
                    out[f"adx_{col}"] = _safe_series(adx[col], idx)
            else:
                out["adx"] = _safe_series(adx, idx)
    except Exception as e:
        logger.debug("ADX: %s", e)
    # PSAR disabled for deterministic backtest (P0 stabilization)
    # try:
    #     psar = ta.psar(h, l, c)
    #     if psar is not None and not psar.empty:
    #         for col in psar.columns:
    #             out[f"psar_{col}"] = _safe_series(psar[col], idx)
    # except Exception as e:
    #     logger.debug("PSAR: %s", e)
    # try:
    #     aroon = ta.aroon(h, l, length=14)
    #     if aroon is not None and not aroon.empty:
    #         for col in aroon.columns:
    #             out[f"aroon_{col}"] = _safe_series(aroon[col], idx)
    # except Exception as e:
    #     logger.debug("Aroon: %s", e)

    # ---- Volatility ---- (P0: commented)
    # try:
    #     bb = ta.bbands(c, length=20, std=2.0)
    #     if bb is not None and not bb.empty:
    #         for col in bb.columns:
    #             out[f"bb_{col}"] = _safe_series(bb[col], idx)
    #         bu, bl = out.get("bb_BBU_20_2.0", pd.Series(0.0, index=idx)), out.get("bb_BBL_20_2.0", pd.Series(0.0, index=idx))
    #         out["bb_position"] = ((c - bl) / (bu - bl + 1e-8)).clip(0, 1).fillna(0.5)
    # except Exception as e:
    #     logger.debug("Bollinger: %s", e)
    # try:
    #     atr = ta.atr(h, l, c, length=14)
    #     if atr is not None:
    #         out["atr"] = _safe_series(atr, idx)
    # except Exception as e:
    #     logger.debug("ATR: %s", e)
    # try:
    #     kc = ta.kc(h, l, c, length=20)
    #     if kc is not None and not kc.empty:
    #         for col in kc.columns:
    #             out[f"kc_{col}"] = _safe_series(kc[col], idx)
    # except Exception as e:
    #     logger.debug("Keltner: %s", e)

    # ---- Momentum ---- (P0: only RSI active)
    # try:
    #     stoch = ta.stoch(h, l, c, k=14, d=3)
    #     if stoch is not None and not stoch.empty:
    #         for col in stoch.columns:
    #             out[f"stoch_{col}"] = _safe_series(stoch[col], idx)
    # except Exception as e:
    #     logger.debug("Stochastic: %s", e)
    # try:
    #     cci = ta.cci(h, l, c, length=20)
    #     if cci is not None:
    #         out["cci"] = _safe_series(cci, idx)
    # except Exception as e:
    #     logger.debug("CCI: %s", e)
    # try:
    #     willr = ta.willr(h, l, c, length=14)
    #     if willr is not None:
    #         out["willr"] = _safe_series(willr, idx)
    # except Exception as e:
    #     logger.debug("Williams %%R: %s", e)
    # try:
    #     roc = ta.roc(c, length=10)
    #     if roc is not None:
    #         out["roc"] = _safe_series(roc, idx)
    # except Exception as e:
    #     logger.debug("ROC: %s", e)
    try:
        rsi = ta.rsi(c, length=14)
        if rsi is not None:
            out["rsi"] = _safe_series(rsi, idx)
    except Exception as e:
        logger.debug("RSI: %s", e)
    # # Momentum 5d/20d (P0: commented)
    # try:
    #     mom5 = ta.roc(c, length=5)
    #     mom20 = ta.roc(c, length=20)
    #     if mom5 is not None:
    #         out["momentum_5d"] = _safe_series(mom5, idx)
    #     if mom20 is not None:
    #         out["momentum_20d"] = _safe_series(mom20, idx)
    # except Exception as e:
    #     logger.debug("Momentum ROC: %s", e)

    # ---- Volume ---- (P0: commented)
    # try:
    #     obv = ta.obv(c, v)
    #     if obv is not None:
    #         out["obv"] = _safe_series(obv, idx)
    # except Exception as e:
    #     logger.debug("OBV: %s", e)
    # try:
    #     cmf = ta.cmf(h, l, c, v, length=20)
    #     if cmf is not None:
    #         out["cmf"] = _safe_series(cmf, idx)
    # except Exception as e:
    #     logger.debug("CMF: %s", e)
    # try:
    #     vwap_ = ta.vwap(h, l, c, v)
    #     if vwap_ is not None:
    #         out["vwap"] = _safe_series(vwap_, idx)
    #     else:
    #         typical = (h + l + c) / 3.0
    #         out["vwap"] = (typical * v).cumsum() / (v.cumsum().replace(0, np.nan)).bfill().fillna(c)
    # except Exception as e:
    #     typical = (h + l + c) / 3.0
    #     out["vwap"] = (typical * v).cumsum() / (v.cumsum().replace(0, np.nan)).bfill().fillna(c)
    # try:
    #     vol_ma = v.rolling(30, min_periods=1).mean()
    #     out["volume_ratio"] = (v / (vol_ma + 1e-8)).fillna(1.0)
    # except Exception as e:
    #     logger.debug("Volume ratio: %s", e)
    #     out["volume_ratio"] = 1.0

    # ---- Moving Averages ---- (P0: commented)
    # for period in [8, 12, 26, 50]:
    #     try:
    #         ema = ta.ema(c, length=period)
    #         if ema is not None:
    #             out[f"ema_{period}"] = _safe_series(ema, idx)
    #     except Exception as e:
    #         logger.debug("EMA %s: %s", period, e)
    # try:
    #     sma50 = ta.sma(c, length=50)
    #     sma200 = ta.sma(c, length=200)
    #     if sma50 is not None and sma200 is not None:
    #         out["sma50"] = _safe_series(sma50, idx)
    #         out["sma200"] = _safe_series(sma200, idx)
    #         out["sma_golden_cross"] = (sma50.reindex(idx).fillna(0) > sma200.reindex(idx).fillna(0)).astype(float)
    # except Exception as e:
    #     logger.debug("SMA golden cross: %s", e)

    # ---- Normalize for Master Score ----
    # Config: rolling window for unbounded indicators (prevents look-ahead bias)
    _config = load_master_score_config()
    _rolling_window = _config.get("rolling_window", 252)

    # Static scaling for bounded indicators (P0: only RSI active)
    if "rsi" in out.columns:
        out["rsi_norm"] = (out["rsi"].clip(0, 100).fillna(50) / 100.0)
    # if "willr" in out.columns:
    #     out["willr_norm"] = (out["willr"].clip(-100, 0).fillna(-50) + 100.0) / 100.0
    # for col in ["stoch_STOCHk_14_3_3", "stoch_STOCHd_14_3_3"]:
    #     if col in out.columns:
    #         out[f"{col}_norm"] = (out[col].clip(0, 100).fillna(50) / 100.0)
    # for c in list(out.columns):
    #     if c.startswith("stoch_") and not c.endswith("_norm") and f"{c}_norm" not in out.columns:
    #         out[f"{c}_norm"] = (out[c].clip(0, 100).fillna(50) / 100.0)

    # Rolling min-max for unbounded (P0: commented; only RSI norm above)
    # _unbounded = [
    #     "atr", "cci", "roc", "momentum_5d", "momentum_20d",
    #     "cmf", "volume_ratio", "bb_position", "obv",
    # ]
    # for col in _unbounded:
    #     if col in out.columns and f"{col}_norm" not in out.columns:
    #         s = out[col].replace([np.inf, -np.inf], np.nan)
    #         out[f"{col}_norm"] = _rolling_minmax(s, window=_rolling_window)
    adx_cols = [c for c in out.columns if c.startswith("adx_") and not c.endswith("_norm")]
    if adx_cols and "adx_norm" not in out.columns:
        s = out[adx_cols[0]].replace([np.inf, -np.inf], np.nan)
        out["adx_norm"] = _rolling_minmax(s, window=_rolling_window)
    macd_cols = [c for c in out.columns if c.startswith("macd_") and not c.endswith("_norm")]
    if macd_cols and "macd_norm" not in out.columns:
        line_col = next((c for c in macd_cols if "MACD_" in c or "macd_" in c), macd_cols[0])
        s = out[line_col].replace([np.inf, -np.inf], np.nan)
        out["macd_norm"] = _rolling_minmax(s, window=_rolling_window)

    # Fill any remaining NaN in _norm columns
    for c in [x for x in out.columns if x.endswith("_norm")]:
        out[c] = out[c].fillna(0.5)

    return out


# Legacy flat weights (only used if config categories are missing); prefer config/technical_master_score.yaml
MASTER_SCORE_WEIGHTS: dict[str, float] = {
    "rsi_norm": 0.12,
    "momentum_5d_norm": 0.10,
    "momentum_20d_norm": 0.10,
    "volume_ratio_norm": 0.08,
    "bb_position_norm": 0.06,
    "atr_norm": 0.04,
    "cmf_norm": 0.10,
    "willr_norm": 0.08,
    "roc_norm": 0.06,
    "adx_norm": 0.06,
    "stoch_STOCHk_14_3_3_norm": 0.06,
    "stoch_STOCHd_14_3_3_norm": 0.04,
    "cci_norm": 0.05,
    "obv_norm": 0.05,
}


def compute_signal_strength(
    row: pd.Series,
    config_path: Optional[Path] = None,
    weight_mode: Optional[str] = None,
    spy_above_sma200: Optional[bool] = None,
    regime_state: Optional[str] = None,
    category_weights_override: Optional[dict[str, float]] = None,
    news_composite: Optional[float] = None,
    news_weight_override: Optional[float] = None,
) -> tuple[float, dict[str, Any]]:
    """
    Compute Category-Weighted Master Score from a single row (e.g. last row of calculate_all_indicators output).
    Weights and indicator→category mapping are read from config/technical_master_score.yaml.

    Dynamic weighting:
    - If category_weights_override is provided, use it (e.g. from rolling/ml).
    - Else if weight_mode == "regime" and regime_state is set: use BULL_WEIGHTS, DEFENSIVE_WEIGHTS, or SIDEWAYS_WEIGHTS.
    - Else if weight_mode == "regime" and spy_above_sma200 is not None: use BULL_WEIGHTS or BEAR_WEIGHTS (fallback).
    - Else use category_weights from config (fixed or default).

    News overlay: If news_composite is not None and config news_weight > 0:
    final_master = (1 - news_weight) * technical_master + news_weight * news_composite (e.g. 0.8/0.2).

    Returns:
        (master_score, result_dict) where result_dict contains:
        - category_sub_scores: { trend, momentum, volume, volatility }
        - breakdown: per-_norm value for inspection
    """
    config = load_master_score_config(config_path)
    categories = config.get("categories", _DEFAULT_CATEGORIES)

    if category_weights_override is not None:
        c_weights = dict(category_weights_override)
    elif (weight_mode or config.get("weight_mode", "fixed")) == "regime":
        if regime_state == "BULL":
            c_weights = config.get("BULL_WEIGHTS", _DEFAULT_WEIGHTS).copy()
        elif regime_state == "BEAR":
            c_weights = config.get("DEFENSIVE_WEIGHTS", config.get("BEAR_WEIGHTS", {"trend": 0.20, "momentum": 0.10, "volume": 0.20, "volatility": 0.50})).copy()
        elif regime_state == "SIDEWAYS":
            c_weights = config.get("SIDEWAYS_WEIGHTS", {c: 0.25 for c in ("trend", "momentum", "volume", "volatility")}).copy()
        elif spy_above_sma200 is not None:
            c_weights = config.get("BULL_WEIGHTS", _DEFAULT_WEIGHTS).copy() if spy_above_sma200 else config.get("DEFENSIVE_WEIGHTS", config.get("BEAR_WEIGHTS", {"trend": 0.20, "momentum": 0.10, "volume": 0.20, "volatility": 0.50})).copy()
        else:
            c_weights = config.get("category_weights", _DEFAULT_WEIGHTS).copy()
    else:
        c_weights = config.get("category_weights", _DEFAULT_WEIGHTS).copy()

    def _get_val(col: str) -> float:
        if col not in row.index:
            return 0.5
        v = row[col]
        return 0.5 if pd.isna(v) else float(v)

    category_sub_scores: dict[str, float] = {}
    for cat_name, cols in categories.items():
        if not cols:
            category_sub_scores[cat_name] = 0.5
            continue
        vals = [_get_val(c) for c in cols]
        category_sub_scores[cat_name] = round(float(np.mean(vals)), 4)

    w_sum = sum(c_weights.get(c, 0) for c in category_sub_scores) or 1.0
    master_score = sum(
        (c_weights.get(cat, 0) / w_sum) * category_sub_scores[cat]
        for cat in category_sub_scores
    )
    master_score = round(float(master_score), 4)

    # News Alpha overlay: blend with news_composite when enabled (override from AdaptiveSelector when provided)
    news_weight = float(news_weight_override) if news_weight_override is not None else (config.get("news_weight", 0.0) or 0.0)
    if news_weight > 0 and news_composite is not None:
        nc = float(news_composite)
        nc = max(0.0, min(1.0, nc))
        master_score = round((1.0 - news_weight) * master_score + news_weight * nc, 4)

    breakdown: dict[str, float] = {}
    for cat_cols in categories.values():
        for col in cat_cols:
            if col in row.index and not pd.isna(row[col]):
                breakdown[col] = round(float(row[col]), 4)

    result = {
        "category_sub_scores": category_sub_scores,
        "breakdown": breakdown,
    }
    return master_score, result
