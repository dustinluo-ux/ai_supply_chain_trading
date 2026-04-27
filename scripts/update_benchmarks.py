"""
Download SPY, VIX, and SMH OHLCV into DATA_DIR/benchmarks/{ticker}.csv.

Benchmark tickers are excluded from the trading universe (not in data_config
watchlist). They are stored only under benchmarks/ for regime and risk overlays.

Usage:
    python scripts/update_benchmarks.py
    python scripts/update_benchmarks.py --start 2020-01-01
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from update_price_data import download_ticker, merge_dataframes

BENCHMARK_TICKERS = ["SPY", "VIX", "SMH"]


def _yf_symbol(ticker: str) -> str:
    """Map logical benchmark name to yfinance symbol."""
    if ticker == "VIX":
        return "^VIX"
    return ticker


def _benchmarks_dir() -> Path:
    base = os.getenv("DATA_DIR", "C:/ai_supply_chain_trading/trading_data")
    return Path(base) / "benchmarks"


def _benchmark_csv_path(ticker: str) -> Path:
    return _benchmarks_dir() / f"{ticker}.csv"


def _load_existing(csv_path: Path) -> pd.DataFrame | None:
    if not csv_path.exists():
        return None
    try:
        existing_df = pd.read_csv(csv_path, index_col=0, parse_dates=False)
        existing_df.index = pd.to_datetime(
            existing_df.index,
            format="mixed",
            dayfirst=True,
        )
        existing_df.index = pd.to_datetime(
            existing_df.index,
            utc=True,
        ).tz_localize(None)
        return existing_df
    except Exception:
        return None


def _atomic_write_csv(merged: pd.DataFrame, target: Path) -> None:
    """Write CSV via temp file; require non-empty output before rename."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    try:
        merged.to_csv(tmp)
        if not tmp.exists() or tmp.stat().st_size == 0:
            raise ValueError(f"benchmark write empty: {target}")
        probe = pd.read_csv(tmp, index_col=0, nrows=5)
        if probe.empty:
            raise ValueError(f"benchmark csv has no rows: {target}")
        os.replace(tmp, target)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def _refresh_all_benchmarks(
    *,
    start: str,
    end: str,
    delay: float,
    verbose: bool,
) -> tuple[int, int]:
    """Returns (success_count, fail_count)."""
    success = 0
    failed = 0
    n = len(BENCHMARK_TICKERS)
    for i, ticker in enumerate(BENCHMARK_TICKERS):
        sym = _yf_symbol(ticker)
        csv_path = _benchmark_csv_path(ticker)
        tag = "UPDATE" if csv_path.exists() else "NEW"
        try:
            existing_df = _load_existing(csv_path)
            new_df = download_ticker(sym, start, end)
            if new_df is None or new_df.empty:
                msg = f"  [{i + 1}/{n}] SKIP {ticker}: no data from yfinance ({sym})"
                if verbose:
                    print(msg, flush=True)
                else:
                    print(msg, file=sys.stderr, flush=True)
                failed += 1
                continue
            merged = merge_dataframes(existing_df, new_df)
            if merged.empty:
                msg = f"  [{i + 1}/{n}] SKIP {ticker}: merged dataframe empty"
                if verbose:
                    print(msg, flush=True)
                else:
                    print(msg, file=sys.stderr, flush=True)
                failed += 1
                continue
            _atomic_write_csv(merged, csv_path)
            existing_rows = len(existing_df) if existing_df is not None else 0
            if verbose:
                print(
                    f"  [{i + 1}/{n}] {tag} {ticker}: "
                    f"{existing_rows} existing + {len(new_df)} new -> {len(merged)} total "
                    f"({merged.index[0].date()} to {merged.index[-1].date()}) "
                    f"-> benchmarks/{ticker}.csv",
                    flush=True,
                )
            success += 1
        except Exception as e:
            print(
                f"  [{i + 1}/{n}] FAIL {ticker}: {e}",
                file=sys.stderr,
                flush=True,
            )
            failed += 1
        if i < n - 1:
            time.sleep(delay)
    return success, failed


def ensure_benchmarks(
    *,
    start: str = "2015-01-01",
    end: str | None = None,
    delay: float = 1.0,
    verbose: bool = False,
) -> int:
    """Refresh SPY, VIX, and SMH CSVs under DATA_DIR/benchmarks (idempotent merge by date).

    Returns the number of tickers that failed to download or save (0 = all OK).
    """
    end_s = end or datetime.date.today().isoformat()
    if verbose:
        print("Update benchmark CSVs (yfinance)", flush=True)
        print(f"  Data dir: {_benchmarks_dir().parent}", flush=True)
        print(f"  Tickers:  {BENCHMARK_TICKERS}", flush=True)
        print(f"  Period:   {start} to {end_s}", flush=True)
        print(f"  Delay:    {delay}s between downloads", flush=True)
        print("=" * 60, flush=True)
    success, failed = _refresh_all_benchmarks(
        start=start,
        end=end_s,
        delay=delay,
        verbose=verbose,
    )
    if verbose:
        print("=" * 60, flush=True)
        print(
            f"  Done: {success} updated, {failed} failed, {len(BENCHMARK_TICKERS)} total",
            flush=True,
        )
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update SPY/VIX/SMH benchmark CSVs under DATA_DIR/benchmarks",
    )
    parser.add_argument("--start", type=str, default="2015-01-01")
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between downloads (rate-limit courtesy)",
    )
    args = parser.parse_args()
    end_s = args.end or datetime.date.today().isoformat()
    failed = ensure_benchmarks(
        start=args.start,
        end=end_s,
        delay=args.delay,
        verbose=True,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
