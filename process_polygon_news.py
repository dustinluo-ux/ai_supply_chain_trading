"""
Process Polygon news dataset and convert to standard news format
Loads polygon_news_sample.json and converts to Marketaux-compatible format
"""
import json
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Paths - try multiple possible locations
possible_paths = [
    Path("C:/Users/dusro/Downloads/poly/polygon_news_sample.json"),
    Path("/mnt/user-data/uploads/polygon_news_sample.json"),
    Path("polygon_news_sample.json"),
    Path("../Downloads/poly/polygon_news_sample.json"),
]

POLYGON_FILE = None
for path in possible_paths:
    if path.exists():
        POLYGON_FILE = path
        break

if POLYGON_FILE is None:
    # Try to find it in Downloads directory
    downloads_dir = Path.home() / "Downloads"
    polygon_path = downloads_dir / "poly" / "polygon_news_sample.json"
    if polygon_path.exists():
        POLYGON_FILE = polygon_path

OUTPUT_DIR = Path("data/news")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("PROCESSING POLYGON NEWS DATA")
print("=" * 60)

# Load Polygon news data
if POLYGON_FILE is None:
    print("❌ ERROR: polygon_news_sample.json not found in any of these locations:")
    for path in possible_paths:
        print(f"   - {path}")
    print("\nPlease specify the correct path in the script or place the file in one of the above locations.")
    exit(1)

print(f"\n[1/4] Loading Polygon news from: {POLYGON_FILE}", flush=True)

try:
    with open(POLYGON_FILE, 'r', encoding='utf-8') as f:
        polygon_articles = json.load(f)
    print(f"✓ Loaded {len(polygon_articles)} articles")
except Exception as e:
    print(f"❌ Error loading file: {e}")
    exit(1)

# Group articles by ticker
print("\n[2/4] Grouping articles by ticker...", flush=True)
articles_by_ticker = defaultdict(list)
tickers_seen = set()

for article in polygon_articles:
    # Extract tickers from article
    tickers = article.get('tickers', [])
    if not tickers:
        continue
    
    # Extract date
    published_utc = article.get('published_utc', '')
    if not published_utc:
        continue
    
    # Convert to standard format for each ticker
    standardized = {
        'title': article.get('title', ''),
        'description': article.get('description', ''),
        'content': article.get('description', ''),  # Use description as content
        'url': article.get('article_url', ''),
        'publishedAt': published_utc,  # Already in ISO format
        'source': article.get('publisher', {}).get('name', 'Polygon'),
        'ticker': '',  # Will be set per ticker
        'fetched_at': datetime.now().isoformat(),
        # Polygon-specific fields
        'author': article.get('author', ''),
        'keywords': article.get('keywords', []),
        'insights': article.get('insights', []),  # Contains sentiment per ticker
        'publisher': article.get('publisher', {})
    }
    
    # Add to each ticker's list
    for ticker in tickers:
        if ticker:  # Skip empty tickers
            ticker_article = standardized.copy()
            ticker_article['ticker'] = ticker
            
            # Extract sentiment for this specific ticker from insights
            ticker_sentiment = None
            for insight in article.get('insights', []):
                if insight.get('ticker') == ticker:
                    ticker_sentiment = {
                        'sentiment': insight.get('sentiment', 'neutral'),
                        'sentiment_reasoning': insight.get('sentiment_reasoning', '')
                    }
                    break
            
            if ticker_sentiment:
                ticker_article['sentiment'] = ticker_sentiment['sentiment']
                ticker_article['sentiment_reasoning'] = ticker_sentiment['sentiment_reasoning']
            
            articles_by_ticker[ticker].append(ticker_article)
            tickers_seen.add(ticker)

print(f"✓ Found articles for {len(tickers_seen)} unique tickers")
print(f"  Total article-ticker pairs: {sum(len(articles) for articles in articles_by_ticker.values())}")

# Filter to 2023 only
print("\n[3/4] Filtering to 2023 articles only...", flush=True)
articles_2023_by_ticker = defaultdict(list)
for ticker, articles in articles_by_ticker.items():
    for article in articles:
        published_at = article.get('publishedAt', '')
        if published_at and published_at.startswith('2023'):
            articles_2023_by_ticker[ticker].append(article)

print(f"✓ 2023 articles for {len(articles_2023_by_ticker)} tickers")
total_2023 = sum(len(articles) for articles in articles_2023_by_ticker.values())
print(f"  Total 2023 article-ticker pairs: {total_2023}")

# Save in Marketaux-compatible format (per ticker JSON files)
print("\n[4/4] Saving articles to data/news/...", flush=True)
saved_count = 0
for ticker, articles in articles_2023_by_ticker.items():
    if not articles:
        continue
    
    # Sort by date
    articles.sort(key=lambda x: x.get('publishedAt', ''))
    
    # Save to {ticker}_news.json (same format as Marketaux/other sources)
    output_file = OUTPUT_DIR / f"{ticker}_news.json"
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(articles, f, indent=2, ensure_ascii=False)
        saved_count += 1
        if saved_count % 10 == 0:
            print(f"  ✓ Saved {saved_count} tickers...", flush=True)
    except Exception as e:
        print(f"  ✗ Error saving {ticker}: {e}", flush=True)

print(f"\n✓ Saved articles for {saved_count} tickers")
print(f"  Output directory: {OUTPUT_DIR}")

# Summary
print("\n" + "=" * 60)
print("PROCESSING COMPLETE")
print("=" * 60)
print(f"Total articles processed: {len(polygon_articles)}")
print(f"Unique tickers: {len(tickers_seen)}")
print(f"2023 articles: {total_2023}")
print(f"Tickers with 2023 data: {len(articles_2023_by_ticker)}")
print(f"Files saved: {saved_count}")
print("=" * 60)
print("\n✅ Polygon news data converted to standard format!")
print("   Files saved to: data/news/{ticker}_news.json")
print("   Ready to use with existing news processing pipeline.")
