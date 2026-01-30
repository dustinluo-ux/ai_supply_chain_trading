"""
Generate minimal SPY placeholder CSV when yfinance is unavailable (e.g. proxy).
Uses 2015-01-02 to 2022-12-30 with synthetic OHLCV so backtest has SPY for Kill-Switch and HMM.
Replace with real data (run download_spy_yfinance.py with network) when possible.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "stock_market_data" / "sp500" / "csv" / "SPY.csv"


def main() -> int:
    import numpy as np
    import pandas as pd

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2015-01-02", "2022-12-30", freq="B")
    n = len(dates)
    np.random.seed(42)
    # Rough SPY-like levels: start ~200, end ~380 (2022 drawdown in between)
    trend = np.linspace(200, 380, n)
    noise = np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(trend + noise, 150)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) * (1 + np.abs(np.random.randn(n) * 0.005))
    low = np.minimum(open_, close) * (1 - np.abs(np.random.randn(n) * 0.005))
    volume = (100_000_000 + np.random.rand(n) * 50_000_000).astype(int)
    adj = close  # no adjustment for placeholder
    df = pd.DataFrame({
        "Low": low, "Open": open_, "Volume": volume, "High": high, "Close": close, "Adjusted Close": adj,
    }, index=dates)
    df.index.name = "Date"
    df.to_csv(OUT_PATH)
    print(f"Wrote placeholder SPY ({n} rows) to {OUT_PATH}. Replace with real data when possible.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
