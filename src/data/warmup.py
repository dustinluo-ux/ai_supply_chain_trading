"""
Warm-Up and Self-Healing data layer.

Bridges historical store (data/prices/ parquet) with the last N days of "Recent" data
from yfinance (or Tiingo when configured), and appends new bars to historical after live fetch.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

from src.utils.logger import setup_logger

logger = setup_logger()


# Default historical store: same as PriceFetcher (data/prices = historical for price)
DEFAULT_HISTORICAL_DIR = "data/prices"
DEFAULT_WARMUP_DAYS = 30


def load_historical(
    tickers: List[str],
    start_date: str,
    end_date: str,
    data_dir: str = DEFAULT_HISTORICAL_DIR,
) -> Dict[str, pd.DataFrame]:
    """
    Load historical OHLCV from local store (parquet per ticker).

    Args:
        tickers: List of ticker symbols.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        data_dir: Directory containing {ticker}.parquet files.

    Returns:
        Dict ticker -> DataFrame with index=datetime, columns including open, high, low, close, volume.
    """
    os.makedirs(data_dir, exist_ok=True)
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    result = {}

    for ticker in tickers:
        path = os.path.join(data_dir, f"{ticker}.parquet")
        if not os.path.exists(path):
            logger.debug(f"No historical file for {ticker} at {path}")
            continue
        try:
            df = pd.read_parquet(path)
            if not isinstance(df.index, pd.DatetimeIndex) and "date" in df.columns:
                df = df.set_index("date")
            if not isinstance(df.index, pd.DatetimeIndex):
                continue
            df = df[(df.index >= start_dt) & (df.index <= end_dt)]
            if not df.empty:
                result[ticker] = df.sort_index()
        except Exception as e:
            logger.warning(f"Error loading historical {ticker}: {e}")
    return result


def fetch_recent_yfinance(
    tickers: List[str],
    last_n_days: int = DEFAULT_WARMUP_DAYS,
) -> Dict[str, pd.DataFrame]:
    """
    Fetch last N calendar days of OHLCV from yfinance (Recent bridge).

    Args:
        tickers: List of ticker symbols.
        last_n_days: Number of calendar days to fetch.

    Returns:
        Dict ticker -> DataFrame with standard OHLCV columns.
    """
    if yf is None:
        logger.warning("yfinance not installed; cannot fetch recent data")
        return {}

    end = datetime.now()
    start = end - timedelta(days=last_n_days)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    result = {}

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(start=start_str, end=end_str, interval="1d")
            if df.empty:
                continue
            df.columns = [c.lower() for c in df.columns]
            required = ["open", "high", "low", "close", "volume"]
            if not all(c in df.columns for c in required):
                continue
            df["ticker"] = ticker
            result[ticker] = df[["ticker"] + required].sort_index()
        except Exception as e:
            logger.debug(f"fetch_recent_yfinance {ticker}: {e}")
    return result


def merge_historical_recent(
    historical: Dict[str, pd.DataFrame],
    recent: Dict[str, pd.DataFrame],
    tickers: Optional[List[str]] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Merge historical and recent DataFrames per ticker; drop duplicate dates, sort index.

    Args:
        historical: Dict ticker -> DataFrame (from load_historical).
        recent: Dict ticker -> DataFrame (from fetch_recent_yfinance).
        tickers: If provided, only merge these tickers; else all keys in historical or recent.

    Returns:
        Dict ticker -> merged DataFrame.
    """
    all_tickers = set(historical.keys()) | set(recent.keys())
    if tickers is not None:
        all_tickers = all_tickers & set(tickers)
    result = {}

    for ticker in all_tickers:
        hist_df = historical.get(ticker)
        rec_df = recent.get(ticker)

        if hist_df is None and rec_df is None:
            continue
        if hist_df is None:
            result[ticker] = rec_df.sort_index()
            continue
        if rec_df is None:
            result[ticker] = hist_df.sort_index()
            continue

        # Align columns (ensure both have same cols)
        cols = [c for c in hist_df.columns if c in rec_df.columns]
        if not cols:
            result[ticker] = hist_df.sort_index()
            continue
        h = hist_df[cols].copy()
        r = rec_df[cols].copy()
        combined = pd.concat([h, r], axis=0)
        combined = combined[~combined.index.duplicated(keep="last")]
        combined = combined.sort_index()
        result[ticker] = combined
    return result


def warm_up(
    tickers: List[str],
    start_date: str,
    end_date: str,
    last_n_days: int = DEFAULT_WARMUP_DAYS,
    data_dir: str = DEFAULT_HISTORICAL_DIR,
    use_recent: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Warm-Up: load historical from data_dir, optionally fetch last_n_days from yfinance, merge.

    Returns one merged DataFrame per ticker with no gap between historical and recent.

    Args:
        tickers: Ticker symbols.
        start_date: Start date for historical load.
        end_date: End date for historical load.
        last_n_days: Days of Recent to fetch (only if use_recent=True).
        data_dir: Historical store (data/prices).
        use_recent: If True, fetch last_n_days from yfinance and merge.

    Returns:
        Dict ticker -> merged DataFrame.
    """
    historical = load_historical(tickers, start_date, end_date, data_dir)
    if not use_recent or yf is None:
        return historical
    recent = fetch_recent_yfinance(tickers, last_n_days=last_n_days)
    return merge_historical_recent(historical, recent, tickers)


def heal_append(
    ticker: str,
    new_bars: pd.DataFrame,
    data_dir: str = DEFAULT_HISTORICAL_DIR,
) -> bool:
    """
    Self-Healing: append new_bars to existing historical parquet for ticker (no duplicate dates).

    Args:
        ticker: Ticker symbol.
        new_bars: DataFrame with index=date and OHLCV columns (e.g. from a live fetch).
        data_dir: Directory containing {ticker}.parquet.

    Returns:
        True if append/save succeeded.
    """
    if new_bars.empty:
        return True
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, f"{ticker}.parquet")

    if not isinstance(new_bars.index, pd.DatetimeIndex):
        if "date" in new_bars.columns:
            new_bars = new_bars.set_index("date")
        else:
            logger.warning("heal_append: new_bars must have DatetimeIndex or 'date' column")
            return False

    existing = None
    if os.path.exists(path):
        try:
            existing = pd.read_parquet(path)
            if "date" in existing.columns and "date" not in existing.index.name:
                existing = existing.set_index("date")
        except Exception as e:
            logger.warning(f"heal_append: could not read existing {path}: {e}")

    if existing is not None and not existing.empty:
        common_cols = [c for c in new_bars.columns if c in existing.columns]
        if common_cols:
            combined = pd.concat([existing[common_cols], new_bars[common_cols]], axis=0)
            combined = combined[~combined.index.duplicated(keep="last")]
            combined = combined.sort_index()
        else:
            combined = new_bars
    else:
        combined = new_bars.sort_index()

    try:
        combined.to_parquet(path)
        logger.info(f"heal_append: saved {ticker} to {path} ({len(combined)} rows)")
        return True
    except Exception as e:
        logger.error(f"heal_append: failed to save {ticker}: {e}")
        return False
