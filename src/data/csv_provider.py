"""
Canonical CSV data loading for the backtest and execution pipelines.

Provides the 4 shared functions for price data ingestion:
- load_data_config: Read data_config.yaml and return data directory path
- find_csv_path: Locate a ticker's CSV across subdirectories
- load_prices: Bulk-load price DataFrames for a list of tickers
- ensure_ohlcv: Guarantee OHLCV columns exist on a DataFrame

Source: lifted from scripts/backtest_technical_library.py (L33-86) to centralize.
Subdirectory search order per ARCHITECTURE.md: nasdaq/csv, sp500/csv, nyse/csv, forbes2000/csv.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import os

# Project root: src/data/csv_provider.py -> src/data -> src -> project_root
_ROOT = Path(__file__).resolve().parent.parent.parent

# Subdirectory search order (ARCHITECTURE.md § "Price Data Ingestion")
CSV_SUBDIRS = ["nasdaq/csv", "sp500/csv", "nyse/csv", "forbes2000/csv"]


def load_data_config() -> dict:
    """
    Read config/data_config.yaml and return {"data_dir": Path}.
    Falls back to {PROJECT_ROOT}/data/stock_market_data if config missing.
    """
    path = _ROOT / "config" / "data_config.yaml"
    if not path.exists():
        return {"data_dir": _ROOT / "data" / "stock_market_data"}
    from src.utils.defensive import safe_read_yaml
    data = safe_read_yaml(str(path))
    ds = data.get("data_sources", {})
    data_dir = Path(ds.get("data_dir", str(_ROOT / "data" / "stock_market_data")))
    return {"data_dir": data_dir}


def find_csv_path(base_dir, ticker):
    """
    Searches recursively for ticker.csv within the stock_market_data subdirectories.
    When multiple copies exist (e.g. different datasets), returns the path whose
    CSV has the latest end date (last index value), so backtests get the longest
    coverage. Uses same read as load_prices: index_col=0, parse_dates=False then index via pd.to_datetime(..., format='mixed', dayfirst=True).
    """
    ticker_clean = ticker.replace('.csv', '').upper()
    target_file = f"{ticker_clean}.csv"
    candidates: list[str] = []
    for root, dirs, files in os.walk(str(base_dir)):
        for f in files:
            if f.upper() == target_file.upper():
                candidates.append(os.path.join(root, f))
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    best_path: str | None = None
    best_max: pd.Timestamp | None = None
    for path in candidates:
        try:
            df = pd.read_csv(path, index_col=0, parse_dates=False)
            df.index = pd.to_datetime(df.index, format="mixed", dayfirst=True)
            if df.empty or df.index is None:
                continue
            last = df.index.max()
            if best_max is None or last > best_max:
                best_max = last
                best_path = path
        except Exception:
            continue
    return best_path


def load_prices(data_dir: Path, tickers: list[str]) -> dict[str, pd.DataFrame]:
    """
    Bulk-load price CSVs.  Returns {ticker: DataFrame} with OHLCV columns,
    tz-naive datetime index, and >=60 rows.
    """
    out = {}
    for t in tickers:
        path = find_csv_path(data_dir, t)
        if not path:
            print(f"  [WARN] No CSV for {t}", flush=True)
            continue
        try:
            df = pd.read_csv(path, index_col=0, parse_dates=False)
            df.index = pd.to_datetime(df.index, format="mixed", dayfirst=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
            df.columns = [c.lower() for c in df.columns]
            if "close" not in df.columns:
                continue
            for c in ["open", "high", "low"]:
                if c not in df.columns:
                    df[c] = df["close"]
            if "volume" not in df.columns:
                df["volume"] = 0.0
            if df.empty or len(df) < 60:
                continue
            out[t] = df
        except Exception as e:
            print(f"  [WARN] Load {t}: {e}", flush=True)
    return out


def ensure_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Guarantee OHLCV columns on a DataFrame.
    Missing open/high/low default from close; missing volume defaults to 0.
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    for c in ["open", "high", "low"]:
        if c not in df.columns and "close" in df.columns:
            df[c] = df["close"]
    if "volume" not in df.columns:
        df["volume"] = 0.0
    return df
