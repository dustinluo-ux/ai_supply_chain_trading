"""
Finnhub News API data source
Backup option - requires API key
Free tier: 60 API calls per minute
"""
import os
import time
import requests
from typing import List, Dict, Optional
from datetime import datetime
import logging
from dotenv import load_dotenv

from src.data.news_base import NewsDataSource

logger = logging.getLogger(__name__)
load_dotenv()


class FinnhubSource(NewsDataSource):
    """Finnhub News API data source"""
    
    def __init__(self, data_dir: str = "data/news", keywords: Optional[List[str]] = None):
        super().__init__(data_dir, keywords)
        
        # Initialize Finnhub API
        api_key = os.getenv("FINNHUB_API_KEY")
        if not api_key:
            raise ValueError("FINNHUB_API_KEY not found in .env file. Get free key from: https://finnhub.io/register")
        
        self.api_key = api_key
        self.base_url = "https://finnhub.io/api/v1"
        
        # Rate limiting: Free tier = 60 calls per minute
        self.calls_per_minute = 60
        self.call_times = []
        
        logger.info("FinnhubSource initialized")
    
    def get_name(self) -> str:
        return "finnhub"
    
    def _check_rate_limit(self):
        """Check and enforce rate limits (60 calls per minute)"""
        now = datetime.now()
        
        # Remove calls older than 1 minute
        self.call_times = [t for t in self.call_times if (now - t).seconds < 60]
        
        # Check per-minute limit
        if len(self.call_times) >= self.calls_per_minute:
            # Wait until we can make another call
            oldest_call = min(self.call_times)
            wait_seconds = 60 - (now - oldest_call).seconds + 1
            logger.debug(f"Rate limit: waiting {wait_seconds} seconds")
            time.sleep(wait_seconds)
            # Clean up again
            now = datetime.now()
            self.call_times = [t for t in self.call_times if (now - t).seconds < 60]
        
        # Track this call
        self.call_times.append(now)
    
    def fetch_articles_for_ticker(self, ticker: str, start_date: str, end_date: str,
                                  use_cache: bool = True) -> List[Dict]:
        """
        Fetch news articles for a specific ticker using Finnhub
        
        Note: This is a stub implementation. Finnhub API structure needs to be implemented.
        """
        # Check cache first
        if use_cache:
            cached = self._get_cached_articles(ticker, start_date, end_date)
            if cached:
                logger.debug(f"Loaded {len(cached)} cached articles for {ticker}")
                return cached
        
        # TODO: Implement Finnhub API calls
        # Finnhub endpoint: GET /news?symbol={symbol}
        # Returns: List of news articles
        
        logger.warning("Finnhub source not fully implemented yet")
        return []
    
    def _parse_finnhub_article(self, article: Dict, ticker: str) -> Dict:
        """Parse Finnhub article format to standardized format"""
        # TODO: Implement parsing when API is integrated
        standardized = {
            'title': article.get('headline', ''),
            'description': article.get('summary', ''),
            'content': article.get('summary', ''),
            'url': article.get('url', ''),
            'publishedAt': article.get('datetime', ''),
            'source': 'Finnhub',
            'ticker': ticker,
            'fetched_at': datetime.now().isoformat()
        }
        return standardized
