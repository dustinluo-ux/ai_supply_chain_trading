"""Verify detected vs actual news date ranges"""
import json
import pandas as pd
from pathlib import Path
from datetime import datetime

print("=" * 60)
print("VERIFYING NEWS DATE RANGE DETECTION")
print("=" * 60)

news_dir = Path("data/news")

# Get first 10 tickers (same as backtest does)
sample_tickers = ['A', 'AA', 'AAL', 'AAN', 'AAON', 'AAPL', 'AAP', 'AAT', 'AAWH', 'AAXN']

print(f"\nChecking {len(sample_tickers)} sample tickers...")

detected_ranges = {}
actual_ranges = {}

for ticker in sample_tickers:
    news_file = news_dir / f"{ticker}_news.json"
    
    if not news_file.exists():
        print(f"\n{ticker}: File does not exist: {news_file}")
        continue
    
    # Load and check actual dates
    try:
        with open(news_file, 'r', encoding='utf-8') as f:
            articles = json.load(f)
        
        if not isinstance(articles, list) or len(articles) == 0:
            print(f"\n{ticker}: No articles or invalid format")
            continue
        
        # Extract actual dates (same logic as backtest)
        dates = []
        for article in articles:
            published_at = article.get('publishedAt', '') or article.get('published_utc', '') or article.get('date', '')
            if published_at:
                try:
                    # Handle space-separated ISO format
                    if 'T' in published_at or 'Z' in published_at or '+' in published_at or (published_at.count(' ') >= 2 and ':' in published_at):
                        date_str = published_at.replace('Z', '+00:00') if published_at.endswith('Z') else published_at
                        article_date = pd.to_datetime(date_str)
                    else:
                        article_date = pd.to_datetime(published_at)
                    if article_date.tzinfo:
                        article_date = article_date.tz_localize(None)
                    dates.append(article_date)
                except Exception as e:
                    pass
        
        if dates:
            actual_start = min(dates)
            actual_end = max(dates)
            actual_ranges[ticker] = (actual_start, actual_end, len(articles))
            
            print(f"\n{ticker}:")
            print(f"  File: {news_file.name}")
            print(f"  File size: {news_file.stat().st_size:,} bytes")
            print(f"  Articles: {len(articles)}")
            print(f"  ACTUAL date range: {actual_start.date()} to {actual_end.date()}")
            print(f"  Date strings (first 3): {[str(d.date()) for d in sorted(set(dates))[:3]]}")
            print(f"  Date strings (last 3): {[str(d.date()) for d in sorted(set(dates))[-3:]]}")
    except Exception as e:
        print(f"\n{ticker}: Error reading file: {e}")
        import traceback
        traceback.print_exc()

# Now simulate what the backtest detection does
print(f"\n" + "=" * 60)
print("SIMULATING BACKTEST DETECTION LOGIC")
print("=" * 60)

news_data_start = None
news_data_end = None

for ticker in sample_tickers:
    if ticker not in actual_ranges:
        continue
    
    actual_start, actual_end, count = actual_ranges[ticker]
    
    # This is what the backtest does
    if news_data_start is None or actual_start < news_data_start:
        news_data_start = actual_start
    if news_data_end is None or actual_end > news_data_end:
        news_data_end = actual_end
    
    print(f"  {ticker}: {actual_start.date()} to {actual_end.date()} ({count} articles)")

if news_data_start and news_data_end:
    print(f"\nDETECTED OVERALL RANGE: {news_data_start.date()} to {news_data_end.date()}")
    print(f"\nThis is what the backtest will use for date alignment!")

# Check specifically for ticker "A"
print(f"\n" + "=" * 60)
print("SPECIFIC CHECK FOR TICKER 'A'")
print("=" * 60)

a_file = news_dir / "A_news.json"
aa_file = news_dir / "AA_news.json"

for ticker, file_path in [("A", a_file), ("AA", aa_file)]:
    if file_path.exists():
        print(f"\n{ticker}_news.json exists:")
        print(f"  Path: {file_path}")
        print(f"  Size: {file_path.stat().st_size:,} bytes")
        print(f"  Modified: {datetime.fromtimestamp(file_path.stat().st_mtime)}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                articles = json.load(f)
            dates = []
            for article in articles:
                pub = article.get('publishedAt', '')
                if pub:
                    try:
                        if 'T' in pub or 'Z' in pub or '+' in pub or (pub.count(' ') >= 2 and ':' in pub):
                            pub = pub.replace('Z', '+00:00') if pub.endswith('Z') else pub
                            dt = pd.to_datetime(pub)
                        else:
                            dt = pd.to_datetime(pub)
                        if dt.tzinfo:
                            dt = dt.tz_localize(None)
                        dates.append(dt)
                    except:
                        pass
            
            if dates:
                print(f"  Articles: {len(articles)}")
                print(f"  Date range: {min(dates).date()} to {max(dates).date()}")
                print(f"  First article title: {articles[0].get('title', '')[:80]}")
            else:
                print(f"  Articles: {len(articles)} but no valid dates")
        except Exception as e:
            print(f"  Error: {e}")
    else:
        print(f"\n{ticker}_news.json does NOT exist")
