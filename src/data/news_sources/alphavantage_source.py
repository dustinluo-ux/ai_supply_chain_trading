"""
Alpha Vantage News & Sentiment API data source
Free tier: 5 API calls per minute, 500 per day
Has historical data back to 2023
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


class AlphaVantageSource(NewsDataSource):
    """Alpha Vantage News & Sentiment API data source"""
    
    def __init__(self, data_dir: str = "data/news", keywords: Optional[List[str]] = None):
        super().__init__(data_dir, keywords)
        
        # Initialize Alpha Vantage API
        api_key = os.getenv("ALPHAVANTAGE_API_KEY")
        if not api_key:
            raise ValueError("ALPHAVANTAGE_API_KEY not found in .env file. Get free key from: https://www.alphavantage.co/support/#api-key")
        
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"
        
        # Rate limiting: Free tier = 5 calls per minute, 500 per day
        self.calls_per_minute = 5
        self.calls_today = 0
        self.last_call_time = None
        self.call_times = []  # Track calls in last minute
        
        logger.info("AlphaVantageSource initialized")
    
    def get_name(self) -> str:
        return "alphavantage"
    
    def _check_rate_limit(self):
        """Check and enforce rate limits (5 calls per minute)"""
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
        self.calls_today += 1
    
    def _fetch_company_news(self, ticker: str, limit: int = 1000) -> List[Dict]:
        """
        Fetch company news from Alpha Vantage
        
        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of articles to fetch
        
        Returns:
            List of raw article dictionaries
        """
        self._check_rate_limit()
        
        params = {
            'function': 'NEWS_SENTIMENT',
            'tickers': ticker,
            'apikey': self.api_key,
            'limit': min(limit, 1000)  # API max is 1000
        }
        
        try:
            logger.debug(f"Fetching Alpha Vantage news for {ticker} with params: {params}")
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            logger.debug(f"Alpha Vantage response keys: {list(data.keys())}")
            
            if 'Error Message' in data:
                logger.error(f"Alpha Vantage error: {data['Error Message']}")
                return []
            
            if 'Note' in data:
                logger.warning(f"Alpha Vantage note: {data['Note']}")
                return []
            
            if 'feed' not in data:
                logger.warning(f"No 'feed' in Alpha Vantage response for {ticker}")
                logger.debug(f"Response keys: {list(data.keys())}")
                logger.debug(f"Response sample: {str(data)[:500]}")
                return []
            
            feed = data['feed']
            items_count = data.get('items', len(feed))
            
            if not isinstance(feed, list):
                logger.error(f"Expected 'feed' to be a list, got {type(feed)}")
                return []
            
            logger.info(f"Alpha Vantage API returned {items_count} items, feed array has {len(feed)} articles for {ticker}")
            
            if len(feed) > 0:
                logger.debug(f"Sample article keys: {list(feed[0].keys())}")
                logger.debug(f"Sample article time_published: {feed[0].get('time_published', 'N/A')}")
            
            return feed
        
        except Exception as e:
            logger.error(f"Error fetching Alpha Vantage news for {ticker}: {e}")
            return []
    
    def _parse_alphavantage_article(self, article: Dict, ticker: str) -> Dict:
        """
        Parse Alpha Vantage article format to standardized format
        
        Alpha Vantage format:
        {
            'title': str,
            'url': str,
            'time_published': str (YYYYMMDDTHHMMSS),
            'authors': [str],
            'summary': str,
            'banner_image': str,
            'source': str,
            'category_within_source': str,
            'source_domain': str,
            'topics': [{'topic': str, 'relevance_score': str}],
            'overall_sentiment_score': float,
            'overall_sentiment_label': str,
            'ticker_sentiment': [{'ticker': str, 'relevance_score': str, 'ticker_sentiment_score': str, 'ticker_sentiment_label': str}]
        }
        """
        # Parse time_published (YYYYMMDDTHHMMSS) to ISO format
        time_published = article.get('time_published', '')
        published_at = ''
        
        if time_published:
            try:
                # Format: 20260121T123824 (YYYYMMDDTHHMMSS)
                dt = datetime.strptime(time_published, '%Y%m%dT%H%M%S')
                published_at = dt.isoformat() + 'Z'
                logger.debug(f"Parsed date: {time_published} -> {published_at}")
            except Exception as e:
                logger.warning(f"Failed to parse time_published '{time_published}': {e}")
                published_at = ''
        
        # Get summary/content
        summary = article.get('summary', '')
        title = article.get('title', '')
        
        # Get source name
        source_name = article.get('source', 'Alpha Vantage')
        if not source_name or source_name == '':
            source_name = 'Alpha Vantage'
        
        standardized = {
            'title': title,
            'description': summary[:500] if summary else title,  # Use summary as description
            'content': summary,  # Full summary as content
            'url': article.get('url', ''),
            'publishedAt': published_at,
            'source': source_name,
            'ticker': ticker,
            'fetched_at': datetime.now().isoformat(),
            # Alpha Vantage specific fields
            'sentiment_score': article.get('overall_sentiment_score', 0.0),
            'sentiment_label': article.get('overall_sentiment_label', 'neutral'),
            'topics': article.get('topics', [])
        }
        
        return standardized
    
    def fetch_articles_for_ticker(self, ticker: str, start_date: str, end_date: str,
                                  use_cache: bool = True) -> List[Dict]:
        """
        Fetch news articles for a specific ticker using Alpha Vantage
        
        Note: Alpha Vantage doesn't support date filtering in the API,
        so we fetch all available articles and filter by date client-side
        """
        # Check cache first
        if use_cache:
            cached = self._get_cached_articles(ticker, start_date, end_date)
            if cached:
                logger.debug(f"Loaded {len(cached)} cached articles for {ticker}")
                # For Alpha Vantage, if we have cached data, we might want to check for updates
                # For now, return cached if available
        
        # Fetch from Alpha Vantage
        raw_articles = self._fetch_company_news(ticker, limit=1000)
        
        if not raw_articles:
            logger.warning(f"No articles returned from Alpha Vantage for {ticker}")
            return []
        
        logger.info(f"API returned {len(raw_articles)} articles for {ticker}")
        
        # Parse and standardize articles
        standardized_articles = []
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        logger.info(f"Filtering articles for date range: {start_date} to {end_date}")
        
        articles_without_date = 0
        articles_out_of_range = 0
        articles_in_range = 0
        
        for article in raw_articles:
            try:
                std_article = self._parse_alphavantage_article(article, ticker)
                
                # Filter by date range
                article_date_str = std_article.get('publishedAt', '')
                if article_date_str:
                    try:
                        # Parse ISO format date (handle Z and timezone)
                        # Format is like: 2024-01-15T12:00:00Z
                        date_str_clean = article_date_str.replace('Z', '').split('+')[0]
                        if 'T' in date_str_clean:
                            # Extract just the date part (YYYY-MM-DD)
                            date_part = date_str_clean.split('T')[0]
                            article_date = datetime.strptime(date_part, '%Y-%m-%d')
                        else:
                            # Already just date
                            article_date = datetime.strptime(date_str_clean, '%Y-%m-%d')
                        
                        # Compare dates (ignore time)
                        article_date_only = article_date.date()
                        if start_dt.date() <= article_date_only <= end_dt.date():
                            standardized_articles.append(std_article)
                            articles_in_range += 1
                        else:
                            articles_out_of_range += 1
                            logger.debug(f"Article date {article_date_only} is outside range {start_dt.date()} to {end_dt.date()}")
                    except Exception as e:
                        # If date parsing fails, include it (better to have it than miss it)
                        logger.warning(f"Date parsing failed for article '{std_article.get('title', '')[:50]}': {e}, including anyway")
                        standardized_articles.append(std_article)
                        articles_without_date += 1
                else:
                    # If no date, include it
                    articles_without_date += 1
                    standardized_articles.append(std_article)
                    logger.debug(f"Article has no publishedAt date, including anyway")
            
            except Exception as e:
                logger.warning(f"Error parsing Alpha Vantage article: {e}")
                logger.debug(f"Article data: {article}")
                continue
        
        logger.info(f"After date filtering: {articles_in_range} in range, {articles_out_of_range} out of range, {articles_without_date} without date")
        logger.info(f"Total standardized articles: {len(standardized_articles)}")
        
        # Filter by keywords
        before_keyword_filter = len(standardized_articles)
        filtered = self._filter_by_keywords(standardized_articles)
        after_keyword_filter = len(filtered)
        logger.info(f"After keyword filtering: {after_keyword_filter} articles (removed {before_keyword_filter - after_keyword_filter})")
        
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
        
        logger.info(f"✅ Final result: {len(unique_articles)} unique articles for {ticker} from Alpha Vantage")
        return unique_articles
