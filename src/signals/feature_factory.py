"""
Feature factory: registry of candidate features and Selection Tournament.

Research layer only. Does not modify technical_library or signal_engine.
Computes all candidate features (pandas_ta + news via train_pipeline),
runs IC + orthogonality screening, writes winners to model_config.yaml feature_names.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta
except ImportError:
    ta = None  # type: ignore[assignment]

from src.signals.technical_library import (
    _rolling_minmax,
    calculate_all_indicators,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SECTION 1 — FEATURE REGISTRY
# ---------------------------------------------------------------------------
# type: "technical" | "news"
# column: name in calculate_all_indicators() output, or None if factory computes
# compute_fn: name of _compute_{feature} in this module (technical only)
# active: True = currently in production model_config.yaml
# protected: True = always included in tournament selection
FEATURE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "rsi_norm": {"type": "technical", "column": "rsi_norm", "compute_fn": None, "active": True, "protected": True},
    "sentiment_velocity": {"type": "news", "column": None, "compute_fn": None, "active": True, "protected": True},
    "news_sentiment": {"type": "news", "column": None, "compute_fn": None, "active": True, "protected": True},
    "momentum_avg": {"type": "technical", "column": None, "compute_fn": "_compute_momentum_avg", "active": False, "protected": False},
    "volume_ratio_norm": {"type": "technical", "column": None, "compute_fn": "_compute_volume_ratio_norm", "active": False, "protected": False},
    "adx_norm": {"type": "technical", "column": "adx_norm", "compute_fn": None, "active": False, "protected": False},
    "macd_norm": {"type": "technical", "column": "macd_norm", "compute_fn": None, "active": False, "protected": False},
    "willr_norm": {"type": "technical", "column": None, "compute_fn": "_compute_willr_norm", "active": False, "protected": False},
    "stoch_k_norm": {"type": "technical", "column": None, "compute_fn": "_compute_stoch_k_norm", "active": False, "protected": False},
    "stoch_d_norm": {"type": "technical", "column": None, "compute_fn": "_compute_stoch_d_norm", "active": False, "protected": False},
    "cci_norm": {"type": "technical", "column": None, "compute_fn": "_compute_cci_norm", "active": False, "protected": False},
    "roc_norm": {"type": "technical", "column": None, "compute_fn": "_compute_roc_norm", "active": False, "protected": False},
    "momentum_5d_norm": {"type": "technical", "column": None, "compute_fn": "_compute_momentum_5d_norm", "active": False, "protected": False},
    "momentum_20d_norm": {"type": "technical", "column": None, "compute_fn": "_compute_momentum_20d_norm", "active": False, "protected": False},
    "bb_position_norm": {"type": "technical", "column": None, "compute_fn": "_compute_bb_position_norm", "active": False, "protected": False},
    "atr_norm": {"type": "technical", "column": None, "compute_fn": "_compute_atr_norm", "active": False, "protected": False},
    "obv_norm": {"type": "technical", "column": None, "compute_fn": "_compute_obv_norm", "active": False, "protected": False},
    "cmf_norm": {"type": "technical", "column": None, "compute_fn": "_compute_cmf_norm", "active": False, "protected": False},
    "news_supply": {"type": "news", "column": None, "compute_fn": None, "active": False, "protected": False},
    "news_spike": {"type": "news", "column": None, "compute_fn": None, "active": False, "protected": False},
}

# Full 7-feature list used when calling pipeline.extract_features_for_date to get news cols
_FULL_FEATURE_ORDER = [
    "momentum_avg", "volume_ratio_norm", "rsi_norm",
    "news_supply", "news_sentiment", "sentiment_velocity", "news_spike",
]

_MIN_REQUIRED_DAYS = 60


def _get_news_features_for_date(ticker: str, date: pd.Timestamp, news_signals: Dict) -> Dict[str, float]:
    """Fast dict lookup for news features (no pandas_ta / calculate_all_indicators). Same logic as train_pipeline."""
    news_signals = news_signals or {}
    ticker_news = news_signals.get(ticker, {})
    date_str = date.strftime("%Y-%m-%d") if isinstance(date, pd.Timestamp) else str(date)
    news = ticker_news.get(date_str) or ticker_news.get(date) or {}
    if news is None:
        news = {}
    news_supply = float(news.get("supply_chain_score", news.get("supply_chain", 0.5)))
    news_sentiment = float(news.get("sentiment_score", news.get("sentiment", 0.5)))
    past_sentiment = None
    for offset in [5, 6, 7, 4, 3]:
        past_date = date - pd.Timedelta(days=offset)
        past_str = past_date.strftime("%Y-%m-%d")
        if past_str in ticker_news:
            past_news = ticker_news.get(past_str) or {}
            past_sentiment = float(past_news.get("sentiment_score", past_news.get("sentiment", 0.5)))
            break
    sentiment_velocity = (news_sentiment - past_sentiment) if past_sentiment is not None else 0.0
    supply_values = []
    for d in range(1, 21):
        back_str = (date - pd.Timedelta(days=d)).strftime("%Y-%m-%d")
        if back_str not in ticker_news:
            continue
        back_news = ticker_news.get(back_str) or {}
        supply_values.append(float(back_news.get("supply_chain_score", back_news.get("supply_chain", 0.5))))
    if len(supply_values) >= 5:
        mean_supply = float(np.mean(supply_values))
        news_spike = (news_supply / mean_supply) if mean_supply > 0 else 1.0
    else:
        news_spike = 1.0
    return {
        "news_supply": news_supply,
        "news_sentiment": news_sentiment,
        "sentiment_velocity": sentiment_velocity,
        "news_spike": news_spike,
    }


# ---------------------------------------------------------------------------
# SECTION 2 — INDICATOR COMPUTE FUNCTIONS (pandas_ta)
# ---------------------------------------------------------------------------
def _ensure_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    from src.data.csv_provider import ensure_ohlcv
    return ensure_ohlcv(df.copy())


def _compute_momentum_avg(df: pd.DataFrame) -> pd.Series:
    if ta is None:
        return pd.Series(0.5, index=df.index)
    c = df["close"]
    m5 = ta.roc(c, length=5)
    m20 = ta.roc(c, length=20)
    if m5 is None:
        m5 = pd.Series(0.0, index=df.index)
    if m20 is None:
        m20 = pd.Series(0.0, index=df.index)
    avg = (m5.reindex(df.index).fillna(0) + m20.reindex(df.index).fillna(0)) / 2.0
    return _rolling_minmax(avg, 252)


def _compute_volume_ratio_norm(df: pd.DataFrame) -> pd.Series:
    v = df["volume"]
    vol_ma = v.rolling(30, min_periods=1).mean()
    ratio = (v / (vol_ma + 1e-8)).fillna(1.0)
    return _rolling_minmax(ratio, 252)


def _compute_willr_norm(df: pd.DataFrame) -> pd.Series:
    if ta is None:
        return pd.Series(0.5, index=df.index)
    w = ta.willr(df["high"], df["low"], df["close"], length=14)
    if w is None:
        return pd.Series(0.5, index=df.index)
    w = w.reindex(df.index).fillna(-50)
    return (w.clip(-100, 0) + 100.0) / 100.0


def _compute_stoch_k_norm(df: pd.DataFrame) -> pd.Series:
    if ta is None:
        return pd.Series(0.5, index=df.index)
    st = ta.stoch(df["high"], df["low"], df["close"], k=14, d=3)
    if st is None or st.empty:
        return pd.Series(0.5, index=df.index)
    col = [c for c in st.columns if "STOCHk" in c or "stochk" in c.lower()][:1]
    s = st[col[0]].reindex(df.index).fillna(50) if col else pd.Series(50.0, index=df.index)
    return (s.clip(0, 100) / 100.0)


def _compute_stoch_d_norm(df: pd.DataFrame) -> pd.Series:
    if ta is None:
        return pd.Series(0.5, index=df.index)
    st = ta.stoch(df["high"], df["low"], df["close"], k=14, d=3)
    if st is None or st.empty:
        return pd.Series(0.5, index=df.index)
    col = [c for c in st.columns if "STOCHd" in c or "stochd" in c.lower()][:1]
    s = st[col[0]].reindex(df.index).fillna(50) if col else pd.Series(50.0, index=df.index)
    return (s.clip(0, 100) / 100.0)


def _compute_cci_norm(df: pd.DataFrame) -> pd.Series:
    if ta is None:
        return pd.Series(0.5, index=df.index)
    cci = ta.cci(df["high"], df["low"], df["close"], length=20)
    if cci is None:
        return pd.Series(0.5, index=df.index)
    return _rolling_minmax(cci.reindex(df.index).fillna(0), 252)


def _compute_roc_norm(df: pd.DataFrame) -> pd.Series:
    if ta is None:
        return pd.Series(0.5, index=df.index)
    roc = ta.roc(df["close"], length=10)
    if roc is None:
        return pd.Series(0.5, index=df.index)
    return _rolling_minmax(roc.reindex(df.index).fillna(0), 252)


def _compute_momentum_5d_norm(df: pd.DataFrame) -> pd.Series:
    if ta is None:
        return pd.Series(0.5, index=df.index)
    m = ta.roc(df["close"], length=5)
    if m is None:
        return pd.Series(0.5, index=df.index)
    return _rolling_minmax(m.reindex(df.index).fillna(0), 252)


def _compute_momentum_20d_norm(df: pd.DataFrame) -> pd.Series:
    if ta is None:
        return pd.Series(0.5, index=df.index)
    m = ta.roc(df["close"], length=20)
    if m is None:
        return pd.Series(0.5, index=df.index)
    return _rolling_minmax(m.reindex(df.index).fillna(0), 252)


def _compute_bb_position_norm(df: pd.DataFrame) -> pd.Series:
    if ta is None:
        return pd.Series(0.5, index=df.index)
    bb = ta.bbands(df["close"], length=20, std=2.0)
    if bb is None or bb.empty:
        return pd.Series(0.5, index=df.index)
    cols = bb.columns.tolist()
    upper = bb[cols[0]].reindex(df.index) if cols else pd.Series(np.nan, index=df.index)
    lower = bb[cols[2]].reindex(df.index) if len(cols) > 2 else pd.Series(np.nan, index=df.index)
    c = df["close"]
    pos = (c - lower) / (upper - lower + 1e-8)
    return pos.clip(0.0, 1.0).fillna(0.5)


def _compute_atr_norm(df: pd.DataFrame) -> pd.Series:
    if ta is None:
        return pd.Series(0.5, index=df.index)
    atr = ta.atr(df["high"], df["low"], df["close"], length=14)
    if atr is None:
        return pd.Series(0.5, index=df.index)
    return _rolling_minmax(atr.reindex(df.index).fillna(0), 252)


def _compute_obv_norm(df: pd.DataFrame) -> pd.Series:
    if ta is None:
        return pd.Series(0.5, index=df.index)
    obv = ta.obv(df["close"], df["volume"])
    if obv is None:
        return pd.Series(0.5, index=df.index)
    return _rolling_minmax(obv.reindex(df.index).fillna(0), 252)


def _compute_cmf_norm(df: pd.DataFrame) -> pd.Series:
    if ta is None:
        return pd.Series(0.5, index=df.index)
    cmf = ta.cmf(df["high"], df["low"], df["close"], df["volume"], length=20)
    if cmf is None:
        return pd.Series(0.5, index=df.index)
    return _rolling_minmax(cmf.reindex(df.index).fillna(0), 252)


# ---------------------------------------------------------------------------
# SECTION 3 — FeatureSelector
# ---------------------------------------------------------------------------
class FeatureSelector:
    def __init__(
        self,
        ic_threshold: float = 0.005,
        corr_threshold: float = 0.70,
        n_keep: int = 5,
    ):
        self.ic_threshold = ic_threshold
        self.corr_threshold = corr_threshold
        self.n_keep = n_keep

    def build_feature_matrix(
        self,
        prices_dict: Dict[str, pd.DataFrame],
        news_signals: Dict,
        start: str,
        end: str,
        feature_columns: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Build DataFrame: rows = (ticker, date), columns = feature names + forward_ret.
        O(tickers x indicators): indicators computed once per ticker; date loop is row lookup only.
        If feature_columns is provided, output only those columns + forward_ret; else all FEATURE_REGISTRY + forward_ret.
        """
        from src.models.train_pipeline import ModelTrainingPipeline

        start_dt = pd.to_datetime(start)
        end_dt = pd.to_datetime(end)
        news_signals = news_signals or {}
        config_path = Path(__file__).resolve().parent.parent.parent / "config" / "model_config.yaml"
        pipeline = ModelTrainingPipeline(str(config_path))
        pipeline.feature_names = _FULL_FEATURE_ORDER.copy()

        rows = []
        for ticker in prices_dict:
            full_df = prices_dict[ticker]
            if full_df.empty or "close" not in full_df.columns:
                continue
            full_df = _ensure_ohlcv(full_df)
            if not all(c in full_df.columns for c in ["open", "high", "low", "close", "volume"]):
                continue

            # STEP A — compute indicators ONCE on full price history
            try:
                ind_df = calculate_all_indicators(full_df)
            except Exception:
                continue
            if ind_df is None or ind_df.empty:
                continue
            for name, meta in FEATURE_REGISTRY.items():
                if meta["type"] != "technical":
                    continue
                if meta["column"] and meta["column"] in ind_df.columns:
                    continue
                if meta["compute_fn"]:
                    fn = globals().get(meta["compute_fn"])
                    if fn is not None:
                        try:
                            s = fn(full_df)
                            ind_df[name] = s.reindex(ind_df.index).fillna(0.5)
                        except Exception:
                            ind_df[name] = 0.5
                    else:
                        ind_df[name] = 0.5

            # STEP B — for each weekly date, extract via row lookup
            weekly_dates = pd.date_range(start_dt, end_dt, freq="W-MON")
            for date in weekly_dates:
                available = ind_df[ind_df.index <= date]
                if len(available) < _MIN_REQUIRED_DAYS:
                    continue
                row = available.iloc[-1]
                feat = {}
                for name, meta in FEATURE_REGISTRY.items():
                    if meta["type"] == "technical":
                        col = name if name in row.index else (meta.get("column") if meta.get("column") else None)
                        val = row.get(col, row.get(name, 0.5))
                        feat[name] = float(val) if pd.notna(val) else 0.5
                    else:
                        feat[name] = 0.5
                news_feat = _get_news_features_for_date(ticker, date, news_signals)
                for k, v in news_feat.items():
                    feat[k] = v
                try:
                    fwd = pipeline._calculate_forward_return(ticker, date, prices_dict, horizon_days=7)
                except Exception:
                    fwd = None
                if fwd is None or (isinstance(fwd, float) and (np.isnan(fwd) or np.isinf(fwd))):
                    continue
                feat["forward_ret"] = float(fwd)
                rows.append((ticker, date, feat))
        if not rows:
            return pd.DataFrame()
        output_cols = list(feature_columns) if feature_columns is not None else list(FEATURE_REGISTRY)
        if "forward_ret" not in output_cols:
            output_cols = output_cols + ["forward_ret"]
        records = []
        for t, d, f in rows:
            rec = {"ticker": t, "date": d}
            for k in output_cols:
                if k in f:
                    rec[k] = f[k]
            records.append(rec)
        out = pd.DataFrame(records).set_index(["ticker", "date"])
        out = out.dropna(subset=["forward_ret"])
        return out

    def tournament(
        self,
        prices_dict: Dict[str, pd.DataFrame],
        news_signals: Dict,
        train_start: str,
        train_end: str,
        config_path: Optional[Path] = None,
    ) -> List[str]:
        """IC screen -> orthogonality screen -> rank top n_keep -> write JSON + update YAML. Returns selected list."""
        from scipy.stats import spearmanr

        config_path = config_path or Path(__file__).resolve().parent.parent.parent / "config" / "model_config.yaml"
        active_names = [n for n, m in FEATURE_REGISTRY.items() if m.get("active")]
        all_candidates = list(FEATURE_REGISTRY.keys())

        # Step 1 — Build matrix
        mat = self.build_feature_matrix(prices_dict, news_signals, train_start, train_end)
        if mat.empty or len(mat) < 200:
            logger.warning("Feature matrix has %d rows; need >= 200. Returning current active.", len(mat))
            return active_names

        n_candidates = len(all_candidates)
        feature_cols = [c for c in mat.columns if c != "forward_ret"]
        y = mat["forward_ret"].values

        # Step 2 — IC screen (drop NaN IC and low |IC|)
        ic_vals = {}
        dropped_nan_ic = []
        dropped_low_ic = []
        for col in feature_cols:
            x = mat[col].values
            valid = np.isfinite(x) & np.isfinite(y)
            if np.sum(valid) < 20:
                continue
            r, _ = spearmanr(x[valid], y[valid], nan_policy="omit")
            r = float(r) if not (r is None or (hasattr(r, "__len__") and len(r) == 0)) else float("nan")
            if math.isnan(r) or not np.isfinite(r):
                dropped_nan_ic.append(col)
                continue
            if abs(r) >= self.ic_threshold:
                ic_vals[col] = r
            else:
                dropped_low_ic.append(col)
        if dropped_nan_ic:
            logger.info("IC screen dropped (NaN/constant): %s", dropped_nan_ic)
        if dropped_low_ic:
            logger.info("IC screen dropped (|IC| < %s): %s", self.ic_threshold, dropped_low_ic)
        survivors = list(ic_vals.keys())

        # Step 3 — Orthogonality screen
        dropped_high_corr = []
        while True:
            sub = mat[survivors].copy()
            sub = sub.replace([np.inf, -np.inf], np.nan).fillna(sub.median())
            corr = sub.corr(method="pearson")
            to_drop = None
            for i, a in enumerate(survivors):
                for j, b in enumerate(survivors):
                    if i >= j:
                        continue
                    c = corr.loc[a, b] if a in corr.columns and b in corr.index else 0.0
                    if abs(c) > self.corr_threshold:
                        if abs(ic_vals.get(a, 0)) < abs(ic_vals.get(b, 0)):
                            to_drop = a
                        elif abs(ic_vals.get(a, 0)) > abs(ic_vals.get(b, 0)):
                            to_drop = b
                        else:
                            to_drop = max(a, b)
                        break
                if to_drop is not None:
                    break
            if to_drop is None:
                break
            survivors.remove(to_drop)
            dropped_high_corr.append(to_drop)
        if dropped_high_corr:
            logger.info("Orthogonality screen dropped: %s", dropped_high_corr)

        # Step 4 — Rank and select (protected always in; fill remaining with top candidates by |IC|)
        protected = [f for f in FEATURE_REGISTRY if FEATURE_REGISTRY[f].get("protected")]
        sorted_survivors = sorted(survivors, key=lambda x: abs(ic_vals.get(x, 0)), reverse=True)
        candidates = [f for f in sorted_survivors if f not in protected]
        n_extra = max(0, self.n_keep - len(protected))
        selected = protected + candidates[:n_extra]

        # Step 5 — Write results
        from datetime import datetime, timezone
        run_date = datetime.now(timezone.utc).isoformat()
        yy_mm = datetime.now().strftime("%Y_%m")
        out_dir = Path(__file__).resolve().parent.parent.parent / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "run_date": run_date,
            "train_start": train_start,
            "train_end": train_end,
            "n_candidates": n_candidates,
            "ic_survivors": ic_vals,
            "protected": protected,
            "selected": selected,
            "dropped_low_ic": dropped_low_ic,
            "dropped_nan_ic": dropped_nan_ic,
            "dropped_high_corr": dropped_high_corr,
        }
        json_path = out_dir / f"feature_tournament_{yy_mm}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        logger.info("Wrote %s", json_path)

        # Update model_config.yaml feature_names (ruamel preserves comments, else PyYAML)
        try:
            try:
                from ruamel.yaml import YAML
                yaml_loader = YAML()
                yaml_loader.preserve_quotes = True
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml_loader.load(f)
                if cfg is None:
                    cfg = {}
                if "features" not in cfg:
                    cfg["features"] = {}
                cfg["features"]["feature_names"] = selected
                with open(config_path, "w", encoding="utf-8") as f:
                    yaml_loader.dump(cfg, f)
            except ImportError:
                import yaml as yaml_mod
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml_mod.safe_load(f)
                if "features" not in cfg:
                    cfg["features"] = {}
                cfg["features"]["feature_names"] = selected
                with open(config_path, "w", encoding="utf-8") as f:
                    yaml_mod.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        except Exception as e:
            logger.warning("Could not update model_config.yaml: %s", e)

        return selected
