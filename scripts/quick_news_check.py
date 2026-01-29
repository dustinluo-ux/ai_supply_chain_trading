"""Quick check of news file coverage - optimized"""
import json
from pathlib import Path
from collections import Counter
import pandas as pd

print("=" * 60)
print("QUICK NEWS COVERAGE CHECK")
print("=" * 60)

news_dir = Path("data/news")

# Count total files
all_files = list(news_dir.glob("*_news.json"))
print(f"\n1. Total news files: {len(all_files)}")

# Check first 50 files for date distribution
print(f"\n2. Checking first 50 files for date distribution...")

date_stats = Counter()
year_stats = Counter()
ticker_count_by_month = Counter()
files_checked = 0

for filepath in all_files[:50]:
    files_checked += 1
    ticker = filepath.stem.replace('_news', '')
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            articles = json.load(f)
        
        if not isinstance(articles, list) or len(articles) == 0:
            continue
        
        dates = []
        for article in articles[:10]:  # Only check first 10 articles per file
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
                    month = article_date.strftime('%Y-%m')
                    date_stats[month] += 1
                    year = article_date.strftime('%Y')
                    year_stats[year] += 1
                except:
                    pass
        
        if dates:
            start_month = min(dates).replace(day=1)
            end_month = max(dates).replace(day=1)
            months = pd.date_range(start_month, end_month, freq='MS')
            for month in months:
                month_key = month.strftime('%Y-%m')
                ticker_count_by_month[month_key] += 1
    
    except Exception as e:
        pass

print(f"   Files checked: {files_checked}")
print(f"   Articles analyzed: {sum(date_stats.values())}")

print(f"\n3. Year Distribution (from sample):")
for year, count in sorted(year_stats.items()):
    print(f"   {year}: {count} articles")

print(f"\n4. Top 10 Months by Article Count:")
for month, count in date_stats.most_common(10):
    print(f"   {month}: {count} articles")

print(f"\n5. Top 10 Months by Ticker Count:")
for month, count in ticker_count_by_month.most_common(10):
    print(f"   {month}: {count} tickers")

# Check what tickers are in the universe
print(f"\n6. Checking which tickers the backtest would use...")
try:
    from src.data.universe_loader import UniverseLoader
    loader = UniverseLoader()
    all_tickers = loader.get_tickers()
    print(f"   Total tickers in universe: {len(all_tickers)}")
    print(f"   First 20: {all_tickers[:20]}")
    
    # Check how many have news files
    tickers_with_news = [t for t in all_tickers if (news_dir / f"{t}_news.json").exists()]
    print(f"   Tickers with news files: {len(tickers_with_news)}")
    print(f"   First 20 with news: {tickers_with_news[:20]}")
except Exception as e:
    print(f"   Could not load universe: {e}")

# Quick check for Oct 2022 in first 100 files
print(f"\n7. Quick check for October 2022 in first 100 files...")
oct_2022_count = 0
for filepath in all_files[:100]:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            articles = json.load(f)
        if isinstance(articles, list):
            for article in articles[:5]:  # Check first 5 articles
                pub = article.get('publishedAt', '')
                if pub and '2022-10' in pub:
                    oct_2022_count += 1
                    break
    except:
        pass

print(f"   Files with Oct 2022 articles (first 100 files): {oct_2022_count}")
