"""
Check raw FNSPID CSV for earliest/latest article dates for universe tickers
(NVDA, AMD, TSM, AAPL). Answers: Does FNSPID have these tickers before Oct 2022?

Usage:
  python scripts/check_fnspid_ticker_dates.py <path_to_fnspid.csv>
  python scripts/check_fnspid_ticker_dates.py   # uses data/raw/fnspid_nasdaq_news.csv

Reads in chunks; uses ticker/symbol column if present, else extracts from Article_title/headline.
"""
import re
import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parent.parent
default_path = project_root / "data" / "raw" / "fnspid_nasdaq_news.csv"

TARGET_TICKERS = {"NVDA", "AMD", "TSM", "AAPL"}
OCT_2022 = pd.Timestamp("2022-10-01")
MAX_CHUNKS = 20  # 20 * 50k = 1M rows (sample; usecols speeds up)


def get_ticker(row, ticker_col, title_col):
    """Get ticker from row: column if present, else extract from title."""
    if ticker_col and ticker_col in row.index:
        val = row.get(ticker_col)
        if pd.notna(val) and str(val).strip():
            t = str(val).upper().strip()
            t = "".join(c for c in t if c.isalnum())
            if 1 <= len(t) <= 10:
                return t
    if title_col and title_col in row.index:
        title = str(row.get(title_col, ""))
        # Match (NVDA), (AMD), (TSM), (AAPL) or standalone
        for sym in TARGET_TICKERS:
            if f"({sym})" in title or f"[{sym}]" in title:
                return sym
        m = re.search(r"\(([A-Z]{2,5})\)", title)
        if m and m.group(1) in TARGET_TICKERS:
            return m.group(1)
    return None


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path
    if not path.exists():
        print(f"File not found: {path}")
        print("Usage: python scripts/check_fnspid_ticker_dates.py [path_to_fnspid.csv]")
        print("  Find path: python scripts/find_cache_path.py")
        return 1

    # Detect columns
    sample = pd.read_csv(path, nrows=5, low_memory=False)
    date_col = None
    for c in ["Date", "date", "publishedAt", "published_at"]:
        if c in sample.columns:
            date_col = c
            break
    ticker_col = None
    for c in ["ticker", "symbol", "stock", "Ticker", "Symbol"]:
        if c in sample.columns:
            ticker_col = c
            break
    title_col = None
    for c in ["Article_title", "article_title", "headline", "title", "Headline"]:
        if c in sample.columns:
            title_col = c
            break
    if not date_col:
        print("Date column not found. Columns:", list(sample.columns))
        return 1
    print(f"Using date col: {date_col}, ticker col: {ticker_col}, title col: {title_col}")
    print(f"Target tickers: {TARGET_TICKERS}")
    print(f"Reading up to {MAX_CHUNKS} chunks (50k rows each)...")

    usecols = [date_col]
    if ticker_col:
        usecols.append(ticker_col)
    if title_col:
        usecols.append(title_col)
    usecols = [c for c in usecols if c in sample.columns]

    # Per-ticker: min_date, max_date, count (vectorized)
    stats = {t: {"min": None, "max": None, "count": 0} for t in TARGET_TICKERS}
    chunk_size = 50_000
    total_rows = 0

    for chunk_num, chunk in enumerate(
        pd.read_csv(path, chunksize=chunk_size, low_memory=False, usecols=usecols), 1
    ):
        if chunk_num > MAX_CHUNKS:
            break
        total_rows += len(chunk)
        chunk[date_col] = pd.to_datetime(chunk[date_col], errors="coerce")
        chunk = chunk.dropna(subset=[date_col])
        if chunk.empty:
            continue
        # Build mask per target ticker
        if ticker_col and ticker_col in chunk.columns:
            ticker_ser = chunk[ticker_col].astype(str).str.upper().str.strip()
            ticker_ser = ticker_ser.str.replace(r"[^A-Z0-9]", "", regex=True)
        else:
            ticker_ser = None

        for t in TARGET_TICKERS:
            if ticker_ser is not None:
                mask = ticker_ser == t
            elif title_col and title_col in chunk.columns:
                title = chunk[title_col].astype(str)
                mask = title.str.contains(f"({t})", regex=False) | title.str.contains(f"[{t}]", regex=False)
            else:
                continue
            sub = chunk.loc[mask, date_col]
            if sub.empty:
                continue
            stats[t]["count"] += len(sub)
            mn, mx = sub.min(), sub.max()
            if stats[t]["min"] is None or mn < stats[t]["min"]:
                stats[t]["min"] = mn
            if stats[t]["max"] is None or mx > stats[t]["max"]:
                stats[t]["max"] = mx

        if chunk_num % 10 == 0:
            print(f"  Chunk {chunk_num}: {total_rows:,} rows scanned")

    print("\n" + "=" * 60)
    print("FNSPID RAW FILE: Date range for universe tickers")
    print("=" * 60)
    print(f"Rows scanned: {total_rows:,}\n")

    has_before_oct = False
    for t in sorted(TARGET_TICKERS):
        s = stats[t]
        if s["count"] == 0:
            print(f"  {t}: NO ARTICLES FOUND in scanned rows")
            continue
        print(f"  {t}: earliest={s['min'].date()}, latest={s['max'].date()}, count={s['count']:,}")
        if s["min"] < OCT_2022:
            has_before_oct = True
            print(f"       -> HAS data before Oct 2022 (can re-process for Apr-Dec 2022)")
        else:
            print(f"       -> Only Oct 2022 or later in this sample")

    print("\n" + "=" * 60)
    if has_before_oct:
        print("CONCLUSION: FNSPID has Apr-Sep 2022 data for at least one universe ticker.")
        print("  -> Re-process: python scripts/process_fnspid.py --date-start 2022-04-01 --date-end 2022-12-31 --input <path>")
    else:
        print("CONCLUSION: In scanned rows, no universe ticker had articles before Oct 2022.")
        print("  -> FNSPID may only have Oct+ 2022 for these tickers; consider Polygon/Tiingo for Apr-Sep 2022.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
