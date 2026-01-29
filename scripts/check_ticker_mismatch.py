"""Check why only 7 tickers are detected - investigate ticker mismatch"""
import json
from pathlib import Path
from collections import Counter
import pandas as pd

print("=" * 60)
print("TICKER MISMATCH INVESTIGATION")
print("=" * 60)

news_dir = Path("data/news")

# Get all news file tickers
all_news_files = list(news_dir.glob("*_news.json"))
news_tickers = [f.stem.replace('_news', '') for f in all_news_files]
print(f"\n1. Total news files: {len(news_tickers)}")
print(f"   Sample news tickers: {news_tickers[:20]}")

# Check what tickers have Oct 2022 coverage
print(f"\n2. Checking ALL news files for October 2022 coverage...")
oct_2022_tickers = []
oct_2022_counts = Counter()

for filepath in all_news_files:
    ticker = filepath.stem.replace('_news', '')
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            articles = json.load(f)
        
        if not isinstance(articles, list) or len(articles) == 0:
            continue
        
        oct_count = 0
        for article in articles:
            published_at = article.get('publishedAt', '')
            if published_at and '2022-10' in published_at:
                oct_count += 1
        
        if oct_count > 0:
            oct_2022_tickers.append(ticker)
            oct_2022_counts[ticker] = oct_count
    
    except Exception as e:
        pass

print(f"   Tickers with October 2022 articles: {len(oct_2022_tickers)}")
print(f"   First 20: {oct_2022_tickers[:20]}")

# Check what the detection logic would see
print(f"\n3. Simulating detection logic...")
print(f"   The detection uses: all_tickers = list(prices_dict.keys())")
print(f"   This means it only checks tickers that have PRICE data loaded")
print(f"   If prices_dict only has 7 tickers, only 7 will be checked!")

# Check best month across ALL news files
print(f"\n4. Finding best month across ALL news files...")
month_coverage = Counter()

for filepath in all_news_files[:500]:  # Check first 500 for speed
    ticker = filepath.stem.replace('_news', '')
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            articles = json.load(f)
        
        if not isinstance(articles, list) or len(articles) == 0:
            continue
        
        dates = []
        for article in articles[:5]:  # First 5 articles
            published_at = article.get('publishedAt', '')
            if published_at:
                try:
                    if 'T' in published_at or 'Z' in published_at or '+' in published_at or (published_at.count(' ') >= 2 and ':' in published_at):
                        date_str = published_at.replace('Z', '+00:00') if published_at.endswith('Z') else published_at
                        article_date = pd.to_datetime(date_str)
                    else:
                        article_date = pd.to_datetime(published_at)
                    if article_date.tzinfo:
                        article_date = article_date.tz_localize(None)
                    dates.append(article_date)
                except:
                    pass
        
        if dates:
            start_month = min(dates).replace(day=1)
            end_month = max(dates).replace(day=1)
            months = pd.date_range(start_month, end_month, freq='MS')
            for month in months:
                month_key = month.strftime('%Y-%m')
                month_coverage[month_key] += 1
    
    except Exception:
        pass

if month_coverage:
    print(f"   Top 10 months by ticker count (from 500 files):")
    for month, count in month_coverage.most_common(10):
        print(f"     {month}: {count} tickers")
    
    best_month = month_coverage.most_common(1)[0]
    print(f"\n   BEST MONTH: {best_month[0]} with {best_month[1]} tickers")

print(f"\n5. CONCLUSION:")
print(f"   The detection only checks tickers in prices_dict.keys()")
print(f"   If DEBUG_MODE is on, it might only load a few tickers")
print(f"   Or if TICKERS list is filtered, only those tickers are checked")
print(f"   Solution: Check ALL news files, not just tickers with price data")
