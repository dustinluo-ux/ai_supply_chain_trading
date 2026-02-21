"""
Task 6: Standalone daily target-weights script.

Reads tickers from data_config.yaml watchlist, loads prices, calls
compute_target_weights() from target_weight_pipeline (no run_execution).
Outputs CSV: date, ticker, target_weight, latest_close, notional_units
($100,000 notional for display).

Usage:
  python scripts/generate_daily_weights.py [--date YYYY-MM-DD]

Default date = today. Exit 0 on success, 1 on error.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate daily target weights table")
    parser.add_argument("--date", type=str, default=None, help="As-of date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    try:
        from src.data.csv_provider import load_data_config, load_prices
        from src.utils.config_manager import get_config
        from src.core.target_weight_pipeline import compute_target_weights
    except Exception as e:
        print(f"ERROR: Failed to load pipeline: {e}", flush=True)
        return 1

    if args.date:
        try:
            as_of = pd.Timestamp(args.date)
        except Exception as e:
            print(f"ERROR: Invalid --date: {e}", flush=True)
            return 1
    else:
        as_of = pd.Timestamp.utcnow().tz_localize(None).normalize()

    cfg = get_config()
    tickers = cfg.get_watchlist()
    data_cfg = load_data_config()
    data_dir = data_cfg["data_dir"]
    if not data_dir or not Path(data_dir).exists():
        print("ERROR: data_dir from data_config not found.", flush=True)
        return 1

    prices_dict = load_prices(data_dir, tickers)
    if not prices_dict:
        print("ERROR: No price data loaded. Check data_dir and watchlist.", flush=True)
        return 1

    try:
        result = compute_target_weights(
            as_of,
            tickers,
            prices_dict,
            data_dir=data_dir,
            return_aux=True,
        )
        weights_series, aux = result
    except Exception as e:
        print(f"ERROR: compute_target_weights failed: {e}", flush=True)
        return 1

    date_str = as_of.strftime("%Y-%m-%d")
    rows = []
    for ticker in weights_series.index:
        w = float(weights_series.get(ticker, 0.0))
        if ticker not in prices_dict or prices_dict[ticker].empty or "close" not in prices_dict[ticker].columns:
            latest_close = float("nan")
            notional_units = 0
        else:
            close_series = prices_dict[ticker]["close"]
            latest_close = float(close_series.asof(as_of)) if hasattr(close_series, "asof") else float("nan")
            if pd.isna(latest_close) or latest_close <= 0:
                notional_units = 0
            else:
                notional_units = int(w * 100_000 / latest_close)
        rows.append((date_str, ticker, w, latest_close, notional_units))

    # Task 7: append to outputs/daily_signals.csv (header on first run; mode 'a', newline='')
    _out_dir = ROOT / "outputs"
    _out_dir.mkdir(parents=True, exist_ok=True)
    _signals_path = _out_dir / "daily_signals.csv"
    _write_header = not _signals_path.exists() or _signals_path.stat().st_size == 0
    with open(_signals_path, "a", newline="", encoding="utf-8") as _f:
        _writer = csv.writer(_f)
        if _write_header:
            _writer.writerow(["date", "ticker", "target_weight", "latest_close", "notional_units"])
        for _r in rows:
            _writer.writerow(_r)

    # UI: today's snapshot for health table (overwrite each run)
    _scores = aux.get("scores") or {}
    _vol_20d = aux.get("vol_20d") or {}
    _vol_triggered = aux.get("vol_triggered") or {}
    _last_signal = {}
    for _r in rows:
        _date_str, _ticker, _w, _lc, _nu = _r
        _last_signal[_ticker] = {
            "weight": float(_w),
            "latest_close": float(_lc) if not pd.isna(_lc) else None,
            "notional_units": int(_nu),
            "score": _scores.get(_ticker) if _scores.get(_ticker) is not None else None,
            "vol_20d": _vol_20d.get(_ticker) if _ticker in _vol_20d else None,
            "vol_triggered": bool(_vol_triggered.get(_ticker, False)),
        }
    import json
    with open(_out_dir / "last_signal.json", "w", encoding="utf-8") as _jf:
        json.dump(_last_signal, _jf, indent=2)

    writer = csv.writer(sys.stdout)
    writer.writerow(["date", "ticker", "target_weight", "latest_close", "notional_units"])
    for r in rows:
        writer.writerow(r)

    # Task 7: daily signal summary table (scores, vol_20d, vol_triggered from aux)
    _order = list(weights_series.index)
    print(f"\n=== Daily Signal Summary: {date_str} ===", flush=True)
    print(f"{'Ticker':<8} {'Score':>8}   {'Vol_20d':>8}   {'VolFilter':<9}", flush=True)
    print("------  -----   -------   ---------", flush=True)
    for _t in _order:
        _sc = _scores.get(_t)
        _sc_str = f"{_sc:.3f}" if _sc is not None else "N/A"
        _vol = _vol_20d.get(_t)
        _vol_str = "N/A" if _vol is None else f"{_vol:.3f}"
        _trig = "YES" if _vol_triggered.get(_t) else "NO"
        print(f"{_t:<8} {_sc_str:>8}   {_vol_str:>8}   {_trig:<9}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
