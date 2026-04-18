"""
Three-layer signal-to-position engine.

Layer 3: technical/sentiment cross-sectional ranking.
Layer 2: fundamental-cycle cross-sectional ranking (quarterly, forward-filled).
Layer 1: macro-regime, quality filter, and earnings-event caps (post-signal only).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.core.portfolio_engine import _load_tes_multipliers

logger = logging.getLogger(__name__)

L3_SIGNALS = [
    "rsi_norm",
    "macd_norm",
    "cmf_norm",
    "momentum_avg",
    "volume_ratio_norm",
    "news_sentiment",
    "news_supply",
    "sentiment_velocity",
    "news_spike",
]

L2_BASE_SIGNALS = [
    "earnings_revision_30d",
    "gross_margin_pct",
    "inventory_days",
    "inventory_days_accel",
    "gross_margin_delta",
    "last_rev_surprise_pct",
    "fcf_yield",
    "roic",
    "fcf_conversion",
    "net_capex_sales",
    "net_debt_ebitda",
]

L1_REQUIRED_SIGNALS = [
    "fcf_ttm",
    "debt_to_equity",
    "last_eps_surprise_pct",
    "last_earnings_date",
    "next_earnings_date",
]


def load_layered_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path is not None else Path(__file__).resolve().parents[2] / "config" / "layered_signal_config.yaml"
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise ValueError("layered signal config must be a mapping")
    return cfg


def _require_columns(df: pd.DataFrame, required: list[str]) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _cross_section_zscore(series: pd.Series, dates: pd.Series) -> pd.Series:
    mean = series.groupby(dates).transform("mean")
    std = series.groupby(dates).transform("std")
    z = (series - mean) / std
    return z.mask(std.eq(0) & series.notna(), 0.0)


def _cross_section_rank01(series: pd.Series, dates: pd.Series) -> pd.Series:
    r = series.groupby(dates).rank(method="average", ascending=True)
    n = series.groupby(dates).transform("count")
    denom = (n - 1).replace(0, np.nan)
    return ((r - 1) / denom).fillna(0.0)


def _load_tes_series(tickers: pd.Series) -> pd.Series:
    tes_map = _load_tes_multipliers({"tes_enabled": True, "tes_scores_path": "data/tes_scores.json"})
    if not tes_map:
        logger.warning("TES scores unavailable; tes_score set to NaN")
    out = tickers.astype(str).str.upper().map(tes_map).astype(float)
    if out.isna().all():
        logger.warning("TES score absent for all tickers; Layer 2 uses non-TES signals only")
    return out


def compute_layered_positions(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Three-layer signal-to-position engine.

    Layer 3: technical/sentiment cross-sectional ranking.
    Layer 2: fundamental-cycle cross-sectional ranking (quarterly, forward-filled).
    Layer 1: macro-regime, quality filter, and earnings-event caps (post-signal only).

    Args:
        df: Panel DataFrame. Required columns listed in docs and module constants.
            Fundamental columns may be NaN; engine handles sparsity via forward-fill
            and stale flags.
        config: dict loaded from config/layered_signal_config.yaml.

    Returns:
        DataFrame with all intermediate and output columns appended.
    """
    required = ["date", "ticker"] + L3_SIGNALS + L1_REQUIRED_SIGNALS
    _require_columns(df, required)

    w_cfg = (config or {}).get("layer_weights", {})
    fw = float(w_cfg.get("fundamental_cycle_weight", 0.6))
    tw = float(w_cfg.get("technical_sentiment_weight", 0.4))
    if abs((fw + tw) - 1.0) > 1e-9:
        raise ValueError("layer_weights must sum to 1.0")

    out = df.copy()
    # filing_date (optional): fundamentals audit metadata only; not in L2_BASE_SIGNALS / L1_REQUIRED_SIGNALS.
    for col in L2_BASE_SIGNALS:
        if col not in out.columns:
            out[col] = np.nan
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["last_earnings_date"] = pd.to_datetime(out["last_earnings_date"], errors="coerce")
    out["next_earnings_date"] = pd.to_datetime(out["next_earnings_date"], errors="coerce")

    # Layer 3: technical/sentiment cross-sectional z-scores and ranks.
    for sig in L3_SIGNALS:
        z_col = f"z_{sig}"
        r_col = f"rank_{sig}"
        out[z_col] = _cross_section_zscore(out[sig], out["date"])
        out[r_col] = _cross_section_rank01(out[z_col], out["date"])
    out["layer3_composite"] = out[[f"rank_{s}" for s in L3_SIGNALS]].mean(axis=1, skipna=True)

    # Layer 2 input prep: add TES score.
    out["tes_score"] = _load_tes_series(out["ticker"])
    out["inventory_days_neg"] = -1.0 * out["inventory_days"]
    out["inventory_days_accel_neg"] = -1.0 * out["inventory_days_accel"]
    out["net_debt_ebitda_neg"] = -1.0 * out["net_debt_ebitda"]

    # Forward-fill fundamentals by ticker with age cap.
    out = out.sort_values(["ticker", "date"]).reset_index(drop=True)
    ffill_days = int((config or {}).get("fundamental_ffill_days", 91))
    l2_signal_cols = [
        "earnings_revision_30d",
        "gross_margin_pct",
        "inventory_days_neg",
        "inventory_days_accel_neg",
        "gross_margin_delta",
        "last_rev_surprise_pct",
        "fcf_yield",
        "roic",
        "fcf_conversion",
        "net_capex_sales",
        "net_debt_ebitda_neg",
        "tes_score",
    ]
    stale_any = pd.Series(False, index=out.index)
    for col in l2_signal_cols:
        src_date_col = f"_{col}_src_date"
        out[src_date_col] = out["date"].where(out[col].notna())
        out[col] = out.groupby("ticker", sort=False)[col].ffill()
        out[src_date_col] = out.groupby("ticker", sort=False)[src_date_col].ffill()
        age_days = (out["date"] - out[src_date_col]).dt.days
        stale_col = out[col].notna() & age_days.gt(ffill_days)
        out.loc[stale_col, col] = np.nan
        stale_any = stale_any | stale_col
        out.drop(columns=[src_date_col], inplace=True)

    out["l2_stale"] = stale_any | out[l2_signal_cols].isna().all(axis=1)

    # Coverage check per date.
    per_date_total = out.groupby("date")["ticker"].transform("count")
    per_date_non_stale = (~out["l2_stale"]).groupby(out["date"]).transform("sum")
    min_cov = float((config or {}).get("min_layer2_coverage", 0.6))
    out["l2_coverage_flag"] = (per_date_non_stale / per_date_total) < min_cov

    # Layer 2 cross-sectional scoring (exclude stale rows).
    l2_rank_inputs = [
        "earnings_revision_30d",
        "gross_margin_pct",
        "inventory_days_neg",
        "inventory_days_accel_neg",
        "gross_margin_delta",
        "last_rev_surprise_pct",
        "fcf_yield",
        "roic",
        "fcf_conversion",
        "net_capex_sales",
        "net_debt_ebitda_neg",
        "tes_score",
    ]
    if out["tes_score"].isna().all():
        l2_rank_inputs = [
            "earnings_revision_30d",
            "gross_margin_pct",
            "inventory_days_neg",
            "inventory_days_accel_neg",
            "gross_margin_delta",
            "last_rev_surprise_pct",
            "fcf_yield",
            "roic",
            "fcf_conversion",
            "net_capex_sales",
            "net_debt_ebitda_neg",
        ]

    for col in l2_rank_inputs:
        safe_series = out[col].where(~out["l2_stale"])
        z_col = f"z_{col}"
        r_col = f"rank_{col}"
        out[z_col] = _cross_section_zscore(safe_series, out["date"])
        out[r_col] = _cross_section_rank01(out[z_col], out["date"])

    # Ensure requested columns exist even when TES is absent.
    if "z_tes_score" not in out.columns:
        out["z_tes_score"] = np.nan
    if "rank_tes_score" not in out.columns:
        out["rank_tes_score"] = np.nan

    l2_rank_cols = [f"rank_{c}" for c in l2_rank_inputs]
    out["layer2_composite"] = out[l2_rank_cols].mean(axis=1, skipna=True)
    out.loc[out["l2_stale"], "layer2_composite"] = np.nan

    # Cross-layer combination.
    out["L3_rank"] = _cross_section_rank01(out["layer3_composite"], out["date"])
    out["L2_rank"] = _cross_section_rank01(out["layer2_composite"], out["date"])

    out["layer3_pseudo_weight"] = out["L3_rank"] * 2.0 - 1.0
    out["layer2_pseudo_weight"] = out["L2_rank"] * 2.0 - 1.0

    out["layer3_pseudo_weight"] = out["layer3_pseudo_weight"] - out.groupby("date")["layer3_pseudo_weight"].transform("mean")
    out["layer2_pseudo_weight"] = out["layer2_pseudo_weight"] - out.groupby("date")["layer2_pseudo_weight"].transform("mean")

    l2_for_combo = out["layer2_pseudo_weight"].where(out["layer2_pseudo_weight"].notna(), out["layer3_pseudo_weight"])
    out["w_raw_combined"] = fw * l2_for_combo + tw * out["layer3_pseudo_weight"]
    out.loc[out["l2_coverage_flag"], "w_raw_combined"] = out.loc[out["l2_coverage_flag"], "layer3_pseudo_weight"]

    # Layer 1 multipliers.
    for col in ("fcf_yield", "roic", "fcf_conversion", "net_capex_sales", "net_debt_ebitda"):
        if col not in out.columns:
            out[col] = np.nan
    qf_cfg = (config or {}).get("quality_filter") or {}
    max_lev = float(qf_cfg.get("max_leverage_ratio", 3.0))
    fcf_yield_min = float(qf_cfg.get("fcf_yield_min", -999.0))
    net_debt_ebitda_max = float(qf_cfg.get("net_debt_ebitda_max", 8.0))
    roic_min = float(qf_cfg.get("roic_min", -999.0))
    quality_pass = (
        (out["fcf_ttm"].isna() | out["fcf_ttm"].gt(0))
        & (out["debt_to_equity"].isna() | out["debt_to_equity"].le(max_lev))
        & (out["fcf_yield"].isna() | out["fcf_yield"].ge(fcf_yield_min))
        & (out["net_debt_ebitda"].isna() | out["net_debt_ebitda"].le(net_debt_ebitda_max))
        & (out["roic"].isna() | out["roic"].ge(roic_min))
    )
    out["l1_quality_pass"] = quality_pass
    out["l1_quality_multiplier"] = np.where(quality_pass, 1.0, 0.0)

    ev_cfg = (config or {}).get("earnings_event", {})
    post_window = int(ev_cfg.get("post_earnings_window", 5))
    miss_threshold = float(ev_cfg.get("miss_threshold", 0.10))
    post_mult = float(ev_cfg.get("post_earnings_miss_multiplier", 0.7))
    days_since_earnings = (out["date"] - out["last_earnings_date"]).dt.days
    post_miss = (
        out["last_earnings_date"].notna()
        & out["last_eps_surprise_pct"].notna()
        & days_since_earnings.le(post_window)
        & out["last_eps_surprise_pct"].lt(-miss_threshold)
    )
    out["l1_post_earnings_multiplier"] = np.where(post_miss, post_mult, 1.0)

    pre_event_days = int(ev_cfg.get("pre_event_days", 2))
    earnings_size_down = float(ev_cfg.get("earnings_size_down", 0.5))
    pre_mult = 1.0 - earnings_size_down
    days_to_earnings = (out["next_earnings_date"] - out["date"]).dt.days
    pre_event = (
        out["next_earnings_date"].notna()
        & days_to_earnings.ge(0)
        & days_to_earnings.le(pre_event_days)
    )
    out["l1_pre_earnings_multiplier"] = np.where(pre_event, pre_mult, 1.0)

    macro_cfg = (config or {}).get("macro_regime", {})
    exp_thr = float(macro_cfg.get("expansion_threshold", 0.5))
    con_thr = float(macro_cfg.get("contraction_threshold", 0.0))
    macro_mult = macro_cfg.get("multipliers", {})
    m_exp = float(macro_mult.get("EXPANSION", 1.0))
    m_late = float(macro_mult.get("LATE_CYCLE", 0.7))
    m_con = float(macro_mult.get("CONTRACTION", 0.4))

    if "yield_curve_slope" in out.columns:
        slope = out["yield_curve_slope"]
        out["l1_regime"] = np.select(
            [slope.gt(exp_thr), slope.lt(con_thr)],
            ["EXPANSION", "CONTRACTION"],
            default="LATE_CYCLE",
        )
        out["l1_regime_multiplier"] = np.select(
            [out["l1_regime"].eq("EXPANSION"), out["l1_regime"].eq("CONTRACTION")],
            [m_exp, m_con],
            default=m_late,
        ).astype(float)
    else:
        out["l1_regime"] = "ABSENT"
        out["l1_regime_multiplier"] = 1.0

    out["l1_combined_multiplier"] = (
        out["l1_quality_multiplier"]
        * out["l1_post_earnings_multiplier"]
        * out["l1_pre_earnings_multiplier"]
        * out["l1_regime_multiplier"]
    )
    out["w_after_l1"] = out["w_raw_combined"] * out["l1_combined_multiplier"]

    # Net-zero normalization per date.
    out["w_demeaned"] = out["w_after_l1"] - out.groupby("date")["w_after_l1"].transform("mean")
    abs_sum = out["w_demeaned"].abs().groupby(out["date"]).transform("sum")
    out["final_position_weight"] = np.where(abs_sum.gt(0), out["w_demeaned"] / abs_sum * 2.0, 0.0)

    return out
