"""
Temporary script: Download SPY OHLCV via yfinance and save to data/stock_market_data/sp500/csv/SPY.csv.
Date range: 2015-01-01 to 2023-01-01. Run once to satisfy backtest Kill-Switch and HMM (SPY-based regime).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "stock_market_data" / "sp500" / "csv" / "SPY.csv"


def main() -> int:
    try:
        import yfinance as yf
    except ImportError:
        print("Install yfinance: pip install yfinance", file=sys.stderr)
        return 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading SPY 2015-01-01 to 2023-01-01 -> {OUT_PATH}", flush=True)
    df = yf.download("SPY", start="2015-01-01", end="2023-01-02", progress=True, auto_adjust=False, threads=False)
    if df is None or df.empty:
        print("No data returned from yfinance.", file=sys.stderr)
        return 1
    # Flatten MultiIndex columns if present (e.g. (Close, SPY) -> Close)
    import pandas as pd
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0).astype(str).str.strip()
    df = df.rename(columns={"Adj Close": "Adjusted Close"})
    cols = ["Low", "Open", "Volume", "High", "Close", "Adjusted Close"]
    if "Adjusted Close" not in df.columns:
        df["Adjusted Close"] = df["Close"]
    df = df[[c for c in cols if c in df.columns]]
    df.index.name = "Date"
    df.to_csv(OUT_PATH)
    print(f"Saved {len(df)} rows to {OUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
