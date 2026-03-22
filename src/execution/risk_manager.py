"""
Additive risk overlay: tiered metadata from SPY trend, VIX level, and cross-sectional correlation.
Observational only — does not modify order flow.
"""
from __future__ import annotations

import csv
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BENCHMARKS_DIR = Path(r"C:\ai_supply_chain_trading\trading_data\benchmarks")
SPY_CSV = DEFAULT_BENCHMARKS_DIR / "SPY.csv"
VIX_CSV = DEFAULT_BENCHMARKS_DIR / "VIX.csv"
SMH_CSV = DEFAULT_BENCHMARKS_DIR / "SMH.csv"
STRATEGY_PARAMS_PATH = ROOT / "config" / "strategy_params.yaml"


def _load_benchmark_close(path: Path) -> pd.Series | None:
    """Load daily close series (index = date), same normalization as tail-hedge runner."""
    try:
        if not path.exists():
            return None
        df = pd.read_csv(path)
        df.columns = [str(c).strip().lower() for c in df.columns]
        if "close" not in df.columns and "adjusted_close" in df.columns:
            df["close"] = df["adjusted_close"]
        if "close" not in df.columns:
            return None
        if "date" in df.columns:
            dt = pd.to_datetime(df["date"], errors="coerce")
            df = df.assign(_d=dt).dropna(subset=["_d"]).set_index("_d")
        else:
            idx = pd.to_datetime(df.iloc[:, 0], errors="coerce")
            df = df.assign(_d=idx).dropna(subset=["_d"]).set_index("_d")
        s = pd.to_numeric(df["close"], errors="coerce").dropna().sort_index()
        s = s[s.index.weekday < 5]
        return s.ffill(limit=5)
    except Exception as e:
        logger.warning("[RiskOverlay] Failed to load benchmark %s: %s", path, e)
        return None


def _ensure_spy_csv_subprocess() -> None:
    script = ROOT / "scripts" / "download_spy.py"
    if not script.exists():
        logger.warning("[RiskOverlay] download_spy.py not found at %s", script)
        return
    try:
        subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            timeout=120,
            check=False,
        )
    except Exception as e:
        logger.warning("[RiskOverlay] SPY download subprocess failed: %s", e)


def _ensure_vix_csv_subprocess() -> None:
    script = ROOT / "scripts" / "download_vix.py"
    if not script.exists():
        logger.warning("[RiskOverlay] download_vix.py not found at %s", script)
        return
    try:
        subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            timeout=120,
            check=False,
        )
    except Exception as e:
        logger.warning("[RiskOverlay] VIX download subprocess failed: %s", e)


def _ensure_smh_csv_subprocess() -> None:
    script = ROOT / "scripts" / "download_smh.py"
    if not script.exists():
        logger.warning("[RiskOverlay] download_smh.py not found at %s", script)
        return
    try:
        subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            timeout=120,
            check=False,
        )
    except Exception as e:
        logger.warning("[RiskOverlay] SMH download subprocess failed: %s", e)


