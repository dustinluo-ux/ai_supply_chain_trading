"""
Tiingo News API data source.

Broad coverage news; use with Marketaux (targeted) for dual-stream.
API key: TIINGO_API_KEY in .env
Docs: https://www.tiingo.com/documentation/news
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


class TiingoSource(NewsDataSource):
    """
    Tiingo News API data source (broad coverage).
    """

    def __init__(self, data_dir: str = "data/news", keywords: Optional[List[str]] = None):
        super().__init__(data_dir, keywords)
        api_key = os.getenv("TIINGO_API_KEY")
        if not api_key:
            raise ValueError(
                "TIINGO_API_KEY not found in .env. "
                "Get key from: https://www.tiingo.com/account/api/token"
            )
        self.api_key = api_key
        self.base_url = "https://api.tiingo.com/tiingo/news"
        logger.info("TiingoSource initialized")

    def get_name(self) -> str:
        return "tiingo"

    def fetch_articles_for_ticker(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        use_cache: bool = True,
    ) -> List[Dict]:
        if use_cache:
            cached = self._get_cached_articles(ticker, start_date, end_date)
            if cached:
                return cached
        try:
            params = {
                "tickers": ticker,
                "startDate": start_date,
                "endDate": end_date,
                "token": self.api_key,
            }
            r = requests.get(self.base_url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            articles = self._normalize_articles(data, ticker)
            if use_cache and articles:
                self._save_articles(ticker, articles)
            return articles
        except Exception as e:
            logger.warning(f"Tiingo fetch_articles_for_ticker {ticker}: {e}")
            return []

    def _normalize_articles(self, raw: List[Dict], ticker: str) -> List[Dict]:
        out = []
        for a in raw:
            published = a.get("publishedDate") or a.get("published") or a.get("crawlDate", "")
            if isinstance(published, datetime):
                published = published.strftime("%Y-%m-%dT%H:%M:%SZ")
            out.append({
                "title": a.get("title", ""),
                "description": a.get("description", a.get("summary", ""))[:500] if a.get("description") or a.get("summary") else "",
                "content": a.get("article", a.get("description", a.get("summary", ""))),
                "url": a.get("url", ""),
                "publishedAt": published,
                "source": "tiingo",
                "ticker": ticker,
                "fetched_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
        return out
