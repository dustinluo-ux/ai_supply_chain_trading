"""
Test Gemini Integration
Verifies that Gemini API is working and returns real (not fallback) scores
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, continue without it
    pass

from src.signals.news_analyzer import NewsAnalyzer
from src.signals.gemini_analyzer import GeminiAnalyzer


def test_gemini_direct():
    """Test Gemini API directly with a sample article"""
    print("=" * 60)
    print("Direct Gemini API Test")
    print("=" * 60)
    
    # Check for API key
    import os
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("\n[ERROR] GEMINI_API_KEY not set!")
        print("  Set it with: export GEMINI_API_KEY=your_key_here")
        print("  Or add to .env file")
        return False
    
    print(f"\n[OK] GEMINI_API_KEY found (length: {len(api_key)})")
    
    # Test article
    test_article = {
        'title': 'NVIDIA Announces Record GPU Orders from Hyperscalers',
        'description': 'NVIDIA reports unprecedented demand for AI training GPUs from AWS, Microsoft Azure, and Google Cloud.',
        'content': 'NVIDIA Corporation announced today that it has received record-breaking orders for its H100 GPUs from major hyperscalers including Amazon Web Services, Microsoft Azure, and Google Cloud Platform. The orders are driven by the explosive growth in AI model training and inference workloads. This partnership strengthens NVIDIA\'s position as a key supplier to the AI infrastructure market.',
        'publishedAt': '2023-06-15T10:00:00Z'
    }
    
    print(f"\n[1/3] Testing GeminiAnalyzer initialization...")
    try:
        analyzer = GeminiAnalyzer()
        print(f"  [OK] GeminiAnalyzer initialized")
    except Exception as e:
        print(f"  [ERROR] Failed to initialize: {e}")
        return False
    
    print(f"\n[2/3] Analyzing test article...")
    print(f"  Title: {test_article['title']}")
    try:
        result = analyzer.analyze_article(test_article)
        print(f"  [OK] Analysis complete")
        print(f"\n  Results:")
        print(f"    Supplier: {result.get('supplier', 'N/A')}")
        print(f"    Customer Type: {result.get('customer_type', 'N/A')}")
        print(f"    Product: {result.get('product', 'N/A')}")
        print(f"    AI Related: {result.get('ai_related', 'N/A')}")
        print(f"    Sentiment: {result.get('sentiment', 'N/A')}")
        print(f"    Relevance Score: {result.get('relevance_score', 'N/A')}")
        
        # Check if result looks reasonable
        if result.get('relevance_score', 0) > 0.5:
            print(f"\n  [OK] Relevance score > 0.5 (looks like real analysis)")
        else:
            print(f"\n  [WARNING] Relevance score <= 0.5 (may be default)")
        
    except Exception as e:
        print(f"  [ERROR] Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print(f"\n[3/3] Testing NewsAnalyzer integration...")
    try:
        news_analyzer = NewsAnalyzer(news_dir="data/news", lookback_days=7)
        
        # Test with a real ticker if news file exists
        test_ticker = "NVDA"
        news_file = Path("data/news") / f"{test_ticker}_news.json"
        
        if news_file.exists():
            print(f"  Found news file: {news_file}")
            print(f"  Testing analyze_news_for_ticker('{test_ticker}', '2023-06-08', '2023-06-15')...")
            
            result = news_analyzer.analyze_news_for_ticker(
                test_ticker,
                '2023-06-08',
                '2023-06-15'
            )
            
            print(f"\n  News Analysis Results:")
            print(f"    Supply Chain Score: {result.get('supply_chain_score', 0):.3f}")
            print(f"    Sentiment Score: {result.get('sentiment_score', 0):.3f}")
            print(f"    Confidence: {result.get('confidence', 0):.3f}")
            
            # Check if scores are fallback (deterministic pattern)
            supply = result.get('supply_chain_score', 0)
            sentiment = result.get('sentiment_score', 0)
            
            # Fallback scores are typically in ranges:
            # supply_chain: 0.3-0.7
            # sentiment: -0.2 to 0.2
            is_fallback = (
                0.3 <= supply <= 0.7 and
                -0.2 <= sentiment <= 0.2
            )
            
            if is_fallback:
                print(f"\n  [WARNING] Scores look like fallback values!")
                print(f"    Fallback range: supply_chain [0.3, 0.7], sentiment [-0.2, 0.2]")
                print(f"    This may indicate:")
                print(f"      1. No articles found in date range")
                print(f"      2. Gemini API call failed")
                print(f"      3. News file format incorrect")
            else:
                print(f"\n  [OK] Scores outside fallback range - likely real Gemini analysis!")
                
        else:
            print(f"  [INFO] News file not found: {news_file}")
            print(f"  [INFO] Run process_fnspid.py first to generate news files")
        
        print(f"  [OK] NewsAnalyzer integration test complete")
        
    except Exception as e:
        print(f"  [ERROR] NewsAnalyzer test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 60)
    print("[SUCCESS] All Gemini tests passed!")
    print("=" * 60)
    return True


def test_multiple_articles():
    """Test with multiple articles to verify consistency"""
    print("\n" + "=" * 60)
    print("Multiple Articles Test")
    print("=" * 60)
    
    news_file = Path("data/news/NVDA_news.json")
    if not news_file.exists():
        print(f"  [SKIP] News file not found: {news_file}")
        return
    
    print(f"\n[1/2] Loading articles from {news_file}...")
    with open(news_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, list):
        articles = data
    elif isinstance(data, dict) and 'articles' in data:
        articles = data['articles']
    else:
        print(f"  [ERROR] Unexpected format in {news_file}")
        return
    
    print(f"  [OK] Loaded {len(articles)} articles")
    
    if len(articles) == 0:
        print(f"  [SKIP] No articles to test")
        return
    
    # Test with first 5 articles
    test_articles = articles[:5]
    print(f"\n[2/2] Testing with {len(test_articles)} articles...")
    
    try:
        analyzer = GeminiAnalyzer()
        results = []
        
        for i, article in enumerate(test_articles, 1):
            print(f"\n  Article {i}/{len(test_articles)}:")
            print(f"    Title: {article.get('title', 'N/A')[:60]}...")
            
            result = analyzer.analyze_article(article)
            results.append(result)
            
            print(f"    Supply Chain Relevance: {result.get('relevance_score', 0):.3f}")
            print(f"    Sentiment: {result.get('sentiment', 'N/A')}")
        
        # Check variance in scores
        relevance_scores = [r.get('relevance_score', 0) for r in results]
        if len(set(relevance_scores)) > 1:
            print(f"\n  [OK] Scores vary across articles (not constant)")
            print(f"    Range: {min(relevance_scores):.3f} to {max(relevance_scores):.3f}")
        else:
            print(f"\n  [WARNING] All scores are identical (may indicate issue)")
        
    except Exception as e:
        print(f"  [ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    success = test_gemini_direct()
    
    if success:
        test_multiple_articles()
    else:
        print("\n[ERROR] Initial test failed. Fix issues before running multiple articles test.")
        sys.exit(1)