def _load_risk_overlay_config() -> dict[str, Any]:
    defaults = {
        "vix_elevated_threshold": 28,
        "spy_sma_window": 200,
        "sector_corr_threshold": 0.85,
        "corr_lookback_days": 60,
        "vix_multiplier": 0.6,
    }
    if not STRATEGY_PARAMS_PATH.exists():
        return defaults
    try:
        with open(STRATEGY_PARAMS_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        ro = data.get("risk_overlay") or {}
        out = defaults.copy()
        for k in defaults:
            if k in ro and ro[k] is not None:
                if k in ("spy_sma_window", "corr_lookback_days"):
                    out[k] = int(ro[k])
                else:
                    out[k] = float(ro[k])
        return out
    except Exception as e:
        logger.warning("[RiskOverlay] Could not read strategy_params risk_overlay: %s", e)
        return defaults


def _avg_pairwise_correlation(
    prices_dict: dict[str, pd.DataFrame] | None,
    as_of: pd.Timestamp,
    lookback: int,
    threshold: float,
) -> tuple[float | None, float]:
    """
    Mean pairwise correlation of daily returns over lookback days.
    Returns (max_positions_override or None, average_corr).
    """
    if not prices_dict:
        return None, 0.0
    rets: dict[str, pd.Series] = {}
    for t, df in prices_dict.items():
        if df is None or df.empty:
            continue
        try:
            slice_df = df[df.index <= as_of].tail(lookback + 5)
            if slice_df.empty or "close" not in slice_df.columns:
                continue
            close = slice_df["close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            r = close.pct_change().dropna().tail(lookback)
            if len(r) < max(20, lookback // 3):
                continue
            rets[str(t)] = r
        except Exception:
            continue
    if len(rets) < 2:
        return None, 0.0
    mat = pd.DataFrame(rets)
    mat = mat.dropna(how="any")
    if mat.shape[0] < 10 or mat.shape[1] < 2:
        return None, 0.0
    corr = mat.corr()
    vals: list[float] = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = corr.iloc[i, j]
            if pd.notna(v):
                vals.append(float(v))
    if not vals:
        return None, 0.0
    avg = float(np.mean(vals))
    override = 8 if avg > float(threshold) else None
    return override, avg


class RiskOverlay:
    """
    Tiered risk metadata from SPY 200-SMA, VIX level, and average pairwise correlation.
    """

    def __init__(
        self,
        spy_series: pd.Series | None = None,
        vix_series: pd.Series | None = None,
        prices_dict: dict[str, pd.DataFrame] | None = None,
        *,
        benchmarks_dir: Path | None = None,
    ) -> None:
        self._cfg = _load_risk_overlay_config()
        self._prices_dict = prices_dict or {}
        bdir = benchmarks_dir or DEFAULT_BENCHMARKS_DIR
        spy_path = bdir / "SPY.csv"
        vix_path = bdir / "VIX.csv"
        smh_path = bdir / "SMH.csv"

        self._spy = spy_series
        self._vix = vix_series

        if self._spy is None or self._spy.empty:
            if not spy_path.exists():
                _ensure_spy_csv_subprocess()
            self._spy = _load_benchmark_close(spy_path)
            if self._spy is None:
                self._spy = pd.Series(dtype=float)

        if self._vix is None or self._vix.empty:
            if not vix_path.exists():
                _ensure_vix_csv_subprocess()
            self._vix = _load_benchmark_close(vix_path)
            if self._vix is None:
                self._vix = pd.Series(dtype=float)

        if not smh_path.exists():
            _ensure_smh_csv_subprocess()

    def evaluate(self, as_of_date: Any) -> dict[str, Any]:
        """Return tier metadata and sizing hints (observational)."""
        try:
            as_of_iso = pd.Timestamp(as_of_date).strftime("%Y-%m-%d")
        except Exception:
            as_of_iso = pd.Timestamp.today().strftime("%Y-%m-%d")
        fallback = {
            "tier1_trend": "BULL",
            "tier2_vix": "NORMAL",
            "allocation_multiplier": 1.0,
            "max_positions_override": None,
            "tier3_corr": 0.0,
            "as_of": as_of_iso,
        }
        try:
            as_of = pd.Timestamp(as_of_date).normalize()
            vix_thr = float(self._cfg["vix_elevated_threshold"])
            sma_w = int(self._cfg["spy_sma_window"])
            corr_thr = float(self._cfg["sector_corr_threshold"])
            lookback = int(self._cfg["corr_lookback_days"])
            vix_mult = float(self._cfg["vix_multiplier"])

            spy_c = self._spy.asof(as_of) if len(self._spy) else np.nan
            spy_sma = self._spy.rolling(sma_w, min_periods=max(1, sma_w // 4)).mean().asof(as_of) if len(self._spy) else np.nan

            if pd.isna(spy_c) or pd.isna(spy_sma):
                tier1 = "BULL"
            else:
                tier1 = "BULL" if float(spy_c) >= float(spy_sma) else "BEAR"

            vix_c = self._vix.asof(as_of) if len(self._vix) else np.nan
            if pd.isna(vix_c):
                tier2 = "NORMAL"
            else:
                tier2 = "ELEVATED" if float(vix_c) > vix_thr else "NORMAL"

            if tier1 == "BEAR":
                mult = 0.0
            elif tier2 == "ELEVATED" and tier1 == "BULL":
                mult = vix_mult
            else:
                mult = 1.0

            max_pos, avg_corr = _avg_pairwise_correlation(
                self._prices_dict, as_of, lookback, corr_thr,
            )

            return {
                "tier1_trend": tier1,
                "tier2_vix": tier2,
                "allocation_multiplier": float(mult),
                "max_positions_override": max_pos,
                "tier3_corr": float(avg_corr) if pd.notna(avg_corr) else 0.0,
                "as_of": as_of.strftime("%Y-%m-%d"),
            }
        except Exception as e:
            logger.warning("[RiskOverlay] evaluate failed: %s", e)
            return fallback


def append_risk_metadata_csv(row: dict[str, Any], csv_path: Path | None = None) -> None:
    """Append one row to risk_metadata_history.csv (create with header if missing)."""
    path = csv_path or (ROOT / "outputs" / "risk_metadata_history.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    run_ts = datetime.now(timezone.utc).isoformat()
    out_row = {**row, "run_timestamp": run_ts}
    fieldnames = [
        "tier1_trend",
        "tier2_vix",
        "allocation_multiplier",
        "max_positions_override",
        "tier3_corr",
        "as_of",
        "run_timestamp",
    ]
    file_exists = path.exists()
    try:
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not file_exists:
                w.writeheader()
            w.writerow(out_row)
    except Exception as e:
        logger.warning("[RiskOverlay] Could not append %s: %s", path, e)
