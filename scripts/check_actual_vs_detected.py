"""Check actual vs detected date ranges"""
import json
import pandas as pd
from pathlib import Path

print("=" * 60)
print("ACTUAL VS DETECTED DATE RANGE COMPARISON")
print("=" * 60)

news_dir = Path("data/news")
ticker = "A"
news_file = news_dir / f"{ticker}_news.json"

print(f"\nChecking ticker: {ticker}")
print(f"File: {news_file}")

if news_file.exists():
    with open(news_file, 'r', encoding='utf-8') as f:
        articles = json.load(f)
    
    print(f"Total articles: {len(articles)}")
    
    # Extract actual dates
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
        actual_min = min(dates)
        actual_max = max(dates)
        print(f"\nACTUAL date range in file: {actual_min.date()} to {actual_max.date()}")
        print(f"Unique dates: {len(set([d.date() for d in dates]))}")
        
        # Show date distribution
        date_counts = {}
        for d in dates:
            date_str = str(d.date())
            date_counts[date_str] = date_counts.get(date_str, 0) + 1
        
        print(f"\nDate distribution (first 10 dates):")
        for date_str in sorted(date_counts.keys())[:10]:
            print(f"  {date_str}: {date_counts[date_str]} articles")
        
        print(f"\nDate distribution (last 10 dates):")
        for date_str in sorted(date_counts.keys())[-10:]:
            print(f"  {date_str}: {date_counts[date_str]} articles")
        
        # Check if Nov 1-29 range exists
        nov_dates = [d for d in dates if d.month == 11 and d.year == 2022]
        if nov_dates:
            print(f"\nNovember 2022 articles: {len(nov_dates)}")
            print(f"  Range: {min(nov_dates).date()} to {max(nov_dates).date()}")
        else:
            print(f"\nNovember 2022 articles: 0 (NONE!)")
else:
    print(f"File does not exist!")
