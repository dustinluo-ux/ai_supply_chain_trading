"""
Update Price CSVs — config-driven yfinance downloader.

Reads the watchlist from data_config.yaml, downloads OHLCV via yfinance,
and merges with existing CSVs (deduplicates by date). Always includes SPY
for kill-switch and HMM regime detection.

Reuse origin:
  - graveyard/scripts/download_spy_yfinance.py (MultiIndex handling, CSV format)
  - graveyard/download_simple.py (download loop pattern)

Usage:
    python scripts/update_price_data.py                     # defaults from YAML
    python scripts/update_price_data.py --start 2023-01-01  # override start
    python scripts/update_price_data.py --tickers NVDA,AMD  # override watchlist
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.csv_provider import CSV_SUBDIRS, find_csv_path, load_data_config

DEFAULT_SUBDIR = "nasdaq/csv"
REQUIRED_TICKERS = ["SPY"]


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex columns produced by yfinance >= 0.2."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0).astype(str).str.strip()
    return df


def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure canonical column order: Date, Low, Open, Volume, High, Close, Adjusted Close."""
    df = _flatten_columns(df)
    if "Adj Close" in df.columns:
        df = df.rename(columns={"Adj Close": "Adjusted Close"})
    if "Adjusted Close" not in df.columns and "Close" in df.columns:
        df["Adjusted Close"] = df["Close"]
    canonical = ["Low", "Open", "Volume", "High", "Close", "Adjusted Close"]
    present = [c for c in canonical if c in df.columns]
    df = df[present]
    df.index.name = "Date"
    return df


def download_ticker(
    ticker: str,
    start: str,
    end: str,
) -> pd.DataFrame | None:
    """Download OHLCV for a single ticker via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: pip install yfinance", file=sys.stderr)
        sys.exit(1)

    df = yf.download(
        ticker,
        start=start,
        end=end,
        progress=False,
        auto_adjust=False,
        threads=False,
    )
    if df is None or df.empty:
        return None
    return _standardize(df)


def merge_dataframes(
    existing: pd.DataFrame | None,
    new: pd.DataFrame,
) -> pd.DataFrame:
    """Merge new data with existing, deduplicating by date index."""
    if existing is None or existing.empty:
        return new
    combined = pd.concat([existing, new])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined.sort_index()
    return combined


def resolve_csv_path(
    data_dir: Path,
    ticker: str,
) -> Path:
    """Find existing CSV or create a default path."""
    existing = find_csv_path(data_dir, ticker)
    if existing is not None:
        return existing
    # Default: data_dir / nasdaq/csv / {TICKER}.csv
    default = data_dir / DEFAULT_SUBDIR / f"{ticker}.csv"
    return default


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update price CSVs from yfinance using data_config.yaml",
    )
    parser.add_argument(
        "--tickers", type=str, default=None,
        help="Comma-separated tickers (default: watchlist from data_config.yaml + SPY)",
    )
    parser.add_argument("--start", type=str, default="2015-01-01")
    parser.add_argument("--end", type=str, default="2025-01-01")
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds between downloads (rate-limit courtesy)",
    )
    args = parser.parse_args()

    # Resolve tickers
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        from src.utils.config_manager import get_config
        tickers = get_config().get_watchlist()

    # Always include required tickers (SPY for kill-switch/regime)
    for req in REQUIRED_TICKERS:
        if req not in tickers:
            tickers.append(req)

    config = load_data_config()
    data_dir = config["data_dir"]

    print(f"Update Price Data (yfinance)", flush=True)
    print(f"  Data dir: {data_dir}", flush=True)
    print(f"  Tickers:  {tickers}", flush=True)
    print(f"  Period:   {args.start} to {args.end}", flush=True)
    print(f"  Delay:    {args.delay}s between downloads", flush=True)
    print("=" * 60, flush=True)

    success = 0
    failed = 0
    for i, ticker in enumerate(tickers, 1):
        csv_path = resolve_csv_path(data_dir, ticker)
        tag = "UPDATE" if csv_path.exists() else "NEW"

        # Load existing data if present
        existing_df = None
        if csv_path.exists():
            try:
                existing_df = pd.read_csv(
                    csv_path, index_col=0, parse_dates=True, dayfirst=True,
                )
                existing_df.index = pd.to_datetime(
                    existing_df.index, utc=True,
                ).tz_localize(None)
            except Exception as e:
                print(
                    f"  [{i}/{len(tickers)}] WARN: Could not read existing {ticker}: {e}",
                    flush=True,
                )
                existing_df = None

        # Download new data
        new_df = download_ticker(ticker, args.start, args.end)
        if new_df is None:
            print(
                f"  [{i}/{len(tickers)}] SKIP {ticker} -- no data from yfinance",
                flush=True,
            )
            failed += 1
            continue

        # Merge
        merged = merge_dataframes(existing_df, new_df)

        # Save
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(csv_path)

        existing_rows = len(existing_df) if existing_df is not None else 0
        print(
            f"  [{i}/{len(tickers)}] {tag} {ticker}: "
            f"{existing_rows} existing + {len(new_df)} new -> {len(merged)} total "
            f"({merged.index[0].date()} to {merged.index[-1].date()}) "
            f"-> {csv_path.relative_to(data_dir)}",
            flush=True,
        )
        success += 1

        if i < len(tickers):
            time.sleep(args.delay)

    print("=" * 60, flush=True)
    print(
        f"  Done: {success} updated, {failed} failed, {len(tickers)} total",
        flush=True,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
