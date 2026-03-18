"""
Intraweek regime monitor: VIX, SPY 200-SMA, SMH daily return.
Writes outputs/regime_status.json. Exit 0 always. ASCII-only print (Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _main() -> int:
    parser = argparse.ArgumentParser(description="Regime monitor: VIX, SPY 200-SMA, SMH daily return.")
    parser.add_argument("--vix-threshold", type=float, default=30, help="VIX above this => EMERGENCY")
    parser.add_argument("--smh-threshold", type=float, default=-0.05, help="SMH daily return below this => EMERGENCY")
    parser.add_argument("--bull-score-floor", type=float, default=0.50, help="Score floor when SPY > 200-SMA (BULL)")
    parser.add_argument("--bear-score-floor", type=float, default=0.65, help="Score floor when SPY < 200-SMA (BEAR)")
    args = parser.parse_args()
    vix_threshold = args.vix_threshold
    smh_threshold = args.smh_threshold

    vix = None
    vix_series = None  # for Z-score (last 20 observations)
    try:
        import yfinance as yf
        t = yf.Ticker("^VIX")
        hist = t.history(period="25d")
        if hist is not None and not hist.empty and "Close" in hist.columns:
            vix = float(hist["Close"].iloc[-1])
            vix_series = hist["Close"].dropna()
    except Exception:
        pass

    spy_close = None
    spy_sma200 = None
    spy_below_sma = False
    try:
        import yfinance as yf
        t = yf.Ticker("SPY")
        spy_hist = t.history(period="220d")
        if spy_hist is not None and len(spy_hist) >= 200 and "Close" in spy_hist.columns:
            spy_close = float(spy_hist["Close"].iloc[-1])
            spy_sma200 = float(spy_hist["Close"].iloc[-200:].mean())
            spy_below_sma = spy_close < spy_sma200
    except Exception:
        pass

    smh_daily = None
    smh_shock = False
    smh_returns_20d = None
    try:
        import yfinance as yf
        t = yf.Ticker("SMH")
        smh_hist = t.history(period="25d")
        if smh_hist is not None and len(smh_hist) >= 2 and "Close" in smh_hist.columns:
            close = smh_hist["Close"]
            smh_daily = (float(close.iloc[-1]) / float(close.iloc[-2])) - 1.0
            rets = close.pct_change(fill_method=None).dropna()
            if len(rets) >= 10:
                smh_returns_20d = rets.iloc[-20:] if len(rets) >= 20 else rets
    except Exception:
        pass

    # Z-score BEAR triggers: need >= 10 observations; else fall back to absolute thresholds
    use_vix_z = vix_series is not None and len(vix_series) >= 10
    use_smh_z = smh_returns_20d is not None and len(smh_returns_20d) >= 10
    if use_vix_z and use_smh_z:
        print("[Regime] Z-score BEAR triggers active (VIX and SMH).", flush=True)
    elif not use_vix_z or not use_smh_z:
        print("[Regime] Insufficient history for Z-score -- using absolute thresholds.", flush=True)

    vix_trigger = False
    if vix is not None:
        if use_vix_z:
            vix_20d = vix_series.iloc[-20:] if len(vix_series) >= 20 else vix_series
            vix_mean = float(vix_20d.mean())
            vix_std = float(vix_20d.std())
            if vix_std > 0:
                vix_z = (vix - vix_mean) / vix_std
                vix_trigger = vix_z > 2.0 or vix > 40
            else:
                vix_trigger = vix > 40
        else:
            vix_trigger = vix > vix_threshold

    if not use_smh_z and smh_daily is not None:
        smh_shock = smh_daily < smh_threshold
    elif use_smh_z and smh_daily is not None and smh_returns_20d is not None:
        smh_mean = float(smh_returns_20d.mean())
        smh_std = float(smh_returns_20d.std())
        if smh_std > 0:
            smh_z = (smh_daily - smh_mean) / smh_std
            smh_shock = smh_z < -2.0 or smh_daily < -0.07
        else:
            smh_shock = smh_daily < -0.07

    emergency_reasons = []
    if vix_trigger:
        emergency_reasons.append(f"VIX {vix:.1f} (Z-score or backstop)" if use_vix_z else f"VIX {vix:.1f} > {vix_threshold}")
    if spy_below_sma:
        emergency_reasons.append("SPY < 200-SMA")
    if smh_shock and smh_daily is not None:
        emergency_reasons.append(f"SMH {smh_daily:.1%} (Z-score or -7%% backstop)" if use_smh_z else f"SMH {smh_daily:.1%} < {smh_threshold:.0%}")

    regime = "EMERGENCY" if emergency_reasons else "NORMAL"

    # Dynamic score floor: BEAR (SPY < 200-SMA) raises entry hurdle
    score_floor = args.bear_score_floor if spy_below_sma else args.bull_score_floor

    out = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "regime": regime,
        "reasons": emergency_reasons,
        "score_floor": score_floor,
        "vix": vix,
        "spy_close": spy_close,
        "spy_sma200": spy_sma200,
        "spy_below_sma": spy_below_sma,
        "smh_daily_return": smh_daily,
        "smh_shock": smh_shock,
        "thresholds": {
            "vix": vix_threshold,
            "smh_daily": smh_threshold,
            "bull_score_floor": args.bull_score_floor,
            "bear_score_floor": args.bear_score_floor,
        },
    }
    out_path = ROOT / "outputs" / "regime_status.json"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    except Exception:
        pass

    # --- Bayesian Meta-Allocator ---
    try:
        import yaml as _yaml
        from pods.meta_allocator import compute_pod_weights, load_pod_fitness, save_pod_fitness
        _mcfg_path = ROOT / "config" / "model_config.yaml"
        _pods_cfg: dict = {}
        if _mcfg_path.exists():
            with open(_mcfg_path, "r", encoding="utf-8") as _f:
                _mcfg = _yaml.safe_load(_f) or {}
            _pods_cfg = _mcfg.get("pods", {})
        _fitness_path = ROOT / _pods_cfg.get("fitness_path", "outputs/pod_fitness.json")
        _meta_weights_path = ROOT / _pods_cfg.get("meta_weights_path", "outputs/meta_weights.json")
        _meta_cfg = _pods_cfg.get("meta_allocator", {})
        _pod_fitness = load_pod_fitness(_fitness_path)
        _meta_weights = compute_pod_weights(
            pod_fitness=_pod_fitness,
            regime_status=out,
            prior=_meta_cfg.get("prior"),
            temperature=float(_meta_cfg.get("temperature", 0.5)),
            ballast_floor=float(_meta_cfg.get("ballast_floor", 0.20)),
        )
        _meta_out = {
            "as_of": out["as_of"],
            "regime": regime,
            "weights": _meta_weights,
            "fitness_used": _pod_fitness,
        }
        _meta_weights_path.parent.mkdir(parents=True, exist_ok=True)
        _meta_weights_path.write_text(json.dumps(_meta_out, indent=2), encoding="utf-8")
        print(
            f"[META] weights -- core={_meta_weights['core']:.3f} | "
            f"extension={_meta_weights['extension']:.3f} | "
            f"ballast={_meta_weights['ballast']:.3f}",
            flush=True,
        )
    except Exception as _e:
        print(f"[META] Meta-allocator skipped: {type(_e).__name__}: {_e}", flush=True)

    # --- Structural Breakdown ---
    try:
        from dotenv import load_dotenv
        import os as _os
        import yaml as _yaml
        import pandas as _pd
        load_dotenv(ROOT / ".env")
        _data_dir = _os.environ.get("DATA_DIR", "")
        _data_dir = Path(_data_dir) if _data_dir else None

        _tickers = []
        _universe_path = ROOT / "config" / "universe.yaml"
        if _universe_path.exists():
            with open(_universe_path, "r", encoding="utf-8") as _f:
                _ucfg = _yaml.safe_load(_f) or {}
            _pillars = _ucfg.get("pillars", {}) or {}
            for _pillar_tickers in _pillars.values():
                _tickers.extend(_pillar_tickers)

        _prices_dict = {}
        if _data_dir and _tickers:
            try:
                from src.data.csv_provider import load_prices as _load_prices
                _prices_dict = _load_prices(_data_dir, _tickers)
            except Exception:
                _prices_dict = {}

        _weights_history = []
        _last_weights_path = ROOT / "outputs" / "last_valid_weights.json"
        if _last_weights_path.exists():
            try:
                with open(_last_weights_path, "r", encoding="utf-8") as _f:
                    _cache = json.load(_f)
                _w = _cache.get("weights") or {}
                _as_of = _cache.get("as_of", "")
                _weights_history = [{"date": _as_of, "weights": _w}]
            except Exception:
                _weights_history = []

        _ic_history = []
        _ic_path = ROOT / "outputs" / "ic_monitor.json"
        if _ic_path.exists():
            try:
                with open(_ic_path, "r", encoding="utf-8") as _f:
                    _ic_data = json.load(_f)
                _ic_history = _ic_data if isinstance(_ic_data, list) else []
            except Exception:
                _ic_history = []

        _smh_prices = _pd.DataFrame()
        if _data_dir:
            _smh_csv = _data_dir / "benchmarks" / "SMH.csv"
            if _smh_csv.exists():
                try:
                    _smh_df = _pd.read_csv(_smh_csv, index_col=0, parse_dates=False)
                    _smh_df.index = _pd.to_datetime(_smh_df.index, format="mixed", dayfirst=True)
                    _smh_prices = _smh_df
                except Exception:
                    pass

        _breakdown_cfg = {}
        _mcfg_path = ROOT / "config" / "model_config.yaml"
        if _mcfg_path.exists():
            try:
                with open(_mcfg_path, "r", encoding="utf-8") as _f:
                    _mcfg = _yaml.safe_load(_f) or {}
                _breakdown_cfg = _mcfg.get("risk_management", {}) or {}
            except Exception:
                pass

        from src.monitoring.structural_breakdown import assess_structural_breakdown
        _breakdown_out = assess_structural_breakdown(
            regime_status=out,
            prices_dict=_prices_dict,
            weights_history=_weights_history,
            ic_history=_ic_history,
            smh_prices=_smh_prices,
            config=_breakdown_cfg,
        )
        _ic_sev = _breakdown_out.get("ic_decay", {}).get("severity", "ok")
        _res_sev = _breakdown_out.get("residual_risk", {}).get("severity", "ok")
        _mis_sev = _breakdown_out.get("regime_misalignment", {}).get("severity", "ok")
        _overall = _breakdown_out.get("structural_breakdown_severity", "ok")
        print(
            f"[BREAKDOWN] ic={_ic_sev} | residual={_res_sev} | misalignment={_mis_sev} | overall={_overall}",
            flush=True,
        )
    except Exception as _e:
        print(f"[BREAKDOWN] skipped: {type(_e).__name__}: {_e}", flush=True)

    if regime == "NORMAL":
        vix_s = f"{vix:.1f}" if vix is not None else "N/A"
        spy_s = f"{spy_close:.1f}" if spy_close is not None else "N/A"
        sma_s = f"{spy_sma200:.1f}" if spy_sma200 is not None else "N/A"
        cmp = ">=" if not spy_below_sma else "<"
        smh_s = f"{smh_daily:+.1%}" if smh_daily is not None else "N/A"
        print(f"[REGIME] NORMAL  -- VIX {vix_s} | SPY {spy_s} {cmp} SMA200 {sma_s} | SMH {smh_s} | score_floor={score_floor}", flush=True)
    else:
        reasons_str = " | ".join(emergency_reasons)
        print(f"[REGIME] EMERGENCY -- {reasons_str}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
