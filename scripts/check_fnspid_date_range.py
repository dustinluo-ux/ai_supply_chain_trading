"""
Check date range in raw FNSPID CSV (without loading the whole file).
Samples first N and last N rows to report min/max date - use to see if
FNSPID has Apr 2022 or earlier data we didn't process.

Usage:
  python scripts/check_fnspid_date_range.py [path_to_fnspid.csv]
  Default path: data/raw/fnspid_nasdaq_news.csv
  Or use cache path from: python scripts/find_cache_path.py
"""
import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parent.parent
default_path = project_root / "data" / "raw" / "fnspid_nasdaq_news.csv"

def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path
    if not path.exists():
        print(f"File not found: {path}")
        print("Usage: python scripts/check_fnspid_date_range.py [path_to_fnspid.csv]")
        print("  Or put fnspid CSV at data/raw/fnspid_nasdaq_news.csv")
        print("  To find cache: python scripts/find_cache_path.py")
        return

    # Detect date column
    sample = pd.read_csv(path, nrows=5, low_memory=False)
    date_col = None
    for c in ["Date", "date", "publishedAt", "published_at", "publish_date", "timestamp"]:
        if c in sample.columns:
            date_col = c
            break
    if not date_col:
        print(f"Date column not found. Columns: {list(sample.columns)}")
        return

    print(f"Reading date column: '{date_col}'")
    print("Sampling first 100k rows...")

    # Sample first 100k rows (FNSPID is often chronological or by ticker - this gives start of data)
    n_sample = 100_000
    df = pd.read_csv(path, nrows=n_sample, low_memory=False, usecols=[date_col])
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])
    sample_min = df[date_col].min()
    sample_max = df[date_col].max()

    print(f"\nSampled first {n_sample:,} rows.")
    print(f"Date range in sample: {sample_min} to {sample_max}")
    global_min, global_max = sample_min, sample_max

    try:
        if global_min.year <= 2022 and global_min.month <= 4:
            print("  -> FNSPID has data before/into Apr 2022. Re-run process_fnspid with --date-start 2022-04-01 to get 9 months.")
        elif global_min.year == 2022 and global_min.month >= 10:
            print("  -> FNSPID sample starts Oct 2022 or later. File may be ordered by date; check full file or use alternative source for Apr-Sep 2022.")
    except Exception:
        pass
    print("Done.")

if __name__ == "__main__":
    main()
