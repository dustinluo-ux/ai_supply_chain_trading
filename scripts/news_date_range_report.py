"""
Report date range of news for ALL data/news/*.json files.
Use to see what we currently have and whether we have earlier 2022 articles.
"""
import json
from pathlib import Path
from collections import Counter
import pandas as pd

news_dir = Path(__file__).resolve().parent.parent / "data" / "news"
if not news_dir.exists():
    print(f"ERROR: {news_dir} not found")
    exit(1)

files = list(news_dir.glob("*_news.json"))
print(f"Scanning {len(files)} news files in {news_dir}...")

# Full scan: date range per ticker
ticker_ranges = {}
month_article_count = Counter()
month_ticker_count = Counter()

for path in files:
    ticker = path.stem.replace("_news", "")
    try:
        with open(path, "r", encoding="utf-8") as f:
            articles = json.load(f)
    except Exception as e:
        print(f"  Skip {ticker}: {e}")
        continue
    if not isinstance(articles, list) or not articles:
        continue
    dates = []
    for a in articles:
        pub = a.get("publishedAt") or a.get("published_utc") or a.get("date") or ""
        if not pub:
            continue
        try:
            if "T" in pub or "Z" in pub or "+" in pub or (pub.count(" ") >= 2 and ":" in pub):
                dt = pd.to_datetime(pub.replace("Z", "+00:00"))
            else:
                dt = pd.to_datetime(pub)
            if dt.tzinfo:
                dt = dt.tz_localize(None)
            dates.append(dt)
            month_article_count[dt.strftime("%Y-%m")] += 1
        except Exception:
            pass
    if dates:
        start, end = min(dates), max(dates)
        ticker_ranges[ticker] = {"start": start, "end": end, "count": len(articles)}
        for m in pd.date_range(start.replace(day=1), end.replace(day=1), freq="MS"):
            month_ticker_count[m.strftime("%Y-%m")] += 1

# Report
print("\n" + "=" * 60)
print("NEWS DATE RANGE REPORT (all data/news/*.json)")
print("=" * 60)
print(f"Tickers with news: {len(ticker_ranges)}")

# Overall min/max
if ticker_ranges:
    all_starts = [r["start"] for r in ticker_ranges.values()]
    all_ends = [r["end"] for r in ticker_ranges.values()]
    print(f"Overall date range: {min(all_starts).date()} to {max(all_ends).date()}")

# Key universe tickers (supply chain top)
key_tickers = ["NVDA", "TSM", "AMD", "AMAT", "INTC", "AAPL", "MSFT", "MU", "QCOM"]
print("\n--- Date range for key universe tickers ---")
for t in key_tickers:
    if t in ticker_ranges:
        r = ticker_ranges[t]
        print(f"  {t}: {r['start'].date()} to {r['end'].date()}  ({r['count']} articles)")
    else:
        print(f"  {t}: (no news file)")

# Sample of tickers with earliest start (do we have Apr 2022?)
sorted_by_start = sorted(ticker_ranges.items(), key=lambda x: x[1]["start"])
print("\n--- 15 tickers with EARLIEST news start ---")
for t, r in sorted_by_start[:15]:
    print(f"  {t}: {r['start'].date()} to {r['end'].date()}  ({r['count']} articles)")

# Articles by month
print("\n--- Article count by month (all tickers) ---")
for month in sorted(month_article_count.keys()):
    print(f"  {month}: {month_article_count[month]:,} articles")

# Tickers with coverage in Apr 2022
apr_2022 = "2022-04"
tickers_with_apr_2022 = [
    t for t, r in ticker_ranges.items()
    if r["start"] <= pd.Timestamp(apr_2022 + "-30") and r["end"] >= pd.Timestamp(apr_2022 + "-01")
]
print(f"\n--- Tickers with news in {apr_2022} (start<=Apr 30, end>=Apr 1): {len(tickers_with_apr_2022)} ---")
if len(tickers_with_apr_2022) <= 30:
    print(f"  {sorted(tickers_with_apr_2022)}")
else:
    print(f"  (first 30) {sorted(tickers_with_apr_2022)[:30]}")

# Apr-Dec 2022 coverage
print("\n--- Months in 2022 with any articles ---")
for m in sorted(month_article_count.keys()):
    if m.startswith("2022"):
        print(f"  {m}: {month_article_count[m]:,} articles, {month_ticker_count.get(m, 0)} tickers")

print("\n" + "=" * 60)
