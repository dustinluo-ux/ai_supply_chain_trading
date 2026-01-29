"""Verify that news JSON files contain actual content"""
import json
from pathlib import Path

news_file = Path('data/news/A_news.json')

print("=" * 60)
print("VERIFYING A_news.json CONTENT")
print("=" * 60)

if not news_file.exists():
    print(f"ERROR: File does not exist: {news_file}")
    exit(1)

print(f"\nFile exists: {news_file.exists()}")
print(f"File size: {news_file.stat().st_size:,} bytes")

# Load and inspect
with open(news_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total articles: {len(data)}")

if len(data) == 0:
    print("ERROR: No articles in file!")
    exit(1)

# Check first article
article = data[0]
print(f"\nFirst article keys: {list(article.keys())}")

title = article.get('title', '')
description = article.get('description', '')
content = article.get('content', '')
publishedAt = article.get('publishedAt', '')

print(f"\nTitle (length {len(title)}): '{title[:150]}'")
print(f"\nDescription (length {len(description)}): '{description[:150]}'")
print(f"\nContent (length {len(content)}): '{content[:300]}'")
print(f"\nPublishedAt: '{publishedAt}'")

# Validation
print("\n" + "=" * 60)
print("VALIDATION:")
print("=" * 60)

title_empty = not title or title.strip() == ''
description_empty = not description or description.strip() == ''
content_empty = not content or content.strip() == ''
publishedAt_empty = not publishedAt or publishedAt.strip() == ''

print(f"Title empty: {title_empty}")
print(f"Description empty: {description_empty}")
print(f"Content empty: {content_empty}")
print(f"PublishedAt empty: {publishedAt_empty}")

if title_empty or content_empty:
    print("\n[FAILED] Title or content is empty!")
    exit(1)
else:
    print("\n[SUCCESS] All fields contain actual text content!")
