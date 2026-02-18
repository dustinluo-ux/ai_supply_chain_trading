"""
Dual-stream news aggregator: Marketaux (targeted) + Tiingo (broad).

Returns a unified list of articles with 'source' tag (marketaux, tiingo)
for downstream sentiment (e.g. Gemini). Use when config requests dual-stream.
"""
import logging
from typing import List, Dict, Optional

from src.data.news_base import NewsDataSource
from src.data.news_fetcher_factory import NewsFetcherFactory
from src.utils.logger import setup_logger

logger = setup_logger()


class DualStreamNewsAggregator(NewsDataSource):
    """
    Fetches from Marketaux and Tiingo, merges into one stream.
    Each article dict includes 'source': 'marketaux' | 'tiingo'.
    """

    def __init__(self, data_dir: str = "data/news", keywords: Optional[List[str]] = None):
        super().__init__(data_dir, keywords)
        self._marketaux = None
        self._tiingo = None
        try:
            self._marketaux = NewsFetcherFactory.create_source("marketaux", data_dir, keywords)
        except Exception as e:
            logger.warning(f"DualStreamNewsAggregator: could not init Marketaux: {e}")
        try:
            self._tiingo = NewsFetcherFactory.create_source("tiingo", data_dir, keywords)
        except Exception as e:
            logger.warning(f"DualStreamNewsAggregator: could not init Tiingo: {e}")
        if not self._marketaux and not self._tiingo:
            raise ValueError("DualStreamNewsAggregator: need at least one of Marketaux or Tiingo")
        logger.info("DualStreamNewsAggregator initialized (marketaux + tiingo)")

    def get_name(self) -> str:
        return "dual_stream"

    def fetch_articles_for_ticker(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        use_cache: bool = True,
    ) -> List[Dict]:
        seen_urls = set()
        out: List[Dict] = []
        for name, src in [("marketaux", self._marketaux), ("tiingo", self._tiingo)]:
            if src is None:
                continue
            try:
                articles = src.fetch_articles_for_ticker(ticker, start_date, end_date, use_cache)
                for a in articles:
                    a = dict(a)
                    a["source"] = name
                    url = a.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        out.append(a)
            except Exception as e:
                logger.debug(f"DualStream fetch {name} {ticker}: {e}")
        out.sort(key=lambda x: x.get("publishedAt", ""), reverse=True)
        return out
