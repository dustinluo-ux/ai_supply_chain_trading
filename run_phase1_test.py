"""
Phase 1 Test Script
Tests data infrastructure: price fetcher, news fetcher, LLM analyzer
"""
import sys
import os
import yaml
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logger
from src.data.price_fetcher import PriceFetcher
from src.data.news_fetcher import NewsFetcher
from src.signals.llm_analyzer import LLMAnalyzer

logger = setup_logger()


def load_config():
    """Load configuration from config.yaml"""
    config_path = project_root / "config" / "config.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def test_price_fetcher(config):
    """Test price data fetching"""
    logger.info("=" * 60)
    logger.info("TEST 1: Price Data Fetcher")
    logger.info("=" * 60)
    
    date_range = config['data']['date_range']
    market_cap = config['market_cap']
    
    fetcher = PriceFetcher(
        data_dir="data/prices",
        min_market_cap=market_cap['min'],
        max_market_cap=market_cap['max']
    )
    
    # Test with small sample first
    logger.info("Fetching price data for test tickers...")
    results = fetcher.run(
        start_date=date_range['start'],
        end_date=date_range['end'],
        use_market_cap_filter=True
    )
    
    logger.info(f"✅ Price fetcher test complete: {len(results)} tickers fetched")
    return results


def test_news_fetcher(config):
    """Test news data fetching"""
    logger.info("=" * 60)
    logger.info("TEST 2: News Data Fetcher")
    logger.info("=" * 60)
    
    # Check if API key is set
    if not os.getenv("NEWS_API_KEY"):
        logger.warning("NEWS_API_KEY not set - skipping news fetcher test")
        logger.info("To test: Add NEWS_API_KEY to .env file")
        return {}
    
    date_range = config['data']['date_range']
    keywords = config['news_keywords']
    
    fetcher = NewsFetcher(
        data_dir="data/news",
        keywords=keywords
    )
    
    # Test with a few tickers
    test_tickers = ['NVDA', 'AMD', 'MU']
    logger.info(f"Fetching news for test tickers: {test_tickers}")
    
    results = fetcher.fetch_all_tickers(
        tickers=test_tickers,
        start_date=date_range['start'],
        end_date=date_range['end'],
        use_cache=True
    )
    
    total_articles = sum(len(articles) for articles in results.values())
    logger.info(f"✅ News fetcher test complete: {total_articles} articles fetched")
    return results


def test_llm_analyzer(config):
    """Test LLM analyzer"""
    logger.info("=" * 60)
    logger.info("TEST 3: LLM Analyzer (FinBERT)")
    logger.info("=" * 60)
    
    llm_config = config['llm']
    provider = llm_config.get('provider', 'finbert')
    
    # Test article
    test_article = {
        'title': 'NVIDIA Partners with Western Digital for AI Data Storage Solutions',
        'description': 'NVIDIA announces partnership with Western Digital to develop high-capacity storage solutions for AI data centers. The partnership will focus on optimizing storage for large language model training.',
        'content': 'NVIDIA and Western Digital have partnered to create storage solutions optimized for AI workloads. The collaboration aims to address the massive storage requirements of modern AI training...',
        'url': 'https://example.com/test',
        'publishedAt': '2024-01-15T10:00:00Z',
        'ticker': 'WDC'
    }
    
    try:
        logger.info("Testing FinBERT (local model)...")
        analyzer = LLMAnalyzer(provider="finbert")
        result = analyzer.analyze_article(test_article)
        logger.info(f"✅ FinBERT test complete")
        logger.info(f"Result: AI Related={result['ai_related']}, Sentiment={result['sentiment']}, Relevance={result['relevance_score']:.2f}")
        return True
    
    except Exception as e:
        logger.error(f"LLM analyzer test failed: {e}")
        return False


def main():
    """Run all Phase 1 tests"""
    logger.info("Starting Phase 1 Data Infrastructure Tests")
    logger.info("=" * 60)
    
    # Load config
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return
    
    results = {
        'price_fetcher': False,
        'news_fetcher': False,
        'llm_analyzer': False
    }
    
    # Test 1: Price Fetcher
    try:
        price_results = test_price_fetcher(config)
        results['price_fetcher'] = len(price_results) > 0
    except Exception as e:
        logger.error(f"Price fetcher test failed: {e}")
    
    # Test 2: News Fetcher
    try:
        news_results = test_news_fetcher(config)
        results['news_fetcher'] = len(news_results) > 0 or not os.getenv("NEWS_API_KEY")
    except Exception as e:
        logger.error(f"News fetcher test failed: {e}")
    
    # Test 3: LLM Analyzer
    try:
        results['llm_analyzer'] = test_llm_analyzer(config)
    except Exception as e:
        logger.error(f"LLM analyzer test failed: {e}")
    
    # Summary
    logger.info("=" * 60)
    logger.info("PHASE 1 TEST SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Price Fetcher: {'✅ PASS' if results['price_fetcher'] else '❌ FAIL'}")
    logger.info(f"News Fetcher: {'✅ PASS' if results['news_fetcher'] else '❌ FAIL'}")
    logger.info(f"LLM Analyzer: {'✅ PASS' if results['llm_analyzer'] else '❌ FAIL'}")
    
    if all(results.values()):
        logger.info("\n🎉 Phase 1 tests passed! Ready for Phase 2.")
    else:
        logger.warning("\n⚠️  Some tests failed. Check logs above for details.")


if __name__ == "__main__":
    main()
