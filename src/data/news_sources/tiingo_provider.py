"""
Tiingo News API provider.

Implements NewsDataSource (JSON cache) and NewsProvider (fetch_history, fetch_live, standardize_data).
Auth: Token in header. Params: tickers, startDate, endDate.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests

from src.data.news_base import NewsDataSource
from src.data.news_sources.base_provider import NewsProvider

logger = logging.getLogger(__name__)


class TiingoProvider(NewsDataSource, NewsProvider):
    """Tiingo news API: https://api.tiingo.com/tiingo/news."""

    def __init__(self, data_dir: Optional[str] = None, keywords: Optional[List[str]] = None):
        if data_dir is None:
            from src.core.config import NEWS_DIR
            data_dir = str(NEWS_DIR)
        super().__init__(data_dir, keywords)
        from src.core.config import TIINGO_API_KEY
        if not TIINGO_API_KEY:
            raise ValueError("TIINGO_API_KEY not set. Set it in .env or environment.")
        self.api_key = TIINGO_API_KEY
        self.base_url = "https://api.tiingo.com/tiingo/news"
        self._auth_header = {"Authorization": f"Token {self.api_key}"}

    def get_name(self) -> str:
        return "tiingo"

    def fetch_articles_for_ticker(
        self, ticker: str, start_date: str, end_date: str, use_cache: bool = True
    ) -> List[Dict]:
        """Fetch news for ticker in date range; check cache first, then Tiingo API."""
        if use_cache:
            cached = self._get_cached_articles(ticker, start_date, end_date)
            if cached:
                logger.info("Loaded %d cached Tiingo articles for %s", len(cached), ticker)
                return cached
        try:
            params = {
                "tickers": ticker,
                "startDate": start_date,
                "endDate": end_date,
            }
            resp = requests.get(
                self.base_url,
                params=params,
                headers=self._auth_header,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            articles_raw = data if isinstance(data, list) else data.get("data", data.get("results", []))
            if not isinstance(articles_raw, list):
                articles_raw = []
            out = []
            for a in articles_raw:
                pub = a.get("publishedDate") or a.get("published_at") or ""
                desc = a.get("description") or a.get("article") or ""
                body = a.get("article") or desc
                out.append({
                    "title": a.get("title", ""),
                    "description": desc,
                    "content": body,
                    "url": a.get("url", ""),
                    "publishedAt": pub,
                    "source": "tiingo",
                    "ticker": ticker,
                    "fetched_at": datetime.now().isoformat(),
                })
            return out
        except requests.HTTPError as e:
            if e.response is not None and (
                e.response.status_code == 429 or 500 <= e.response.status_code < 600
            ):
                raise
            logger.warning("Tiingo fetch failed for %s %s–%s: %s", ticker, start_date, end_date, e)
            return []
        except Exception as e:
            logger.warning("Tiingo fetch failed for %s %s–%s: %s", ticker, start_date, end_date, e)
            return []

    def fetch_history(self, ticker: str, start_date: str, end_date: str) -> List[Dict]:
        """Fetch historical news articles. Returns raw provider dicts."""
        return self.fetch_articles_for_ticker(ticker, start_date, end_date, use_cache=True)

    def fetch_live(self, ticker: str) -> List[Dict]:
        """Fetch latest news articles (last 24h)."""
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self.fetch_articles_for_ticker(ticker, yesterday, today, use_cache=False)

    def standardize_data(self, raw_data: List[Dict]) -> "pd.DataFrame":
        """Standardize raw provider dicts to canonical DataFrame schema: [Date, Ticker, Title, Body, Source]."""
        import pandas as pd
        if not raw_data:
            return pd.DataFrame(columns=["Date", "Ticker", "Title", "Body", "Source"])
        rows = []
        for a in raw_data:
            # Date from publishedAt or published_at only (no fetched_at or other field)
            pub = a.get("publishedAt") or a.get("published_at") or ""
            dt = pd.to_datetime(pub, errors="coerce")
            if pd.notna(dt) and getattr(dt, "tz", None) is not None:
                dt = dt.tz_convert("UTC").tz_localize(None)
            rows.append({
                "Date": dt,
                "Ticker": str(a.get("ticker", "")).upper(),
                "Title": str(a.get("title", "")),
                "Body": str(a.get("description", "") or a.get("content", "")),
                "Source": str(a.get("source", "tiingo")),
            })
        df = pd.DataFrame(rows, columns=["Date", "Ticker", "Title", "Body", "Source"])
        df = df.sort_values("Date", ascending=True).reset_index(drop=True)
        return df
