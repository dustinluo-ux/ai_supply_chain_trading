"""
Structural Breakdown Detector: IC decay, residual risk, regime misalignment.
Writes outputs/structural_breakdown.json. Spec: docs/RISK_MANAGEMENT_SPEC.md.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_PATH = ROOT / "outputs" / "structural_breakdown.json"

# Mandate ranges (beta to SMH) per pod
MANDATES = {
    "core": [0.8, 1.2],
    "extension": [-0.2, 0.6],
    "ballast": [0.0, 0.5],
}


def assess_structural_breakdown(
    regime_status: dict,
    prices_dict: dict,
    weights_history: list[dict],
    ic_history: list[dict],
    smh_prices: pd.DataFrame,
    config: dict,
) -> dict:
    """
    Run IC decay, residual risk, and regime misalignment sub-assessments;
    return merged dict with overall severity and write outputs/structural_breakdown.json.
    """
    cfg = config.get("risk_management", config)
    ic_baseline = float(cfg.get("ic_baseline", 0.0428))
    ic_decay_window = int(cfg.get("ic_decay_window", 20))
    rr_warn_mult = float(cfg.get("residual_risk_warning_multiple", 2.0))
    rr_crit_mult = float(cfg.get("residual_risk_critical_multiple", 3.0))
    beta_warn_buf = float(cfg.get("beta_mandate_warning_buffer", 0.3))
    beta_crit_buf = float(cfg.get("beta_mandate_critical_buffer", 0.6))

    out = dict(regime_status)

    # --- IC Decay ---
    try:
        ic_decay = _assess_ic_decay(ic_history, ic_baseline, ic_decay_window)
        out["ic_decay"] = ic_decay
    except Exception:
        out["ic_decay"] = {
            "rolling_ic_20d": None,
            "baseline": ic_baseline,
            "severity": "ok",
            "triggered": False,
        }

    # --- Residual Risk ---
    try:
        residual_risk = _assess_residual_risk(
            weights_history, prices_dict, rr_warn_mult, rr_crit_mult
        )
        out["residual_risk"] = residual_risk
    except Exception:
        out["residual_risk"] = {
            "pnl_vol_8w": 0.0,
            "explained_fraction": 0.0,
            "severity": "ok",
            "triggered": False,
        }

    # --- Regime Misalignment ---
    try:
        regime_misalignment = _assess_regime_misalignment(
            weights_history,
            prices_dict,
            smh_prices,
            MANDATES,
            beta_warn_buf,
            beta_crit_buf,
        )
        out["regime_misalignment"] = regime_misalignment
    except Exception:
        out["regime_misalignment"] = {
            "pod_betas": {},
            "mandates": {k: list(v) for k, v in MANDATES.items()},
            "severity": "ok",
            "triggered": False,
        }

    # Overall severity
    sev_map = {"ok": 0, "warning": 1, "critical": 2}
    max_sev = max(
        sev_map.get(out["ic_decay"].get("severity", "ok"), 0),
        sev_map.get(out["residual_risk"].get("severity", "ok"), 0),
        sev_map.get(out["regime_misalignment"].get("severity", "ok"), 0),
    )
    rev_map = {0: "ok", 1: "warning", 2: "critical"}
    out["structural_breakdown_severity"] = rev_map.get(max_sev, "ok")
    out["last_updated"] = datetime.now(timezone.utc).isoformat()

    try:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    except Exception:
        pass

    return out


def _assess_ic_decay(
    ic_history: list[dict],
    baseline: float,
    window: int,
) -> dict[str, Any]:
    result = {
        "rolling_ic_20d": None,
        "baseline": baseline,
        "severity": "ok",
        "triggered": False,
    }
    try:
        if not ic_history:
            return result
        # Last N entries by date (assume list is date-ordered or sort)
        entries = sorted(
            (e for e in ic_history if "ic" in e and e.get("ic") is not None),
            key=lambda x: x.get("date", ""),
        )[-window:]
        if len(entries) < 5:
            return result
        ics = [float(e["ic"]) for e in entries]
        mean_ic = float(np.mean(ics))
        result["rolling_ic_20d"] = mean_ic
        if mean_ic < 0:
            result["severity"] = "critical"
            result["triggered"] = True
        elif mean_ic < 0.5 * baseline:
            result["severity"] = "warning"
            result["triggered"] = True
    except Exception:
        pass
    return result


def _assess_residual_risk(
    weights_history: list[dict],
    prices_dict: dict,
    warn_mult: float,
    crit_mult: float,
) -> dict[str, Any]:
    result = {
        "pnl_vol_8w": 0.0,
        "explained_fraction": 0.0,
        "severity": "ok",
        "triggered": False,
    }
    try:
        if not weights_history or not prices_dict:
            return result

        # Build weekly P&L: for each entry (date, weights), compute next 5 trading days return
        pnl_list = []
        score_list = []
        ret_list = []

        for i, entry in enumerate(weights_history):
            date_str = entry.get("date")
            weights = entry.get("weights") or {}
            scores = entry.get("scores")  # optional
            if not date_str or not weights:
                continue
            try:
                as_of = pd.to_datetime(date_str)
            except Exception:
                continue

            tickers = [
                t for t in weights if t in prices_dict and prices_dict[t] is not None
            ]
            if not tickers:
                continue

            # Next 5 trading days returns per ticker
            next_returns = {}
            for t in tickers:
                df = prices_dict[t]
                if df.empty or "close" not in df.columns:
                    continue
                close = df["close"]
                if getattr(close, "ndim", 1) > 1:
                    close = close.iloc[:, 0]
                idx = df.index[df.index > as_of]
                if len(idx) < 5:
                    continue
                idx_5 = idx[:5]
                start_val = (
                    close.reindex(close.index[close.index <= as_of]).iloc[-1]
                    if len(close.reindex(close.index[close.index <= as_of]).dropna())
                    else None
                )
                if start_val is None or start_val == 0:
                    continue
                end_val = close.reindex(idx_5).dropna().iloc[-1] if len(idx_5) else None
                if end_val is None:
                    continue
                next_returns[t] = float(end_val / start_val - 1.0)

            if not next_returns:
                continue
            w_sum = sum(abs(weights.get(t, 0)) for t in next_returns)
            if w_sum <= 0:
                continue
            pnl = sum(float(weights.get(t, 0)) * next_returns[t] for t in next_returns)
            pnl_list.append(pnl)
            if scores and isinstance(scores, dict):
                rank = np.argsort(
                    np.argsort([scores.get(t, 0.5) for t in next_returns])
                )  # rank order
                score_list.append(np.mean(rank))
            ret_list.append(pnl)

        if len(pnl_list) < 8:
            return result

        pnl_arr = np.array(pnl_list)
        result["pnl_vol_8w"] = float(np.std(pnl_arr[-8:]))
        baseline_8w = (
            float(np.std(pnl_arr[:8])) if len(pnl_arr) >= 8 else result["pnl_vol_8w"]
        )
        if baseline_8w <= 0:
            baseline_8w = 1e-8

        # Explained fraction: Spearman between score rank and return
        if len(score_list) >= 8 and len(ret_list) >= 8:
            from scipy.stats import spearmanr

            r, _ = spearmanr(score_list[-8:], ret_list[-8:], nan_policy="omit")
            result["explained_fraction"] = float(
                np.clip(r * r if r == r else 0.0, 0.0, 1.0)
            )

        ratio = result["pnl_vol_8w"] / baseline_8w
        if ratio >= crit_mult:
            result["severity"] = "critical"
            result["triggered"] = True
        elif ratio >= warn_mult:
            result["severity"] = "warning"
            result["triggered"] = True
    except Exception:
        pass
    return result


def _assess_regime_misalignment(
    weights_history: list[dict],
    prices_dict: dict,
    smh_prices: pd.DataFrame,
    mandates: dict[str, list[float]],
    warn_buf: float,
    crit_buf: float,
) -> dict[str, Any]:
    result = {
        "pod_betas": {},
        "mandates": {k: list(v) for k, v in mandates.items()},
        "severity": "ok",
        "triggered": False,
    }
    try:
        if (
            not weights_history
            or not prices_dict
            or smh_prices is None
            or smh_prices.empty
        ):
            return result
        if len(weights_history) < 3:
            return result

        latest = weights_history[-1]
        weights = latest.get("weights") or {}
        date_str = latest.get("date")
        if not weights or not date_str:
            return result

        try:
            as_of = pd.to_datetime(date_str)
        except Exception:
            return result

        tickers = [t for t in weights if t in prices_dict]
        if not tickers:
            return result

        # SMH returns (last 20 trading days up to as_of)
        if "close" not in smh_prices.columns:
            close_smh = smh_prices.iloc[:, 0]
        else:
            close_smh = smh_prices["close"]
        if getattr(close_smh, "ndim", 1) > 1:
            close_smh = close_smh.iloc[:, 0]
        smh_slice = smh_prices[smh_prices.index <= as_of].tail(21)
        if len(smh_slice) < 20:
            for pod in mandates:
                result["pod_betas"][pod] = 1.0
            return result

        smh_ret = (
            close_smh.reindex(smh_slice.index).pct_change(fill_method=None).dropna()
        )
        if len(smh_ret) < 20:
            for pod in mandates:
                result["pod_betas"][pod] = 1.0
            return result
        smh_ret = smh_ret.iloc[-20:]
        common_idx = smh_ret.index

        # Portfolio returns: same 20 days, weighted sum of ticker returns
        port_ret_list = []
        for t in tickers:
            df = prices_dict[t]
            if df.empty or "close" not in df.columns:
                continue
            close = df["close"]
            if getattr(close, "ndim", 1) > 1:
                close = close.iloc[:, 0]
            r = close.pct_change(fill_method=None).reindex(common_idx).dropna()
            if len(r) < 20:
                continue
            port_ret_list.append((t, r.reindex(common_idx).fillna(0)))

        if not port_ret_list:
            for pod in mandates:
                result["pod_betas"][pod] = 1.0
            return result

        port_ret = pd.Series(0.0, index=common_idx)
        for t, ser in port_ret_list:
            port_ret = port_ret.add(ser.mul(weights.get(t, 0)), fill_value=0)
        smh_20 = smh_ret.reindex(common_idx).fillna(0)
        port_20 = port_ret.reindex(common_idx).fillna(0)
        var_smh = float(smh_20.var())
        if var_smh <= 0:
            var_smh = 1e-8
        cov_p = float(port_20.cov(smh_20))
        beta = cov_p / var_smh if var_smh != 0 else 1.0

        for pod in mandates:
            result["pod_betas"][pod] = beta

        low, high = mandates["core"][0], mandates["core"][1]
        if beta < low - crit_buf or beta > high + crit_buf:
            result["severity"] = "critical"
            result["triggered"] = True
        elif beta < low - warn_buf or beta > high + warn_buf:
            if result["severity"] != "critical":
                result["severity"] = "warning"
                result["triggered"] = True

        for pod in ("extension", "ballast"):
            low, high = mandates[pod][0], mandates[pod][1]
            if beta < low - crit_buf or beta > high + crit_buf:
                result["severity"] = "critical"
                result["triggered"] = True
            elif (beta < low - warn_buf or beta > high + warn_buf) and result[
                "severity"
            ] != "critical":
                result["severity"] = "warning"
                result["triggered"] = True
    except Exception:
        pass
    return result
