"""
Test News Loading - Debug news file structure and date filtering
"""
import json
import os
from pathlib import Path
from datetime import datetime

ticker = "A"
news_file = Path(f"data/news/{ticker}_news.json")

print("=" * 60)
print("NEWS FILE STRUCTURE TEST")
print("=" * 60)
print(f"\nTesting news file: {news_file}")
print(f"Exists: {news_file.exists()}")

if news_file.exists():
    with open(news_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"\nFile structure:")
    print(f"  Type: {type(data)}")
    print(f"  Is list: {isinstance(data, list)}")
    print(f"  Is dict: {isinstance(data, dict)}")
    
    if isinstance(data, dict):
        print(f"  Keys: {list(data.keys())}")
        if 'articles' in data:
            articles = data['articles']
            print(f"  Articles list length: {len(articles)}")
        else:
            print(f"  No 'articles' key found")
            articles = []
    elif isinstance(data, list):
        articles = data
        print(f"  Direct list, length: {len(articles)}")
    else:
        articles = []
        print(f"  Unknown structure")
    
    if articles:
        first = articles[0]
        print(f"\nFirst article structure:")
        print(f"  Keys: {list(first.keys())}")
        print(f"  publishedAt: {first.get('publishedAt', 'N/A')}")
        print(f"  title: {first.get('title', 'N/A')[:100] if first.get('title') else 'N/A'}")
        
        # Check date range
        dates = []
        for article in articles:
            pub_date = article.get('publishedAt', '') or article.get('published_utc', '') or article.get('date', '')
            if pub_date:
                try:
                    if 'T' in pub_date or 'Z' in pub_date:
                        dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                    else:
                        dt = datetime.strptime(pub_date, "%Y-%m-%d")
                    dates.append(dt)
                except:
                    pass
        
        if dates:
            print(f"\nDate range in file:")
            print(f"  Min: {min(dates)}")
            print(f"  Max: {max(dates)}")
            print(f"  2021 articles: {sum(1 for d in dates if d.year == 2021)}")
            print(f"  2022 articles: {sum(1 for d in dates if d.year == 2022)}")
            print(f"  2023 articles: {sum(1 for d in dates if d.year == 2023)}")
        
        # Test date filtering
        print(f"\nTesting date filtering:")
        test_start = "2022-09-01"
        test_end = "2022-12-31"
        start_dt = datetime.strptime(test_start, "%Y-%m-%d")
        end_dt = datetime.strptime(test_end, "%Y-%m-%d")
        
        filtered = []
        for article in articles:
            pub_date = article.get('publishedAt', '') or article.get('published_utc', '') or article.get('date', '')
            if not pub_date:
                continue
            try:
                if 'T' in pub_date or 'Z' in pub_date:
                    article_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                else:
                    article_date = datetime.strptime(pub_date, "%Y-%m-%d")
                if article_date.tzinfo:
                    article_date = article_date.replace(tzinfo=None)
                if start_dt <= article_date <= end_dt:
                    filtered.append(article)
            except Exception as e:
                pass
        
        print(f"  Articles in range {test_start} to {test_end}: {len(filtered)}")
        if len(filtered) == 0 and dates:
            print(f"  [WARNING] No articles match! Date range issue?")
            print(f"  Requested: {start_dt.date()} to {end_dt.date()}")
            print(f"  Available: {min(dates).date()} to {max(dates).date()}")
else:
    print(f"\n[ERROR] News file does not exist!")

print("\n" + "=" * 60)
