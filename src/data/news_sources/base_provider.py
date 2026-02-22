"""
Abstract base class for provider-agnostic news interface.

Independent of NewsDataSource in src/data/news_base.py (which handles JSON caching).
Providers may implement both.
"""
from abc import ABC, abstractmethod
from typing import Dict, List

import pandas as pd


class NewsProvider(ABC):
    """Abstract interface for fetching and standardizing news. No caching logic here."""

    @abstractmethod
    def fetch_history(self, ticker: str, start_date: str, end_date: str) -> List[Dict]:
        """Fetch historical news articles. Returns raw provider dicts."""
        ...

    @abstractmethod
    def fetch_live(self, ticker: str) -> List[Dict]:
        """Fetch latest news articles (last 24h)."""
        ...

    @abstractmethod
    def standardize_data(self, raw_data: List[Dict]) -> pd.DataFrame:
        """Standardize raw provider dicts to canonical DataFrame schema: [Date, Ticker, Title, Body, Source]."""
        ...
