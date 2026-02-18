"""
Marketaux News API data source
Free tier: 100 requests per day, up to 3 articles per request
Supports historical data filtering via published_after/published_before
All dates are in UTC
"""
import os
import time
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging
from dotenv import load_dotenv

from src.data.news_base import NewsDataSource

logger = logging.getLogger(__name__)
load_dotenv()


class MarketauxSource(NewsDataSource):
    """
    Marketaux News API data source
    
    Free Tier Limits:
    - 100 requests per day maximum
    - Up to 3 news articles returned per request on free plan
    - All dates returned in UTC
    - Supports historical filtering via published_after / published_before
    
    API Documentation: https://www.marketaux.com/documentation
    """
    
    def __init__(self, data_dir: str = "data/news", keywords: Optional[List[str]] = None):
        super().__init__(data_dir, keywords)
        
        # Initialize Marketaux API
        api_key = os.getenv("MARKETAUX_API_KEY")
        if not api_key:
            raise ValueError(
                "MARKETAUX_API_KEY not found in .env file. "
                "Get free key from: https://www.marketaux.com/"
            )
        
        self.api_key = api_key
        self.base_url = "https://api.marketaux.com/v1/news/all"
        
        # Rate limiting: Free tier = 100 requests per day
        self.requests_per_day = 100
        self.requests_today = 0
        self.last_request_date = datetime.now().date()
        self.request_times = []  # Track requests for rate limiting
        
        # Free tier returns max 3 articles per request
        self.max_articles_per_request = 3
        
        logger.info("MarketauxSource initialized")
        logger.info(f"Free tier limits: {self.requests_per_day} requests/day, "
                   f"{self.max_articles_per_request} articles per request")
    
    def get_name(self) -> str:
        return "marketaux"
    
    def _check_rate_limit(self):
        """Check and enforce rate limits (100 requests per day)"""
        now = datetime.now()
        today = now.date()
        
        # Reset daily counter if it's a new day
        if today != self.last_request_date:
            self.requests_today = 0
            self.last_request_date = today
            logger.debug("Daily request counter reset")
        
        # Check daily limit
        if self.requests_today >= self.requests_per_day:
            logger.warning(
                f"Daily rate limit reached ({self.requests_per_day} requests). "
                "Waiting until tomorrow..."
            )
            # Calculate seconds until midnight
            tomorrow = datetime.combine(today + timedelta(days=1), datetime.min.time())
            wait_seconds = (tomorrow - now).total_seconds() + 1
            logger.info(f"Waiting {wait_seconds:.0f} seconds until rate limit resets")
            time.sleep(min(wait_seconds, 3600))  # Cap at 1 hour wait
            # Reset after wait
            self.requests_today = 0
            self.last_request_date = datetime.now().date()
        
        # Track this request
        self.requests_today += 1
        self.request_times.append(now)
        logger.debug(f"Request {self.requests_today}/{self.requests_per_day} today")
    
    def _fetch_articles_batch(self, ticker: str, start_date: str, end_date: str, 
                               page: int = 1) -> Dict:
        """
        Fetch a batch of articles from Marketaux API
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            page: Page number for pagination
        
        Returns:
            API response dictionary
        """
        self._check_rate_limit()
        
        params = {
            'api_token': self.api_key,
            'symbols': ticker,
            'published_after': start_date,
            'published_before': end_date,
            'language': 'en',
            'limit': self.max_articles_per_request,  # Free tier max
            'page': page
        }
        
        try:
            logger.debug(f"Fetching Marketaux news for {ticker} (page {page}) with params: {params}")
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Check for errors
            if 'error' in data:
                logger.error(f"Marketaux API error: {data['error']}")
                return {}
            
            # Small delay to be polite with API
            time.sleep(0.5)
            
            return data
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching Marketaux news for {ticker}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error fetching Marketaux news for {ticker}: {e}")
            return {}
    
    def _parse_marketaux_article(self, article: Dict, ticker: str) -> Dict:
        """
        Parse Marketaux article format to standardized format
        
        Marketaux format:
        {
            'uuid': str,
            'title': str,
            'description': str,
            'snippet': str,
            'url': str,
            'image_url': str,
            'language': str,
            'published_at': str (ISO format),
            'source': str,
            'categories': [str],
            'relevance_score': float,
            'entities': [{'symbol': str, 'name': str, 'exchange': str, ...}],
            'similar': [article_uuids]
        }
        """
        # Parse published_at (ISO format, UTC)
        published_at = article.get('published_at', '')
        if not published_at:
            logger.warning(f"Article missing published_at: {article.get('title', 'N/A')[:50]}")
        
        # Get content (use snippet or description)
        snippet = article.get('snippet', '')
        description = article.get('description', '')
        content = snippet if snippet else description
        
        # Get source name
        source_name = article.get('source', 'Marketaux')
        if not source_name:
            source_name = 'Marketaux'
        
        standardized = {
            'title': article.get('title', ''),
            'description': description[:500] if description else article.get('title', ''),
            'content': content,  # Full snippet/description as content
            'url': article.get('url', ''),
            'publishedAt': published_at,
            'source': source_name,
            'ticker': ticker,
            'fetched_at': datetime.now().isoformat(),
            # Marketaux specific fields
            'relevance_score': article.get('relevance_score', 0.0),
            'categories': article.get('categories', []),
            'entities': article.get('entities', [])
        }
        
        return standardized
    
    def fetch_articles_for_ticker(self, ticker: str, start_date: str, end_date: str,
                                  use_cache: bool = True) -> List[Dict]:
        """
        Fetch news articles for a specific ticker using Marketaux API
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            use_cache: Whether to use cached articles
        
        Returns:
            List of standardized article dictionaries
        """
        # Check cache first
        if use_cache:
            cached = self._get_cached_articles(ticker, start_date, end_date)
            if cached:
                logger.info(f"Loaded {len(cached)} cached articles for {ticker}")
                return cached
        
        # Fetch from Marketaux with pagination
        all_articles = []
        page = 1
        max_pages = 50  # Safety limit to avoid infinite loops
        
        logger.info(f"Fetching Marketaux news for {ticker} from {start_date} to {end_date}")
        
        while page <= max_pages:
            # Fetch batch
            response_data = self._fetch_articles_batch(ticker, start_date, end_date, page)
            
            if not response_data or 'data' not in response_data:
                logger.debug(f"No more articles for {ticker} (page {page})")
                break
            
            articles_batch = response_data.get('data', [])
            
            if not articles_batch:
                logger.debug(f"No articles in batch for {ticker} (page {page})")
                break
            
            logger.info(f"Fetched {len(articles_batch)} articles for {ticker} (page {page})")
            
            # Parse and standardize articles
            for article in articles_batch:
                try:
                    std_article = self._parse_marketaux_article(article, ticker)
                    all_articles.append(std_article)
                except Exception as e:
                    logger.warning(f"Error parsing Marketaux article: {e}")
                    logger.debug(f"Article data: {article}")
                    continue
            
            # Check if there are more pages
            meta = response_data.get('meta', {})
            current_page = meta.get('current_page', page)
            last_page = meta.get('last_page', current_page)
            
            if current_page >= last_page:
                logger.debug(f"Reached last page ({last_page}) for {ticker}")
                break
            
            page += 1
            
            # Safety check: if we got fewer articles than max, we're probably done
            if len(articles_batch) < self.max_articles_per_request:
                logger.debug(f"Received fewer articles than max ({len(articles_batch)} < {self.max_articles_per_request}), stopping pagination")
                break
        
        logger.info(f"Fetched {len(all_articles)} total articles for {ticker} from Marketaux")
        
        # Filter by keywords
        before_keyword_filter = len(all_articles)
        filtered = self._filter_by_keywords(all_articles)
        after_keyword_filter = len(filtered)
        logger.info(f"After keyword filtering: {after_keyword_filter} articles "
                   f"(removed {before_keyword_filter - after_keyword_filter})")
        
        # Deduplicate by URL
        seen_urls = set()
        unique_articles = []
        for article in filtered:
            url = article.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_articles.append(article)
        
        logger.info(f"After deduplication: {len(unique_articles)} unique articles")
        
        # Save to cache
        if unique_articles:
            self._save_articles(ticker, unique_articles)
        
        logger.info(f"✅ Final result: {len(unique_articles)} unique articles for {ticker} from Marketaux")
        return unique_articles
