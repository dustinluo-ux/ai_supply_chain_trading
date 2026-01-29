"""Diagnose news file coverage across all tickers"""
import json
import os
from collections import Counter
from pathlib import Path
import pandas as pd
import random

print("=" * 60)
print("NEWS COVERAGE DIAGNOSTIC")
print("=" * 60)

news_dir = Path("data/news")

# Check directory
print(f"\n1. Checking directory: {news_dir}")
print(f"   Exists: {news_dir.exists()}")

if not news_dir.exists():
    print("   ERROR: Directory does not exist!")
    exit(1)

# List all files
all_files = list(news_dir.glob("*_news.json"))
print(f"\n2. Total news files found: {len(all_files)}")

if len(all_files) == 0:
    print("   ERROR: No news files found!")
    exit(1)

print(f"   Sample files: {[f.name for f in all_files[:10]]}")

# Sample files for analysis
sample_size = min(100, len(all_files))
sample_files = random.sample(all_files, sample_size)
print(f"\n3. Analyzing {sample_size} random files...")

date_stats = Counter()
ticker_count_by_month = Counter()
ticker_date_ranges = {}
files_with_articles = 0
files_without_articles = 0
files_with_invalid_dates = 0

for filepath in sample_files:
    ticker = filepath.stem.replace('_news', '')
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            articles = json.load(f)
        
        if not isinstance(articles, list):
            files_without_articles += 1
            continue
        
        if len(articles) == 0:
            files_without_articles += 1
            continue
        
        files_with_articles += 1
        dates = []
        
        for article in articles:
            published_at = article.get('publishedAt', '') or article.get('published_utc', '') or article.get('date', '')
            if published_at:
                try:
                    # Parse date
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
                except Exception as e:
                    files_with_invalid_dates += 1
                    pass
        
        if dates:
            ticker_date_ranges[ticker] = {
                'start': min(dates),
                'end': max(dates),
                'count': len(articles)
            }
            # Count tickers per month
            start_month = min(dates).replace(day=1)
            end_month = max(dates).replace(day=1)
            months = pd.date_range(start_month, end_month, freq='MS')
            for month in months:
                month_key = month.strftime('%Y-%m')
                ticker_count_by_month[month_key] += 1
    
    except Exception as e:
        print(f"   Error reading {filepath.name}: {e}")
        files_without_articles += 1

print(f"\n4. File Statistics:")
print(f"   Files with articles: {files_with_articles}")
print(f"   Files without articles: {files_with_invalid_dates}")
print(f"   Files with invalid dates: {files_with_invalid_dates}")

print(f"\n5. Article Date Distribution (from {sample_size} sample files):")
print(f"   Total articles analyzed: {sum(date_stats.values())}")
if date_stats:
    print(f"   Top 10 months by article count:")
    for month, count in date_stats.most_common(10):
        print(f"     {month}: {count} articles")

print(f"\n6. Ticker Coverage by Month (from {sample_size} sample files):")
print(f"   Tickers with date ranges: {len(ticker_date_ranges)}")
if ticker_count_by_month:
    print(f"   Top 10 months by ticker count:")
    for month, count in ticker_count_by_month.most_common(10):
        print(f"     {month}: {count} tickers")

# Now check ALL files for October 2022 specifically
print(f"\n7. Checking ALL files for October 2022 coverage...")
oct_2022_tickers = []
target_month = "2022-10"

for filepath in all_files:
    ticker = filepath.stem.replace('_news', '')
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            articles = json.load(f)
        
        if not isinstance(articles, list) or len(articles) == 0:
            continue
        
        has_oct_2022 = False
        for article in articles:
            published_at = article.get('publishedAt', '') or article.get('published_utc', '') or article.get('date', '')
            if published_at and target_month in published_at:
                has_oct_2022 = True
                break
        
        if has_oct_2022:
            oct_2022_tickers.append(ticker)
    
    except Exception as e:
        pass

print(f"   Tickers with October 2022 articles: {len(oct_2022_tickers)}")
if len(oct_2022_tickers) <= 20:
    print(f"   Tickers: {oct_2022_tickers}")
else:
    print(f"   First 20 tickers: {oct_2022_tickers[:20]}")

# Check what year has most coverage
print(f"\n8. Year Distribution:")
year_stats = Counter()
for month, count in date_stats.items():
    year = month[:4]
    year_stats[year] += count

print(f"   Articles by year:")
for year, count in sorted(year_stats.items()):
    print(f"     {year}: {count} articles")

# Check detection logic
print(f"\n9. Simulating Detection Logic:")
print(f"   All tickers from prices_dict would be: (simulating with sample)")
print(f"   Tickers with date ranges found: {len(ticker_date_ranges)}")
if ticker_date_ranges:
    print(f"   Sample date ranges:")
    for ticker in list(ticker_date_ranges.keys())[:10]:
        ranges = ticker_date_ranges[ticker]
        print(f"     {ticker}: {ranges['start'].date()} to {ranges['end'].date()} ({ranges['count']} articles)")
