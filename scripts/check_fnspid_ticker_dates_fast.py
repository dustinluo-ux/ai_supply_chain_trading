"""Fast check: first N rows of FNSPID for NVDA/AMD/TSM/AAPL date range."""
import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parent.parent
default_path = project_root / "data" / "raw" / "fnspid_nasdaq_news.csv"
TARGET = {"NVDA", "AMD", "TSM", "AAPL"}
NROWS = 150_000  # fast

def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path
    if not path.exists():
        print(f"File not found: {path}")
        return 1
    sample = pd.read_csv(path, nrows=5, low_memory=False)
    date_col = "Date" if "Date" in sample.columns else "date"
    title_col = "Article_title" if "Article_title" in sample.columns else ("headline" if "headline" in sample.columns else None)
    ticker_col = "ticker" if "ticker" in sample.columns else ("symbol" if "symbol" in sample.columns else None)
    usecols = [date_col]
    if ticker_col and ticker_col in sample.columns:
        usecols.append(ticker_col)
    if title_col and title_col in sample.columns:
        usecols.append(title_col)
    print(f"Reading first {NROWS:,} rows (cols: {usecols})...")
    df = pd.read_csv(path, nrows=NROWS, low_memory=False, usecols=usecols)
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])
    stats = {t: {"min": None, "max": None, "count": 0} for t in TARGET}
    if ticker_col:
        ticker_ser = df[ticker_col].astype(str).str.upper().str.strip().str.replace(r"[^A-Z0-9]", "", regex=True)
    for t in TARGET:
        if ticker_col:
            mask = ticker_ser == t
        elif title_col:
            mask = df[title_col].astype(str).str.contains(f"({t})", regex=False)
        else:
            continue
        sub = df.loc[mask, date_col]
        if sub.empty:
            continue
        stats[t]["count"] = len(sub)
        stats[t]["min"] = sub.min()
        stats[t]["max"] = sub.max()
    print("\n" + "=" * 60)
    print("FNSPID (first {} rows): date range for NVDA/AMD/TSM/AAPL".format(NROWS))
    print("=" * 60)
    for t in sorted(TARGET):
        s = stats[t]
        if s["count"] == 0:
            print(f"  {t}: NOT FOUND in first {NROWS:,} rows")
            continue
        mn_str = str(s["min"])[:10]  # YYYY-MM-DD
        before = "YES (before Oct 2022)" if mn_str < "2022-10" else "NO (Oct 2022 or later only)"
        min_d = str(s["min"])[:10]
        max_d = str(s["max"])[:10]
        print(f"  {t}: earliest={min_d}, latest={max_d}, count={s['count']:,}  -> {before}")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
