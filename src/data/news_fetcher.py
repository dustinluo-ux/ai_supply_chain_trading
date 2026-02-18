"""
News data fetcher - modular system supporting multiple sources
Backward compatible wrapper around NewsFetcherFactory

This module maintains backward compatibility while supporting multiple news sources.
Use NewsFetcherFactory to create sources, or use NewsFetcher which reads from config.
"""
from src.data.news_fetcher_factory import NewsFetcher, NewsFetcherFactory

# Export for backward compatibility
__all__ = ['NewsFetcher', 'NewsFetcherFactory']


if __name__ == "__main__":
    # Test script
    import logging
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    
    # Test with config-based source selection
    try:
        fetcher = NewsFetcher()  # Reads from config.yaml
        test_tickers = ['NVDA', 'AMD', 'MU']
        results = fetcher.fetch_all_tickers(test_tickers, "2024-01-01", "2024-01-31")
        print(f"\n✅ Fetched news for {len(results)} tickers")
    except Exception as e:
        print(f"ERROR: {e}")
        print("\nAvailable sources:", NewsFetcherFactory.list_available_sources())
        print("\nMake sure to:")
        print("1. Set news source in config.yaml (news.source)")
        print("2. Add appropriate API key to .env file")
