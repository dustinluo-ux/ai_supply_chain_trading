"""
NewsAPI data source implementation
Keeps existing NewsAPI functionality intact
"""
import os
import time
from typing import List, Dict, Optional
from datetime import datetime
import logging
from newsapi import NewsApiClient
from dotenv import load_dotenv

from src.data.news_base import NewsDataSource

logger = logging.getLogger(__name__)
load_dotenv()


class NewsAPISource(NewsDataSource):
    """NewsAPI data source - original implementation"""
    
    def __init__(self, data_dir: str = "data/news", keywords: Optional[List[str]] = None):
        super().__init__(data_dir, keywords)
        
        # Initialize NewsAPI client
        api_key = os.getenv("NEWS_API_KEY")
        if not api_key:
            raise ValueError("NEWS_API_KEY not found in .env file. Please add it.")
        
        self.client = NewsApiClient(api_key=api_key)
        
        # Rate limiting: Free tier = 100 requests/day
        self.rate_limit_daily = 100
        self.requests_today = 0
        self.last_request_date = None
        
        logger.info("NewsAPISource initialized")
    
    def get_name(self) -> str:
        return "newsapi"
    
    def _check_rate_limit(self):
        """Check and enforce rate limits"""
        today = datetime.now().date()
        
        # Reset counter if new day
        if self.last_request_date != today:
            self.requests_today = 0
            self.last_request_date = today
        
        if self.requests_today >= self.rate_limit_daily:
            raise Exception(f"Daily rate limit reached ({self.rate_limit_daily} requests/day)")
        
        self.requests_today += 1
    
    def fetch_articles_for_ticker(self, ticker: str, start_date: str, end_date: str,
                                  use_cache: bool = True) -> List[Dict]:
        """
        Fetch news articles for a specific ticker using NewsAPI
        Searches for articles containing ticker symbol + keywords
        """
        # Check cache first
        if use_cache:
            cached = self._get_cached_articles(ticker, start_date, end_date)
            if cached:
                logger.debug(f"Loaded {len(cached)} cached articles for {ticker}")
        
        all_articles = []
        
        # Search with ticker + each keyword combination
        search_queries = [f"{ticker} {keyword}" for keyword in self.keywords[:3]]  # Limit to avoid rate limits
        search_queries.append(ticker)  # Also search for ticker alone
        
        for query in search_queries:
            try:
                self._check_rate_limit()
                
                # NewsAPI search
                response = self.client.get_everything(
                    q=query,
                    from_param=start_date,
                    to=end_date,
                    language='en',
                    sort_by='publishedAt',
                    page_size=100  # Max per request
                )
                
                if response['status'] == 'ok':
                    articles = response.get('articles', [])
                    
                    # Standardize and filter articles
                    standardized = []
                    for article in articles:
                        std_article = self._standardize_article(article, ticker, self.get_name())
                        std_article['query'] = query  # Keep query for debugging
                        standardized.append(std_article)
                    
                    # Filter by keywords
                    filtered = self._filter_by_keywords(standardized)
                    all_articles.extend(filtered)
                    logger.debug(f"Found {len(filtered)} relevant articles for query: {query}")
                
                elif response['status'] == 'error':
                    error_msg = response.get('message', 'Unknown error')
                    if 'rate limit' in error_msg.lower():
                        logger.error("Rate limit exceeded")
                        break
                    else:
                        logger.warning(f"NewsAPI error for {query}: {error_msg}")
                
                # Rate limiting delay
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error fetching articles for query '{query}': {e}")
                continue
        
        # Deduplicate by URL
        seen_urls = set()
        unique_articles = []
        for article in all_articles:
            url = article.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_articles.append(article)
        
        # Save to cache
        if unique_articles:
            self._save_articles(ticker, unique_articles)
        
        logger.info(f"Fetched {len(unique_articles)} unique articles for {ticker}")
        return unique_articles
