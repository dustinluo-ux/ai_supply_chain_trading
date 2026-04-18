"""
Two-Lane Risk Lane: consolidates exposure-control inputs into RiskConstraints.

Reads drawdown tracker, SPY/VIX benchmarks, strategy_params risk_overlay, and
optional IBKR account summary. Does not modify order flow or risk_manager.
"""
from __future__ import annotations

import json
import logging
import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from dotenv import load_dotenv as _load_dotenv

from src.risk.types import RiskConstraints

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
_load_dotenv(ROOT / ".env", override=True)
STRATEGY_PARAMS_PATH = ROOT / "config" / "strategy_params.yaml"
TRADING_CONFIG_PATH = ROOT / "config" / "trading_config.yaml"
DRAWDOWN_TRACKER_PATH = ROOT / "outputs" / "drawdown_tracker.json"


def _load_risk_overlay_config() -> dict[str, Any]:
    """Same pattern as src/execution/risk_manager.py:_load_risk_overlay_config(); SPY window default 100 per RiskPolicy spec."""
    defaults = {
        "vix_elevated_threshold": 28,
        "spy_sma_window": 100,
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
        logger.warning("[RiskPolicy] Could not read strategy_params risk_overlay: %s", e)
        return defaults


def _benchmarks_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "C:/ai_supply_chain_trading/trading_data")) / "benchmarks"


def _load_benchmark_close(path: Path) -> pd.Series | None:
    """Load daily close series (index = date); graceful None on failure or missing file."""
    try:
        if not path.exists():
            return None
        df = pd.read_csv(path)
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.loc[:, ~df.columns.duplicated(keep="last")]
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
        logger.warning("[RiskPolicy] Failed to load benchmark %s: %s", path, e)
        return None


def _load_trading_ib_config() -> tuple[str, int, int]:
    host, port, cid = "127.0.0.1", 7497, 5
    if not TRADING_CONFIG_PATH.exists():
        return host, port, cid
    try:
        with open(TRADING_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        ib = (data.get("trading") or {}).get("ib") or {}
        if isinstance(ib.get("host"), str) and ib["host"].strip():
            host = ib["host"].strip()
        if ib.get("port") is not None:
            port = int(ib["port"])
        if ib.get("client_id") is not None:
            cid = int(ib["client_id"])
    except Exception as e:
        logger.warning("[RiskPolicy] Could not read trading_config ib: %s", e)
    return host, port, cid


class RiskPolicy:
    """Exposure control: evaluate once per as_of into RiskConstraints."""

    def evaluate(self, as_of: pd.Timestamp) -> RiskConstraints:
        audit_log: list[str] = []
        as_of_ts = pd.Timestamp(as_of).normalize()
        position_scale = Decimal("1")
        stop_loss_active = False
        cfg = _load_risk_overlay_config()

        # 1. Drawdown stop-loss
        try:
            if DRAWDOWN_TRACKER_PATH.exists():
                with open(DRAWDOWN_TRACKER_PATH, encoding="utf-8") as f:
                    dd = json.load(f)
                if isinstance(dd, dict) and bool(dd.get("flatten_active")):
                    audit_log.append("drawdown_tracker: flatten_active=True")
                    return RiskConstraints(
                        as_of=as_of_ts,
                        beta_cap=Decimal("0"),
                        position_scale=Decimal("0"),
                        stop_loss_active=True,
                        margin_headroom_pct=Decimal("1"),
                        audit_log=list(audit_log),
                    )
        except Exception as e:
            logger.warning("[RiskPolicy] drawdown_tracker read failed: %s", e)

        # 2. SPY / SMA regime gate
        spy_path = _benchmarks_dir() / "SPY.csv"
        spy_series = _load_benchmark_close(spy_path)
        if spy_series is None or spy_series.empty:
            audit_log.append("SPY CSV missing: skipping regime gate")
        else:
            try:
                sma_w = int(cfg["spy_sma_window"])
                spy_c = spy_series.asof(as_of_ts) if len(spy_series) else float("nan")
                spy_sma = (
                    spy_series.rolling(sma_w, min_periods=max(1, sma_w // 4))
                    .mean()
                    .asof(as_of_ts)
                    if len(spy_series)
                    else float("nan")
                )
                if pd.isna(spy_c) or pd.isna(spy_sma):
                    audit_log.append("SPY data insufficient at as_of: skipping regime gate")
                elif float(spy_c) < float(spy_sma):
                    position_scale *= Decimal("0.0")
                    audit_log.append(f"SPY < SMA{sma_w}: regime=BEAR → position_scale=0.0")
            except Exception as e:
                logger.warning("[RiskPolicy] SPY regime gate failed: %s", e)
                audit_log.append("SPY regime gate error: skipped")

        # 3. VIX overlay
        vix_path = _benchmarks_dir() / "VIX.csv"
        vix_series = _load_benchmark_close(vix_path)
        if vix_series is None or vix_series.empty:
            audit_log.append("VIX CSV missing: skipping VIX overlay")
        else:
            try:
                vix_thr = float(cfg["vix_elevated_threshold"])
                vix_mult = float(cfg["vix_multiplier"])
                vix_c = vix_series.asof(as_of_ts) if len(vix_series) else float("nan")
                if not pd.isna(vix_c) and float(vix_c) > vix_thr:
                    position_scale *= Decimal(str(vix_mult))
                    audit_log.append(
                        f"VIX={float(vix_c):.1f} > {vix_thr} → scale×{vix_mult}"
                    )
            except Exception as e:
                logger.warning("[RiskPolicy] VIX overlay failed: %s", e)
                audit_log.append("VIX CSV missing: skipping VIX overlay")

        # 4. Margin headroom
        margin_headroom_pct = Decimal("1")
        try:
            from src.data import ibkr_live_provider as _ibkr

            host, port, base_cid = _load_trading_ib_config()
            client_id = base_cid + (int(time.time()) % 89)
            ib = _ibkr.connect(host, port, client_id=client_id)
            try:
                acct = _ibkr.get_account_summary(ib)
            finally:
                ib.disconnect()
            nav = float(acct.get("net_liquidation", 0.0) or 0.0)
            avail = float(acct.get("available_funds", 0.0) or 0.0)
            if nav <= 0:
                margin_headroom_pct = Decimal("1")
            else:
                ratio = avail / nav
                if ratio < 0.15:
                    position_scale *= Decimal("0.8")
                    audit_log.append("margin headroom < 15% → scale×0.8")
                    margin_headroom_pct = Decimal(str(round(ratio, 6)))
                else:
                    margin_headroom_pct = Decimal("1")
        except Exception:
            margin_headroom_pct = Decimal("1")
            audit_log.append("margin: IBKR unavailable, using default 1.0")

        # 5. beta_cap = position_scale
        beta_cap = position_scale

        return RiskConstraints(
            as_of=as_of_ts,
            beta_cap=beta_cap,
            position_scale=position_scale,
            stop_loss_active=stop_loss_active,
            margin_headroom_pct=margin_headroom_pct,
            audit_log=list(audit_log),
        )
