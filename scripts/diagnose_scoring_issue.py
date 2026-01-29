"""
Diagnostic script to investigate why non-AI companies score high in supply chain ranking.
Shows actual scores, sample news headlines, and keyword matches.
"""
import pandas as pd
import json
from pathlib import Path

# Load scores
df = pd.read_csv('data/supply_chain_mentions.csv')

# Problem stocks
problem_stocks = ['ACLS', 'AAL', 'AEM', 'A', 'ADM']

print("=" * 80)
print("SUPPLY CHAIN SCORING DIAGNOSIS")
print("=" * 80)

print("\n1. ACTUAL SCORES FOR PROBLEM STOCKS:")
print("-" * 80)
problem_df = df[df['ticker'].isin(problem_stocks)].sort_values('supply_chain_score', ascending=False)
print(problem_df[['ticker', 'supply_chain_score', 'ai_related_count', 'total_articles', 
                  'supplier_mentions', 'customer_mentions', 'avg_relevance_score', 
                  'positive_sentiment_count']].to_string(index=False))

print("\n2. KEY FINDINGS:")
print("-" * 80)
for _, row in problem_df.iterrows():
    ticker = row['ticker']
    score = row['supply_chain_score']
    ai_count = row['ai_related_count']
    total = row['total_articles']
    supplier = row['supplier_mentions']
    customer = row['customer_mentions']
    
    print(f"\n{ticker}:")
    print(f"  Score: {score:.4f}")
    print(f"  AI-related articles: {ai_count}/{total} ({ai_count/total*100:.1f}%)")
    print(f"  Supplier mentions: {supplier} (FinBERT can't extract - always 0)")
    print(f"  Customer mentions: {customer} (FinBERT can't extract - always 0)")
    print(f"  Problem: High 'ai_related_count' but no actual AI supply chain relationships!")

print("\n3. SAMPLE NEWS HEADLINES:")
print("-" * 80)

# Check sample news for each problem stock
for ticker in problem_stocks:
    news_file = Path(f'data/news/{ticker}_news.json')
    if news_file.exists():
        try:
            with open(news_file, 'r', encoding='utf-8') as f:
                articles = json.load(f)
            
            print(f"\n{ticker} - Sample headlines (first 5):")
            for i, article in enumerate(articles[:5], 1):
                title = article.get('title', 'N/A')
                desc = article.get('description', '')[:100] if article.get('description') else ''
                print(f"  {i}. {title}")
                if desc:
                    print(f"     {desc}...")
                
                # Check for keyword matches
                text_lower = f"{title} {desc}".lower()
                keywords = ['ai', 'artificial intelligence', 'gpu', 'semiconductor', 'datacenter', 'supply chain']
                matches = [kw for kw in keywords if kw in text_lower]
                if matches:
                    print(f"     [KEYWORD MATCHES: {', '.join(matches)}]")
        except Exception as e:
            print(f"  Error loading {ticker} news: {e}")

print("\n4. SCORING FORMULA BREAKDOWN:")
print("-" * 80)
print("""
Current formula (from supply_chain_scanner.py):
  score = (
      ai_score * 0.4 +           # ai_related_count / 10.0 (capped at 1.0)
      mention_score * 0.3 +      # (supplier*0.4 + customer*0.3 + product*0.3) / total
      relevance_weight * 0.2 +   # avg_relevance_score (keyword-based)
      sentiment_ratio * 0.1      # positive_sentiment_count / total_sentiment
  )

PROBLEM: mention_score is ALWAYS 0 because FinBERT returns supplier=None, customer=None, product=None
So the score is effectively:
  score = ai_score * 0.4 + relevance * 0.2 + sentiment * 0.1
  (30% of weight is lost!)

And "supply chain" keyword matches generic logistics news, not AI supply chain.
""")

print("\n5. RECOMMENDED FIX:")
print("-" * 80)
print("""
Option 1: Switch to Gemini (RECOMMENDED)
  - Gemini can actually extract supplier/customer relationships
  - Can distinguish AI supply chain from generic supply chain
  - mention_score will be non-zero

Option 2: Improve keyword matching
  - Remove generic "supply chain" keyword
  - Require AI-specific context: "AI supply chain", "datacenter supply chain"
  - Require multiple keywords (not just one)

Option 3: Add minimum threshold
  - Require supplier_mentions > 0 OR customer_mentions > 0
  - This would require Gemini (FinBERT can't extract this)
""")

print("\n" + "=" * 80)
