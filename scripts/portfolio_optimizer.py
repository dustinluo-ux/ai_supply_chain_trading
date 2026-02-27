"""
Volatility-Adjusted Alpha Tilt portfolio optimizer.

Reads outputs/last_signal.json and price CSVs, computes 30-day vol, builds
weights = score/vol normalized and capped at max_weight. Writes last_valid_weights.json
and last_optimized_weights.json. Exit 0 on success, 1 if last_signal missing.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _main() -> int:
    parser = argparse.ArgumentParser(description="Volatility-Adjusted Alpha Tilt optimizer.")
    parser.add_argument("--top-quantile", type=float, default=0.75, help="Quantile cutoff — e.g. 0.75 = top 25%% of scored tickers eligible")
    parser.add_argument("--score-floor", type=float, default=0.50, help="Hard minimum score — no ticker with score <= floor is eligible (overridden by regime_status.json if present)")
    parser.add_argument("--bear-score-floor", type=float, default=0.65, help="Score floor override when SPY is in BEAR regime (close < 200-SMA)")
    parser.add_argument("--max-weight", type=float, default=0.25, help="Max weight per ticker (0-1)")
    parser.add_argument("--vol-window", type=int, default=30, help="Rolling window for volatility (days)")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    # 1. ROOT and path already set at top
    last_signal_path = ROOT / "outputs" / "last_signal.json"
    if not last_signal_path.exists():
        print("ERROR: last_signal.json not found.", flush=True)
        return 1
    with open(last_signal_path, "r", encoding="utf-8") as f:
        last_signal = json.load(f)
    if not last_signal or not isinstance(last_signal, dict):
        print("ERROR: last_signal.json not found.", flush=True)
        return 1

    # 2–3. Scores dict
    scores = {}
    for ticker, entry in last_signal.items():
        if not isinstance(entry, dict):
            continue
        sc = entry.get("score")
        if sc is None:
            continue
        try:
            v = float(sc)
            if v != v:  # NaN
                continue
            scores[ticker] = v
        except (TypeError, ValueError):
            continue
    if not scores:
        print("ERROR: last_signal.json not found.", flush=True)
        return 1

    # 4. Load prices
    from src.data.csv_provider import load_data_config, load_prices
    data_cfg = load_data_config()
    data_dir = data_cfg["data_dir"]
    prices_dict = load_prices(data_dir, list(scores.keys()))
    if not prices_dict:
        print("ERROR: No price data loaded.", flush=True)
        return 1

    # NAV fetch (update portfolio_state.json if present)
    from pathlib import Path as _Path
    import json as _json
    from src.execution.ibkr_nav import fetch_nav

    state_path = ROOT / "outputs" / "portfolio_state.json"
    nav = fetch_nav()
    if nav is not None:
        print(f"[NAV] IBKR NAV: ${nav:,.2f}", flush=True)
        if state_path.exists():
            try:
                ps = _json.loads(state_path.read_text())
                ps["last_nav"] = nav
                ps["last_nav_fetched_at"] = datetime.now(timezone.utc).isoformat()
                state_path.write_text(_json.dumps(ps, indent=2))
            except Exception:
                pass
    else:
        nav = None
        if state_path.exists():
            try:
                ps = _json.loads(state_path.read_text())
                nav = ps.get("last_nav")
                if nav:
                    print(f"[NAV] IBKR unavailable -- using last known NAV ${nav:,.2f}", flush=True)
            except Exception:
                pass
        if nav is None:
            print("[NAV] IBKR unavailable and no last_nav cached -- share counts will be skipped", flush=True)

    # 5a. Regime detection — prefer regime_status.json (written by regime_monitor.py),
    # fall back to independent SPY 200-SMA check if not available or stale.
    import numpy as np
    regime = "UNKNOWN"
    score_floor = args.score_floor

    # Try to read score_floor from regime_status.json (single source of truth)
    _regime_status_path = ROOT / "outputs" / "regime_status.json"
    _loaded_from_monitor = False
    if _regime_status_path.exists():
        try:
            import json as _json_r
            _rs = _json_r.loads(_regime_status_path.read_text(encoding="utf-8"))
            _floor_from_monitor = _rs.get("score_floor")
            _regime_from_monitor = _rs.get("regime", "UNKNOWN")
            if _floor_from_monitor is not None:
                score_floor = float(_floor_from_monitor)
                regime = "BULL" if not _rs.get("spy_below_sma", False) else "BEAR"
                if _regime_from_monitor == "EMERGENCY":
                    regime = "EMERGENCY"
                _loaded_from_monitor = True
                print(f"[REGIME] Read from regime_status.json: {regime}, score_floor={score_floor}", flush=True)
        except Exception:
            pass

    if not _loaded_from_monitor:
        # Fallback: independent SPY 200-SMA check via price CSVs
        try:
            spy_dict = load_prices(data_dir, ["SPY"])
            if spy_dict and "SPY" in spy_dict:
                spy_df = spy_dict["SPY"]
                if "close" in spy_df.columns and len(spy_df) >= 200:
                    close_series = spy_df["close"]
                    if isinstance(close_series, __import__("pandas").DataFrame):
                        close_series = close_series.iloc[:, 0]
                    spy_close = float(close_series.iloc[-1])
                    spy_sma200 = float(close_series.iloc[-200:].mean())
                    if spy_close < spy_sma200:
                        regime = "BEAR"
                        score_floor = args.bear_score_floor
                        print(f"[REGIME] BEAR -- SPY {spy_close:.2f} < 200-SMA {spy_sma200:.2f} -- score_floor raised to {score_floor}", flush=True)
                    else:
                        regime = "BULL"
                        print(f"[REGIME] BULL -- SPY {spy_close:.2f} >= 200-SMA {spy_sma200:.2f} -- score_floor={score_floor}", flush=True)
                else:
                    print(f"[REGIME] SPY data insufficient for 200-SMA (rows={len(spy_df)}); using default floor", flush=True)
            else:
                print("[REGIME] SPY prices unavailable; using default floor", flush=True)
        except Exception as e:
            print(f"[REGIME] SPY regime check failed ({e}); using default floor", flush=True)

    # 5. EWMA volatility per ticker (RiskMetrics lambda=0.94, span=38)
    EWMA_SPAN = 38  # round(2/(1-0.94)) - 1
    vol_30d = {}
    for ticker, df in prices_dict.items():
        if df is None or df.empty or "close" not in df.columns:
            continue
        try:
            returns = df["close"].pct_change(fill_method=None).dropna()
            if len(returns) < 2:
                continue
            ewma_std = returns.ewm(span=EWMA_SPAN, adjust=False).std()
            vol = float(ewma_std.iloc[-1]) if len(ewma_std) else None
            if vol is None or vol != vol or vol <= 0:
                vol = float(returns.std())
            if vol is None or vol != vol or vol <= 0:
                vol = 0.01
            vol_30d[ticker] = vol
        except Exception:
            continue

    # 5b. Liquidity-scaled caps: adv_i = 20d mean(close*volume), cap_i = clip(base*sqrt(adv_i/adv_median), 0.10, 0.40)
    BASE_CAP, CAP_FLOOR, CAP_CEIL = 0.20, 0.10, 0.40
    adv = {}
    for ticker, df in prices_dict.items():
        if df is None or df.empty or "close" not in df.columns:
            continue
        if "volume" not in df.columns:
            adv[ticker] = None
            continue
        try:
            close = df["close"]
            if hasattr(close, "iloc") and getattr(close, "ndim", 1) > 1:
                close = close.iloc[:, 0]
            vol = df["volume"]
            if hasattr(vol, "iloc") and getattr(vol, "ndim", 1) > 1:
                vol = vol.iloc[:, 0]
            dollar_vol = (close * vol).dropna()
            if len(dollar_vol) < 20:
                adv[ticker] = None
                continue
            adv[ticker] = float(dollar_vol.iloc[-20:].mean())
        except Exception:
            adv[ticker] = None
    adv_values = [v for v in adv.values() if v is not None and v > 0]
    adv_median = float(np.median(adv_values)) if adv_values else 1.0
    liquidity_cap = {}
    for ticker in vol_30d:
        if adv.get(ticker) is None or adv_median <= 0:
            liquidity_cap[ticker] = BASE_CAP
        else:
            raw = BASE_CAP * np.sqrt(adv[ticker] / adv_median)
            liquidity_cap[ticker] = float(np.clip(raw, CAP_FLOOR, CAP_CEIL))

    # 6. Eligible: score > effective_threshold (top quantile, with floor) and valid vol
    top_quantile = args.top_quantile
    # score_floor already set by regime detection (5a) — do not overwrite
    score_threshold = float(np.quantile(list(scores.values()), top_quantile))
    effective_threshold = max(score_threshold, score_floor)
    eligible = [t for t in scores if t in vol_30d and scores[t] > effective_threshold]

    # 6b. HRP base weights for eligible (fallback to score/vol if HRP fails or < 2 tickers with enough history)
    use_hrp = False
    hrp_base_weight = {}  # ticker -> base weight for display
    try:
        import pandas as pd
        lookback_days = 60
        min_obs = 30
        returns_dict = {}
        for t in eligible:
            if t not in prices_dict or prices_dict[t] is None or prices_dict[t].empty or "close" not in prices_dict[t].columns:
                continue
            df = prices_dict[t]
            close = df["close"]
            if hasattr(close, "iloc") and getattr(close, "ndim", 1) > 1:
                close = close.iloc[:, 0]
            ret = close.pct_change(fill_method=None).dropna()
            if len(ret) < min_obs:
                continue
            ret = ret.iloc[-lookback_days:]
            returns_dict[t] = ret
        if len(returns_dict) < 2:
            raise ValueError("fewer than 2 tickers with sufficient return history")
        returns_df = pd.concat(returns_dict, axis=1, join="outer")
        valid_counts = returns_df.notna().sum()
        keep = valid_counts >= min_obs
        returns_df = returns_df.loc[:, keep]
        if returns_df.shape[1] < 2:
            raise ValueError("fewer than 2 tickers with >= 30 valid observations")
        from pypfopt.hierarchical_portfolio import HRPOpt
        hrp = HRPOpt(returns=returns_df)
        hrp_result = hrp.optimize(linkage_method="ward")
        hrp_weights = hrp_result.to_dict() if hasattr(hrp_result, "to_dict") else dict(hrp_result)
        dropped = [t for t in eligible if t not in hrp_weights]
        hrp_sum = sum(hrp_weights.values())
        equal_share = (1.0 - hrp_sum) / len(dropped) if dropped else 0.0
        for t in dropped:
            hrp_weights[t] = equal_share
        use_hrp = True
        hrp_base_weight = {t: hrp_weights[t] for t in eligible}
    except Exception as e:
        print(f"[Optimizer] HRP failed: {e} -- falling back to score/vol", flush=True)

    # 7. Fallback: top-3 equal weight
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fallback = False
    if not eligible:
        fallback = True
        top3 = sorted(scores.keys(), key=lambda t: scores[t], reverse=True)[:3]
        weights = {t: 1.0 / 3.0 for t in top3} if top3 else {}
        metadata = {t: {"score": scores[t], "vol_30d": vol_30d.get(t), "raw_weight": 1.0 / 3.0} for t in top3} if top3 else {}
        print("WARNING: No tickers above score threshold. Falling back to top-3 equal weight.", flush=True)

    if not fallback:
        if use_hrp:
            # HRP + alpha tilt: base_weight * (score / mean_score), renormalize, then liquidity cap, renormalize
            mean_score = float(np.mean([scores[t] for t in eligible]))
            if mean_score <= 0:
                mean_score = 1e-9
            tilted_w = {t: hrp_base_weight[t] * (scores[t] / mean_score) for t in eligible}
            total_tilted = sum(tilted_w.values())
            if total_tilted <= 0:
                tilted_w = {t: 1.0 / len(eligible) for t in eligible}
            else:
                tilted_w = {t: tilted_w[t] / total_tilted for t in eligible}
            w = tilted_w.copy()
            raw_w = tilted_w.copy()  # for metadata display
        else:
            # Score/vol (existing)
            raw_w = {t: scores[t] / vol_30d[t] for t in eligible}
            total_raw = sum(raw_w.values())
            if total_raw <= 0:
                eligible = []
                fallback = True
                top3 = sorted(scores.keys(), key=lambda t: scores[t], reverse=True)[:3]
                weights = {t: 1.0 / 3.0 for t in top3} if top3 else {}
                metadata = {t: {"score": scores[t], "vol_30d": vol_30d.get(t), "raw_weight": 1.0 / 3.0} for t in top3} if top3 else {}
            else:
                w = {t: raw_w[t] / total_raw for t in eligible}

        if not fallback:
            # 10. Iterative cap at per-ticker liquidity-scaled cap
            while True:
                cap_t = {t: liquidity_cap.get(t, BASE_CAP) for t in w}
                capped = {t for t in w if w[t] > cap_t[t]}
                uncapped = {t for t in w if w[t] <= cap_t[t]}
                if not capped:
                    break
                excess = sum(w[t] - cap_t[t] for t in capped)
                for t in capped:
                    w[t] = cap_t[t]
                if uncapped:
                    total_uncapped = sum(w[t] for t in uncapped)
                    for t in uncapped:
                        w[t] += excess * (w[t] / total_uncapped)
                else:
                    break
            total_after_cap = sum(w.values())
            if total_after_cap > 0:
                w = {t: w[t] / total_after_cap for t in w}
            weights = w
            metadata = {
                t: {
                    "score": scores[t],
                    "vol_30d": vol_30d[t],
                    "raw_weight": raw_w.get(t),
                    "hrp_weight": hrp_base_weight.get(t) if use_hrp else None,
                }
                for t in eligible
            }

    # 11. Write last_valid_weights.json
    out_dir = ROOT / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    valid_path = out_dir / "last_valid_weights.json"
    with open(valid_path, "w", encoding="utf-8") as f:
        json.dump({"as_of": as_of, "weights": weights}, f, indent=2)

    # 12. Write last_optimized_weights.json
    opt_method = "hrp_alpha_tilt" if (use_hrp and not fallback) else "volatility_adjusted_alpha_tilt"
    optimized = {
        "as_of": as_of,
        "method": opt_method,
        "regime": regime,
        "params": {"top_quantile": args.top_quantile, "score_floor": score_floor, "max_weight": args.max_weight, "vol_window": args.vol_window},
        "weights": weights,
        "metadata": metadata,
    }
    opt_path = out_dir / "last_optimized_weights.json"
    with open(opt_path, "w", encoding="utf-8") as f:
        json.dump(optimized, f, indent=2)

    # Update portfolio_state.json if it exists
    if state_path.exists():
        try:
            ps = _json.loads(state_path.read_text())
            ps["target_weights"] = weights
            ps["cash_weight"] = 1.0 - sum(weights.values())
            ps["regime"] = "NORMAL" if regime == "BULL" else regime
            today_d = datetime.now(timezone.utc).date()
            ps["weekly_lock"] = {
                "locked": True,
                "rebalance_date": today_d.isoformat(),
                "locked_until": (today_d + timedelta(days=7)).isoformat(),
            }
            ps["last_updated"] = datetime.now(timezone.utc).isoformat()
            if nav is not None and nav > 0:
                holdings = {}
                for t, w in weights.items():
                    close_val = last_signal.get(t, {}).get("latest_close")
                    if close_val is None and t in prices_dict:
                        close_ser = prices_dict[t]["close"]
                        if hasattr(close_ser, "iloc"):
                            close_val = float(close_ser.iloc[-1]) if getattr(close_ser, "ndim", 1) == 1 else float(close_ser.iloc[:, 0].iloc[-1])
                    if close_val is not None and float(close_val) > 0:
                        sh = int((nav * w) / float(close_val))
                        holdings[t] = {"shares": sh, "avg_cost": 0.0}
                ps["holdings"] = holdings
            state_path.write_text(_json.dumps(ps, indent=2))
        except Exception:
            pass

    # 13. Print table
    method_name = "HRP + Alpha Tilt" if (use_hrp and not fallback) else "Volatility-Adjusted Alpha Tilt"
    print(f"=== Portfolio Optimizer -- {as_of} ===", flush=True)
    print(f"Method: {method_name}", flush=True)
    print(f"Regime: {regime}  |  Score threshold: {effective_threshold:.3f} (top {(1 - args.top_quantile) * 100:.0f}% quantile, floor={score_floor})", flush=True)
    print("", flush=True)
    print("  Ticker     Score   Vol(EWMA)   HRP Wt   Final Wt", flush=True)
    print("  " + "-" * 56, flush=True)
    for t in sorted(weights.keys(), key=lambda x: -weights[x]):
        sc = scores.get(t)
        vol = vol_30d.get(t)
        hrp_wt = hrp_base_weight.get(t) if (use_hrp and not fallback) else None
        fw = weights[t]
        sc_s = f"{sc:.3f}" if sc is not None else "—"
        vol_s = f"{vol:.3f}" if vol is not None else "—"
        hrp_s = f"{hrp_wt:.1%}" if hrp_wt is not None else "—"
        print(f"  {t:<10} {sc_s:>6}   {vol_s:>7}   {hrp_s:>6}   {fw:.1%}", flush=True)
    total_w = sum(weights.values())
    print("", flush=True)
    print(f"  Total weight: {total_w:.1%}   Positions: {len(weights)}", flush=True)
    ewma_vols_rounded = {t: round(v, 4) for t, v in vol_30d.items()}
    liquidity_caps_rounded = {t: round(c, 2) for t, c in liquidity_cap.items()}
    print(f"[Optimizer] EWMA vols: {ewma_vols_rounded}", flush=True)
    print(f"[Optimizer] Liquidity caps: {liquidity_caps_rounded}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
