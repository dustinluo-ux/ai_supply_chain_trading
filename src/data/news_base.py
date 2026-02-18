"""
Abstract base class for news data sources
All news sources must implement this interface
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import os
import json
import logging
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)


class NewsDataSource(ABC):
    """Abstract base class for all news data sources"""
    
    def __init__(self, data_dir: str = "data/news", keywords: Optional[List[str]] = None):
        """
        Initialize news data source
        
        Args:
            data_dir: Directory to store cached articles
            keywords: List of keywords to filter articles
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.keywords = keywords or []
        logger.info(f"{self.__class__.__name__} initialized with {len(self.keywords)} keywords")
    
    @abstractmethod
    def fetch_articles_for_ticker(self, ticker: str, start_date: str, end_date: str,
                                  use_cache: bool = True) -> List[Dict]:
        """
        Fetch news articles for a specific ticker
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            use_cache: Whether to use cached articles
        
        Returns:
            List of article dictionaries with standardized format:
            {
                'title': str,
                'description': str,
                'content': str,
                'url': str,
                'publishedAt': str (ISO format),
                'source': str,
                'ticker': str,
                'fetched_at': str (ISO format)
            }
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Return the name of this data source"""
        pass
    
    def _get_cached_articles(self, ticker: str, start_date: str, end_date: str) -> List[Dict]:
        """Load cached articles for a ticker if they exist"""
        cache_path = os.path.join(self.data_dir, f"{ticker}_news.json")
        
        if not os.path.exists(cache_path):
            return []
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            
            # Filter by date range
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            
            filtered = []
            for article in cached:
                article_date = pd.to_datetime(article.get('publishedAt', ''))
                if start_dt <= article_date <= end_dt:
                    filtered.append(article)
            
            return filtered
        except Exception as e:
            logger.warning(f"Error loading cache for {ticker}: {e}")
            return []
    
    def _save_articles(self, ticker: str, articles: List[Dict]):
        """Save articles to JSON cache"""
        cache_path = os.path.join(self.data_dir, f"{ticker}_news.json")
        
        # Load existing articles
        existing = self._get_cached_articles(ticker, "2000-01-01", "2100-01-01")
        
        # Merge and deduplicate by URL
        existing_urls = {a.get('url', '') for a in existing}
        new_articles = [a for a in articles if a.get('url', '') not in existing_urls]
        
        all_articles = existing + new_articles
        
        # Sort by date
        all_articles.sort(key=lambda x: x.get('publishedAt', ''))
        
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(all_articles, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved {len(new_articles)} new articles for {ticker}")
        except Exception as e:
            logger.error(f"Error saving articles for {ticker}: {e}")
    
    def _standardize_article(self, article: Dict, ticker: str, source_name: str) -> Dict:
        """
        Standardize article format across all sources
        
        Args:
            article: Raw article from source
            ticker: Stock ticker
            source_name: Name of the data source
        
        Returns:
            Standardized article dictionary
        """
        standardized = {
            'title': article.get('title', ''),
            'description': article.get('description', ''),
            'content': article.get('content', article.get('description', '')),
            'url': article.get('url', ''),
            'publishedAt': article.get('publishedAt', ''),
            'source': source_name,
            'ticker': ticker,
            'fetched_at': datetime.now().isoformat()
        }
        return standardized
    
    def _filter_by_keywords(self, articles: List[Dict]) -> List[Dict]:
        """Filter articles that contain any of the keywords"""
        if not self.keywords:
            return articles
        
        filtered = []
        for article in articles:
            text = f"{article.get('title', '')} {article.get('description', '')} {article.get('content', '')}".lower()
            if any(keyword.lower() in text for keyword in self.keywords):
                filtered.append(article)
        
        return filtered
    
    def fetch_all_tickers(self, tickers: List[str], start_date: str, end_date: str,
                          use_cache: bool = True) -> Dict[str, List[Dict]]:
        """
        Fetch news for all tickers
        
        Args:
            tickers: List of ticker symbols
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            use_cache: Whether to use cached articles
        
        Returns:
            Dictionary mapping ticker to list of articles
        """
        from tqdm import tqdm
        
        results = {}
        logger.info(f"Fetching news for {len(tickers)} tickers from {start_date} to {end_date}")
        
        for ticker in tqdm(tickers, desc=f"Fetching news ({self.get_name()})"):
            try:
                articles = self.fetch_articles_for_ticker(ticker, start_date, end_date, use_cache)
                results[ticker] = articles
            except Exception as e:
                logger.error(f"Error fetching news for {ticker}: {e}")
                results[ticker] = []
        
        # Save summary
        summary = {
            'date': datetime.now().isoformat(),
            'source': self.get_name(),
            'date_range': {'start': start_date, 'end': end_date},
            'tickers': {ticker: len(articles) for ticker, articles in results.items()},
            'total_articles': sum(len(articles) for articles in results.values())
        }
        
        summary_path = os.path.join(self.data_dir, "fetch_summary.json")
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"News fetch complete. Total articles: {summary['total_articles']}")
        return results
