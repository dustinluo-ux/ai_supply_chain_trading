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
