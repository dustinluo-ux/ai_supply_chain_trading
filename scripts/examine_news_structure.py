"""Examine news data directory structure and show sample articles"""
import json
import os
from pathlib import Path
from datetime import datetime

print("=" * 60)
print("NEWS DATA DIRECTORY STRUCTURE")
print("=" * 60)

# Show directory structure
project_root = Path.cwd()
data_dir = project_root / "data"
news_dir = data_dir / "news"
raw_dir = data_dir / "raw"

print(f"\nProject root: {project_root}")
print(f"\nDirectory structure:")
print(f"  {project_root}/")
print(f"  +-- data/")
print(f"      +-- news/           <- Backtest reads from HERE")
print(f"      |   +-- *_news.json")
print(f"      +-- raw/            <- Original fnspid CSV")
print(f"      |   +-- fnspid_nasdaq_news.csv")
print(f"      +-- stock_market_data/")

print(f"\n" + "=" * 60)
print("BACKTEST NEWS PATH")
print("=" * 60)

# Exact path from backtest code
news_dir_path = "data/news"
ticker = "A"
news_file_path = f"{news_dir_path}/{ticker}_news.json"

print(f"\nBacktest code uses:")
print(f"  news_dir = Path('{news_dir_path}')")
print(f"  news_file = news_dir / f'{{ticker}}_news.json'")
print(f"\nFull path: {Path(news_file_path).absolute()}")

print(f"\n" + "=" * 60)
print("FILES IN NEWS DIRECTORY")
print("=" * 60)

news_path = Path(news_dir_path)
if news_path.exists():
    json_files = sorted([f.name for f in news_path.glob("*.json") if f.name.endswith("_news.json")])
    print(f"\nNews files directory: {news_path.absolute()}")
    print(f"Total *_news.json files: {len(json_files)}")
    print(f"\nFirst 10 files:")
    for f in json_files[:10]:
        print(f"  {f}")
    print(f"\nLast 5 files:")
    for f in json_files[-5:]:
        print(f"  {f}")
else:
    print(f"ERROR: Directory does not exist: {news_path.absolute()}")

print(f"\n" + "=" * 60)
print("A_news.json DATE RANGE AND SAMPLE")
print("=" * 60)

news_file = Path(news_file_path)
if news_file.exists():
    print(f"\nFile: {news_file.absolute()}")
    print(f"File size: {news_file.stat().st_size:,} bytes")
    
    with open(news_file, 'r', encoding='utf-8') as f:
        articles = json.load(f)
    
    print(f"Total articles: {len(articles)}")
    
    if len(articles) > 0:
        # Extract dates
        dates = []
        for article in articles:
            pub_date = article.get('publishedAt', '')
            if pub_date:
                dates.append(pub_date)
        
        if dates:
            print(f"\nDate range: {min(dates)} to {max(dates)}")
        
        # Show first article
        first_article = articles[0]
        print(f"\nFirst article:")
        print(f"  Keys: {list(first_article.keys())}")
        print(f"  Title: {first_article.get('title', '')[:100]}")
        print(f"  Description: {first_article.get('description', '')[:150]}")
        print(f"  Content (first 200 chars): {first_article.get('content', '')[:200]}")
        print(f"  PublishedAt: {first_article.get('publishedAt', '')}")
        
        # Show a few more articles
        print(f"\n" + "-" * 60)
        print("Sample of first 3 articles:")
        print("-" * 60)
        for i, article in enumerate(articles[:3], 1):
            print(f"\nArticle {i}:")
            print(f"  Title: {article.get('title', '')[:80]}")
            print(f"  PublishedAt: {article.get('publishedAt', '')}")
            print(f"  Content length: {len(article.get('content', ''))} chars")
else:
    print(f"\nERROR: File does not exist: {news_file.absolute()}")

print(f"\n" + "=" * 60)
print("DELETED FILES LOCATION")
print("=" * 60)
print(f"\nThe files that were deleted were in:")
print(f"  {news_path.absolute()}")
print(f"\nThey were deleted with command:")
print(f"  Remove-Item data\\news\\*_news.json -Force")
print(f"\nIf you need to recover them, check:")
print(f"  1. Recycle Bin")
print(f"  2. OneDrive version history (if synced)")
print(f"  3. Git history (if committed)")
