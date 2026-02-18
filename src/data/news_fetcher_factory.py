"""
News fetcher factory
Creates the appropriate news data source based on configuration
"""
import importlib
import logging
from pathlib import Path
from typing import Optional, List

import yaml

from src.data.news_base import NewsDataSource

logger = logging.getLogger(__name__)

# Lazy-load source classes to avoid ModuleNotFoundError when a source's package is uninstalled
_SOURCE_MAP = {
    'newsapi': ('src.data.news_sources.newsapi_source', 'NewsAPISource'),
    'alphavantage': ('src.data.news_sources.alphavantage_source', 'AlphaVantageSource'),
    'finnhub': ('src.data.news_sources.finnhub_source', 'FinnhubSource'),
    'marketaux': ('src.data.news_sources.marketaux_source', 'MarketauxSource'),
    'tiingo': ('src.data.news_sources.tiingo_source', 'TiingoSource'),
    'dual_stream': ('src.data.news_aggregator', 'DualStreamNewsAggregator'),
}


class NewsFetcherFactory:
    """Factory for creating news data sources"""
    
    @classmethod
    def create_source(cls, source_name: str, data_dir: str = "data/news",
                     keywords: Optional[List[str]] = None,
                     config: Optional[dict] = None) -> NewsDataSource:
        """
        Create a news data source instance
        
        Args:
            source_name: Name of the source ('newsapi', 'alphavantage', 'finnhub', 'marketaux')
            data_dir: Directory to store cached articles
            keywords: List of keywords to filter articles
            config: Optional configuration dict for source-specific settings
        
        Returns:
            NewsDataSource instance
        """
        source_name_lower = source_name.lower()
        
        if source_name_lower not in _SOURCE_MAP:
            available = ', '.join(_SOURCE_MAP.keys())
            raise ValueError(f"Unknown news source: {source_name}. Available: {available}")
        
        module_path, class_name = _SOURCE_MAP[source_name_lower]
        try:
            mod = importlib.import_module(module_path)
            source_class = getattr(mod, class_name)
        except ModuleNotFoundError as e:
            raise ImportError(
                f"Failed to load news source '{source_name_lower}': {e}. "
                "Install the required package for this source."
            ) from e
        
        try:
            instance = source_class(data_dir=data_dir, keywords=keywords)
            logger.info(f"Created {source_name_lower} news source")
            return instance
        except Exception as e:
            logger.error(f"Error creating {source_name_lower} source: {e}")
            raise
    
    @classmethod
    def create_from_config(cls, config_path: Optional[str] = None) -> NewsDataSource:
        """
        Create news source from config.yaml
        
        Args:
            config_path: Path to config.yaml (default: config/config.yaml)
        
        Returns:
            NewsDataSource instance
        """
        if config_path is None:
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "config.yaml"
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Get news source configuration
        news_config = config.get('news', {})
        source_name = news_config.get('source', 'newsapi')
        
        # Get keywords from config
        keywords = config.get('news_keywords', [])
        
        # Get data directory
        data_dir = "data/news"
        
        logger.info(f"Creating news source from config: {source_name}")
        return cls.create_source(source_name, data_dir, keywords, news_config)
    
    @classmethod
    def list_available_sources(cls) -> List[str]:
        """Return list of available news sources"""
        return list(_SOURCE_MAP.keys())


# Backward compatibility: Create NewsFetcher class that uses factory
class NewsFetcher:
    """
    Backward-compatible NewsFetcher class
    Uses factory to create the appropriate source
    """
    
    def __init__(self, data_dir: str = "data/news", keywords: Optional[List[str]] = None,
                 source: Optional[str] = None):
        """
        Initialize news fetcher
        
        Args:
            data_dir: Directory to store cached articles
            keywords: List of keywords to filter articles
            source: News source name (if None, reads from config.yaml)
        """
        if source is None:
            # Read from config
            self.source = NewsFetcherFactory.create_from_config()
        else:
            # Use specified source
            self.source = NewsFetcherFactory.create_source(source, data_dir, keywords)
    
    def fetch_articles_for_ticker(self, ticker: str, start_date: str, end_date: str,
                                  use_cache: bool = True):
        """Fetch articles for a ticker"""
        return self.source.fetch_articles_for_ticker(ticker, start_date, end_date, use_cache)
    
    def fetch_all_tickers(self, tickers: List[str], start_date: str, end_date: str,
                         use_cache: bool = True):
        """Fetch articles for all tickers"""
        return self.source.fetch_all_tickers(tickers, start_date, end_date, use_cache)
