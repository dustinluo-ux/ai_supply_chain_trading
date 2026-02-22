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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _main() -> int:
    parser = argparse.ArgumentParser(description="Volatility-Adjusted Alpha Tilt optimizer.")
    parser.add_argument("--top-quantile", type=float, default=0.75, help="Quantile cutoff — e.g. 0.75 = top 25%% of scored tickers eligible")
    parser.add_argument("--score-floor", type=float, default=0.50, help="Hard minimum score — no ticker with score <= floor is eligible")
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

    # 5a. Regime detection — SPY 200-day SMA gate
    import numpy as np
    regime = "UNKNOWN"
    score_floor = args.score_floor
    try:
        spy_dict = load_prices(data_dir, ["SPY"])
        if spy_dict and "SPY" in spy_dict:
            spy_df = spy_dict["SPY"]
            if "close" in spy_df.columns and len(spy_df) >= 200:
                close_series = spy_df["close"]
                # Handle duplicate columns (EODHD global issue)
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

    # 5. 30-day rolling vol per ticker
    vol_window = max(1, args.vol_window)
    vol_30d = {}
    for ticker, df in prices_dict.items():
        if df is None or df.empty or "close" not in df.columns:
            continue
        try:
            returns = df["close"].pct_change(fill_method=None).dropna()
            if len(returns) < vol_window:
                continue
            vol = float(returns.iloc[-vol_window:].std())
            if vol is None or vol != vol or vol <= 0:
                continue
            vol_30d[ticker] = vol
        except Exception:
            continue

    # 6. Eligible: score > effective_threshold (top quantile, with floor) and valid vol
    top_quantile = args.top_quantile
    # score_floor already set by regime detection (5a) — do not overwrite
    score_threshold = float(np.quantile(list(scores.values()), top_quantile))
    effective_threshold = max(score_threshold, score_floor)
    eligible = [t for t in scores if t in vol_30d and scores[t] > effective_threshold]

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
        # 8. Raw weights: score / vol
        raw_w = {t: scores[t] / vol_30d[t] for t in eligible}
        total_raw = sum(raw_w.values())
        if total_raw <= 0:
            eligible = []
            fallback = True
            top3 = sorted(scores.keys(), key=lambda t: scores[t], reverse=True)[:3]
            weights = {t: 1.0 / 3.0 for t in top3} if top3 else {}
            metadata = {t: {"score": scores[t], "vol_30d": vol_30d.get(t), "raw_weight": 1.0 / 3.0} for t in top3} if top3 else {}
        else:
            # 9. Normalize
            w = {t: raw_w[t] / total_raw for t in eligible}
            # 10. Iterative cap at max_weight
            max_weight = max(1e-9, min(1.0, args.max_weight))
            while True:
                capped = {t for t in w if w[t] > max_weight}
                uncapped = {t for t in w if w[t] <= max_weight}
                if not capped:
                    break
                excess = sum(w[t] - max_weight for t in capped)
                for t in capped:
                    w[t] = max_weight
                if uncapped:
                    total_uncapped = sum(w[t] for t in uncapped)
                    for t in uncapped:
                        w[t] += excess * (w[t] / total_uncapped)
                else:
                    break
            weights = w
            metadata = {t: {"score": scores[t], "vol_30d": vol_30d[t], "raw_weight": raw_w[t]} for t in eligible}

    # 11. Write last_valid_weights.json
    out_dir = ROOT / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    valid_path = out_dir / "last_valid_weights.json"
    with open(valid_path, "w", encoding="utf-8") as f:
        json.dump({"as_of": as_of, "weights": weights}, f, indent=2)

    # 12. Write last_optimized_weights.json
    optimized = {
        "as_of": as_of,
        "method": "volatility_adjusted_alpha_tilt",
        "regime": regime,
        "params": {"top_quantile": args.top_quantile, "score_floor": score_floor, "max_weight": args.max_weight, "vol_window": args.vol_window},
        "weights": weights,
        "metadata": metadata,
    }
    opt_path = out_dir / "last_optimized_weights.json"
    with open(opt_path, "w", encoding="utf-8") as f:
        json.dump(optimized, f, indent=2)

    # 13. Print table
    print(f"=== Portfolio Optimizer -- {as_of} ===", flush=True)
    print("Method: Volatility-Adjusted Alpha Tilt", flush=True)
    print(f"Regime: {regime}  |  Score threshold: {effective_threshold:.3f} (top {(1 - args.top_quantile) * 100:.0f}% quantile, floor={score_floor})", flush=True)
    print("", flush=True)
    print("  Ticker     Score   Vol(30d)   Raw Wt   Final Wt", flush=True)
    print("  " + "-" * 52, flush=True)
    for t in sorted(weights.keys(), key=lambda x: -weights[x]):
        sc = scores.get(t)
        vol = vol_30d.get(t)
        rw = metadata.get(t, {}).get("raw_weight") if not fallback else (1.0 / 3.0)
        fw = weights[t]
        sc_s = f"{sc:.3f}" if sc is not None else "—"
        vol_s = f"{vol:.3f}" if vol is not None else "—"
        rw_s = f"{rw:.2f}" if rw is not None else "—"
        print(f"  {t:<10} {sc_s:>6}   {vol_s:>7}   {rw_s:>6}   {fw:.1%}", flush=True)
    total_w = sum(weights.values())
    print("", flush=True)
    print(f"  Total weight: {total_w:.1%}   Positions: {len(weights)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
