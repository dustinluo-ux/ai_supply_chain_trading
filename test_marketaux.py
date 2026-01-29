"""
Test script to verify Marketaux API returns historical news data (2023-2024)
Tests if free tier actually provides historical data access
"""
import os
from dotenv import load_dotenv
from src.data.news_sources.marketaux_source import MarketauxSource

# Load environment variables
load_dotenv()

print("=" * 60)
print("MARKETAUX HISTORICAL DATA TEST")
print("=" * 60)

# Check if API key exists
api_key = os.getenv("MARKETAUX_API_KEY")
if not api_key:
    print("❌ ERROR: MARKETAUX_API_KEY not found in .env file")
    print("   Add: MARKETAUX_API_KEY=your_key_here")
    exit(1)

print(f"✓ API key found: {api_key[:10]}...{api_key[-4:]}")
print()

# Initialize Marketaux source
try:
    print("Initializing MarketauxSource...", flush=True)
    source = MarketauxSource(data_dir="data/news", keywords=None)
    print("✓ MarketauxSource initialized")
    print()
except Exception as e:
    print(f"❌ Error initializing MarketauxSource: {e}")
    exit(1)

# Test: Fetch articles for NVDA from January 2023
ticker = "NVDA"
start_date = "2023-01-01"
end_date = "2023-01-31"

print(f"Fetching articles for {ticker} from {start_date} to {end_date}...")
print("(This may take a moment due to rate limiting)", flush=True)
print()

try:
    articles = source.fetch_articles_for_ticker(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        use_cache=False  # Don't use cache for testing
    )
    
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Number of articles returned: {len(articles)}")
    print()
    
    if len(articles) == 0:
        print("⚠️  WARNING: No articles returned!")
        print()
        print("This could mean:")
        print("  1. Free tier doesn't provide historical data")
        print("  2. Rate limit reached (100 requests/day)")
        print("  3. No articles available for this date range")
        print("  4. API error (check logs above)")
        print()
        print("To debug, check the API response in the logs above.")
        print("You can also test with a more recent date range.")
    else:
        print("✓ SUCCESS: Historical data is available!")
        print()
        print("First article:")
        first = articles[0]
        print(f"  Date: {first.get('publishedAt', 'N/A')}")
        print(f"  Title: {first.get('title', 'N/A')[:80]}...")
        print(f"  Source: {first.get('source', 'N/A')}")
        print(f"  URL: {first.get('url', 'N/A')[:80]}...")
        print()
        
        if len(articles) > 1:
            print(f"Sample of {min(3, len(articles))} articles:")
            for i, article in enumerate(articles[:3], 1):
                print(f"  {i}. [{article.get('publishedAt', 'N/A')[:10]}] {article.get('title', 'N/A')[:60]}...")
        
        print()
        print("✅ Marketaux free tier provides historical data!")
        print("   You can use this for backtesting 2023-2024 data.")
    
except Exception as e:
    print("=" * 60)
    print("ERROR")
    print("=" * 60)
    print(f"❌ Exception occurred: {e}")
    print()
    print("Full error details:")
    import traceback
    traceback.print_exc()
    print()
    print("Check:")
    print("  1. API key is valid")
    print("  2. Rate limit not exceeded (100 requests/day)")
    print("  3. Internet connection is working")
    print("  4. Marketaux API is accessible")

print()
print("=" * 60)
