"""Test the field mapping fix"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.process_fnspid import convert_to_our_format
import pandas as pd

# Load one article from CSV
df = pd.read_csv('data/raw/fnspid_nasdaq_news.csv', nrows=1)
article = df.iloc[0].to_dict()

print("Raw article keys:", list(article.keys()))
print("\nRaw article sample:")
print(f"  Article_title: {str(article.get('Article_title', 'N/A'))[:150]}")
print(f"  Article (first 200 chars): {str(article.get('Article', 'N/A'))[:200]}")
print(f"  Date: {article.get('Date', 'N/A')}")
print(f"  Lsa_summary (first 150 chars): {str(article.get('Lsa_summary', 'N/A'))[:150]}")

# Convert
result = convert_to_our_format(article)

print("\n" + "="*60)
print("CONVERTED RESULT:")
print("="*60)
print(f"title: {result['title'][:150]}")
print(f"\ndescription: {result['description'][:150]}")
print(f"\ncontent (first 300 chars): {result['content'][:300]}")
print(f"\npublishedAt: {result['publishedAt']}")

# Check if fields are populated
print("\n" + "="*60)
print("VALIDATION:")
print("="*60)
print(f"title empty: {not result['title']}")
print(f"description empty: {not result['description']}")
print(f"content empty: {not result['content']}")
print(f"publishedAt empty: {not result['publishedAt']}")
