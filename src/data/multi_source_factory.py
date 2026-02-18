"""
Multi-Source Alpha Pipeline - Unified Data Factory
Merges existing historical framework with new live data feeds.

Main entry point:
    get_data(ticker, start_date, end_date, include_news=True, use_ibkr_for_intraday=False)

Returns a DataFrame with columns:
    [timestamp, ticker, price, volume, sentiment_score, source_origin]
"""

import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import requests
import backoff
from dotenv import load_dotenv


logger = logging.getLogger(__name__)

# Load environment variables once at import time
load_dotenv()


# ============================================================================
# Gemini sentiment scorer
# ============================================================================

class GeminiScorer:
    """
    Strict JSON sentiment scorer using Gemini.

    Output format (always):
        {"ticker": str, "score": float, "relevance": float}
    """

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.5-flash-lite"):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment (.env).")

        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as e:
            raise ImportError("google-generativeai is required for GeminiScorer. Install with 'pip install google-generativeai'.") from e

        genai.configure(api_key=self.api_key)
        self._genai = genai
        self._model = genai.GenerativeModel(model_name)

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        max_time=30,
    )
    def score(self, text: str, ticker: str) -> Dict[str, float]:
        """
        Score news text and return strict JSON:
            {"ticker": str, "score": float, "relevance": float}

        score      : sentiment in [-1.0, 1.0]
        relevance  : AI supply chain relevance in [0.0, 1.0]
        """
        if not text or not text.strip():
            return {"ticker": ticker.upper(), "score": 0.0, "relevance": 0.0}

        prompt = f"""
You are a financial sentiment and relevance scorer.
Return ONLY a valid JSON object with this exact structure:
{{
  "ticker": "{ticker.upper()}",
  "score": <float between -1.0 and 1.0>,
  "relevance": <float between 0.0 and 1.0>
}}

Where:
- score: overall news sentiment for the ticker (-1.0 = very negative, 0.0 = neutral, 1.0 = very positive)
- relevance: how relevant this article is to the ticker's AI supply chain exposure (0.0 = not related, 1.0 = highly related)

Article text (truncated if very long):
{text[:2000]}

Return ONLY the JSON object, without backticks or commentary.
"""
        try:
            response = self._model.generate_content(prompt)
            raw = (response.text or "").strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                # e.g. ```json\n{...}\n```
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                raw = raw.replace("json", "", 1).strip()

            import json

            parsed = json.loads(raw)
            # Validate and normalize
            ticker_out = str(parsed.get("ticker", ticker)).upper()
            score = float(parsed.get("score", 0.0))
            relevance = float(parsed.get("relevance", 0.0))

            score = max(-1.0, min(1.0, score))
            relevance = max(0.0, min(1.0, relevance))

            return {"ticker": ticker_out, "score": score, "relevance": relevance}
        except Exception as e:
            logger.warning(f"Gemini scoring failed for {ticker}: {e} - returning neutral.")
            return {"ticker": ticker.upper(), "score": 0.0, "relevance": 0.0}


# ============================================================================
# News fetchers (Marketaux & Tiingo)
# ============================================================================

class MarketauxFetcher:
    """Marketaux news client (English, highly relevant articles)."""

    BASE_URL = "https://api.marketaux.com/v1"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("MARKETAUX_API_KEY")
        if not self.api_key:
            raise ValueError("MARKETAUX_API_KEY not found in environment (.env).")

    @backoff.on_exception(
        backoff.expo,
        requests.exceptions.RequestException,
        max_tries=3,
        max_time=30,
    )
    def fetch_news(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Fetch Marketaux news for a ticker.

        Returns list of standardized article dicts.
        """
        articles: List[Dict] = []
        page = 1

        while len(articles) < limit:
            params = {
                "api_token": self.api_key,
                "symbols": ticker,
                "language": "en",
                "filter_entities": "true",  # Only highly relevant
                "published_after": start_date,
                "published_before": end_date,
                "page": page,
                "limit": min(100, limit - len(articles)),
            }

            resp = requests.get(f"{self.BASE_URL}/news/all", params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            batch = data.get("data") or []
            if not batch:
                break

            for art in batch:
                articles.append(
                    {
                        "title": art.get("title", "") or "",
                        "description": art.get("description", "") or "",
                        "content": art.get("text", "") or "",
                        "url": art.get("url", "") or "",
                        "publishedAt": art.get("published_at", "") or "",
                        "source": "Marketaux",
                        "ticker": ticker.upper(),
                        "fetched_at": datetime.utcnow().isoformat(),
                    }
                )

            meta = data.get("meta") or {}
            found = int(meta.get("found", 0))
            if found <= len(articles):
                break

            page += 1

        logger.info(f"Marketaux: fetched {len(articles)} articles for {ticker}.")
        return articles[:limit]


class TiingoFetcher:
    """Tiingo news client for broad tagging & historical backfill."""

    BASE_URL = "https://api.tiingo.com"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TIINGO_API_KEY")
        if not self.api_key:
            raise ValueError("TIINGO_API_KEY not found in environment (.env).")

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Token {self.api_key}",
        }

    @backoff.on_exception(
        backoff.expo,
        requests.exceptions.RequestException,
        max_tries=3,
        max_time=30,
    )
    def fetch_news(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Fetch Tiingo news for a ticker.

        Returns list of standardized article dicts.
        """
        url = f"{self.BASE_URL}/tiingo/news"
        params = {
            "tickers": ticker,
            "startDate": start_date,
            "endDate": end_date,
            "limit": limit,
        }

        resp = requests.get(url, headers=self.headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json() or []

        articles: List[Dict] = []
        for art in data:
            articles.append(
                {
                    "title": art.get("title", "") or "",
                    "description": art.get("description", "") or "",
                    "content": art.get("article", "") or "",
                    "url": art.get("url", "") or "",
                    "publishedAt": art.get("publishedDate", "") or "",
                    "source": "Tiingo",
                    "ticker": ticker.upper(),
                    "fetched_at": datetime.utcnow().isoformat(),
                }
            )

        logger.info(f"Tiingo: fetched {len(articles)} articles for {ticker}.")
        return articles


# ============================================================================
# Sentiment normalization
# ============================================================================

def normalize_sentiment(score: float, source: str) -> float:
    """
    Normalize sentiment to the common [-1.0, 1.0] scale.

    This is primarily defensive: Gemini already returns -1..1,
    but we keep the hook to map any vendor-native scores if needed.
    """
    try:
        value = float(score)
    except Exception:
        value = 0.0

    # For now, all sources are treated as already on -1..1
    return max(-1.0, min(1.0, value))


# ============================================================================
# Price data (yfinance + optional IBKR)
# ============================================================================

def _init_yfinance_cache() -> None:
    """
    Initialize yfinance cache directory (~/.cache/py-yfinance) to
    prevent SQLite database errors on first use.
    """
    cache_dir = Path.home() / ".cache" / "py-yfinance"
    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Initialized yfinance cache at {cache_dir}")


@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=3,
    max_time=30,
)
def _fetch_price_yfinance(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Daily OHLCV from yfinance."""
    try:
        import yfinance as yf  # type: ignore
    except ImportError as e:
        raise ImportError("yfinance is required for price data. Install with 'pip install yfinance'.") from e

    stock = yf.Ticker(ticker)
    df = stock.history(start=start_date, end=end_date, interval="1d")

    if df.empty:
        logger.warning(f"yfinance returned no data for {ticker}.")
        return pd.DataFrame()

    df.columns = [c.lower() for c in df.columns]
    df.reset_index(inplace=True)
    df.rename(columns={"date": "timestamp"}, inplace=True)

    df["ticker"] = ticker.upper()
    df["source_origin"] = "yfinance"

    out = df[["timestamp", "ticker", "close", "volume", "source_origin"]].copy()
    out.rename(columns={"close": "price"}, inplace=True)
    return out


_ibkr_client_id_counter = 99  # start at 99 as requested


def _next_ibkr_client_id() -> int:
    """Rotate IBKR client IDs starting at 99."""
    global _ibkr_client_id_counter
    cid = _ibkr_client_id_counter
    _ibkr_client_id_counter = (_ibkr_client_id_counter + 1) % 1000
    if _ibkr_client_id_counter < 99:
        _ibkr_client_id_counter = 99
    return cid


def _fetch_price_ibkr(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch daily price/volume from IBKR.

    Volume handling: apply x100 multiplier consistent with Tick ID 8 spec.
    """
    try:
        from ib_insync import IB, Stock, util  # type: ignore
        import nest_asyncio  # type: ignore
    except ImportError as e:
        raise ImportError("ib_insync and nest_asyncio are required for IBKR data.") from e

    nest_asyncio.apply()
    client_id = _next_ibkr_client_id()

    ib = IB()
    try:
        ib.connect("127.0.0.1", 7497, clientId=client_id)
        contract = Stock(ticker, "SMART", "USD")

        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_date or "",
            durationStr="2 Y",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
        if not bars:
            logger.warning(f"IBKR returned no data for {ticker}.")
            return pd.DataFrame()

        df = util.df(bars)
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df.set_index("date", inplace=True)
        df = df[df.index >= pd.Timestamp(start_date)]

        # x100 volume multiplier per Tick ID 8 convention
        if "volume" in df.columns:
            df["volume"] = df["volume"] * 100

        df.reset_index(inplace=True)
        df.rename(columns={"date": "timestamp", "close": "price"}, inplace=True)
        df["ticker"] = ticker.upper()
        df["source_origin"] = "ibkr"

        return df[["timestamp", "ticker", "price", "volume", "source_origin"]]
    except Exception as e:
        logger.error(f"IBKR price fetch failed for {ticker}: {e}")
        return pd.DataFrame()
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass


def _fetch_price(
    ticker: str,
    start_date: str,
    end_date: str,
    use_ibkr_for_intraday: bool,
) -> pd.DataFrame:
    """
    Wrapper for price data.

    For now we always return daily bars; when use_ibkr_for_intraday is True,
    we prefer IBKR over yfinance.
    """
    if use_ibkr_for_intraday:
        df = _fetch_price_ibkr(ticker, start_date, end_date)
        if not df.empty:
            return df
        # Fallback to yfinance if IBKR fails
        logger.info(f"Falling back to yfinance for {ticker} after IBKR failure.")
    return _fetch_price_yfinance(ticker, start_date, end_date)


# ============================================================================
# News + sentiment
# ============================================================================

def _fetch_news_with_sentiment(
    ticker: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Fetch news from Marketaux (primary) and Tiingo (backfill),
    score each article with Gemini, normalize sentiment, and
    return a DataFrame with [timestamp, ticker, sentiment_score, relevance, source_origin].
    """
    all_articles: List[Dict] = []

    # Marketaux (primary)
    try:
        marketaux = MarketauxFetcher()
        all_articles.extend(marketaux.fetch_news(ticker, start_date, end_date, limit=100))
    except Exception as e:
        logger.warning(f"Marketaux fetch failed for {ticker}: {e}")

    # Tiingo (secondary / backfill)
    try:
        tiingo = TiingoFetcher()
        all_articles.extend(tiingo.fetch_news(ticker, start_date, end_date, limit=50))
    except Exception as e:
        logger.warning(f"Tiingo fetch failed for {ticker}: {e}")

    if not all_articles:
        return pd.DataFrame()

    scorer = GeminiScorer()
    scored_rows: List[Dict] = []

    for art in all_articles:
        try:
            # Use title + description primarily; fall back to content
            text = (art.get("title", "") or "") + " " + (art.get("description", "") or "")
            if not text.strip():
                text = (art.get("content", "") or "")[:500]

            score_obj = scorer.score(text, ticker)
            sentiment = normalize_sentiment(score_obj["score"], art.get("source", "Gemini"))

            ts_raw = art.get("publishedAt") or art.get("fetched_at") or datetime.utcnow().isoformat()
            try:
                ts = pd.to_datetime(ts_raw)
            except Exception:
                ts = pd.to_datetime(datetime.utcnow())

            scored_rows.append(
                {
                    "timestamp": ts,
                    "ticker": ticker.upper(),
                    "sentiment_score": sentiment,
                    "relevance": float(score_obj.get("relevance", 0.0)),
                    "source_origin": (art.get("source") or "unknown").lower(),
                }
            )
        except Exception as e:
            logger.warning(f"Failed to score news article for {ticker}: {e}")

    if not scored_rows:
        return pd.DataFrame()

    df = pd.DataFrame(scored_rows)
    df.sort_values("timestamp", inplace=True)
    return df


# ============================================================================
# Merge & self-healing storage
# ============================================================================

def _merge_price_and_news(
    price_df: pd.DataFrame,
    news_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """
    Merge price and news frames to:
        [timestamp, ticker, price, volume, sentiment_score, source_origin]

    Strategy:
      - Start from price_df (daily bars).
      - Aggregate news sentiment by calendar day, then map to the nearest
        trading day >= news date (forward to next bar).
    """
    if price_df is None or price_df.empty:
        return pd.DataFrame()

    df = price_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp", inplace=True)

    # Ensure required columns exist
    if "sentiment_score" not in df.columns:
        df["sentiment_score"] = 0.0

    if news_df is not None and not news_df.empty:
        news_df = news_df.copy()
        news_df["timestamp"] = pd.to_datetime(news_df["timestamp"])
        news_df.set_index("timestamp", inplace=True)

        # Daily average of sentiment
        daily = news_df.resample("D")["sentiment_score"].mean().dropna()

        for date, sentiment in daily.items():
            # Find first trading bar on/after this date
            idx = df.index[df.index.date >= date.date()]
            if len(idx) > 0:
                df.loc[idx[0], "sentiment_score"] = float(sentiment)

    df.reset_index(inplace=True)

    # Final column ordering
    required_cols = ["timestamp", "ticker", "price", "volume", "sentiment_score", "source_origin"]
    for col in required_cols:
        if col not in df.columns:
            if col == "sentiment_score":
                df[col] = 0.0
            elif col == "source_origin":
                df[col] = "unknown"
            else:
                logger.warning(f"Missing column {col} in merged data.")

    return df[required_cols]


def _append_to_historical(ticker: str, df: pd.DataFrame) -> None:
    """
    Self-healing storage:
      - Append/merge latest data into data/historical/{TICKER}.csv
      - De-duplicate by timestamp and sort.
    """
    if df is None or df.empty:
        return

    historical_dir = Path("data/historical")
    historical_dir.mkdir(parents=True, exist_ok=True)

    path = historical_dir / f"{ticker.upper()}.csv"

    if path.exists():
        try:
            existing = pd.read_csv(path, parse_dates=["timestamp"])
            combined = pd.concat([existing, df], ignore_index=True)
            combined.drop_duplicates(subset=["timestamp"], keep="last", inplace=True)
            combined.sort_values("timestamp", inplace=True)
            combined.to_csv(path, index=False)
            logger.info(f"Updated historical file {path} (rows={len(combined)}).")
            return
        except Exception as e:
            logger.warning(f"Failed to merge with existing {path}: {e} - overwriting.")

    df.to_csv(path, index=False)
    logger.info(f"Created historical file {path} (rows={len(df)}).")


# ============================================================================
# Public API
# ============================================================================

def get_data(
    ticker: str,
    start_date: str,
    end_date: str,
    include_news: bool = True,
    use_ibkr_for_intraday: bool = False,
) -> pd.DataFrame:
    """
    Unified data fetcher for the Multi-Source Alpha Pipeline.

    Args:
        ticker: Stock ticker symbol.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        include_news: If True, fetch and score news (Marketaux + Tiingo + Gemini).
        use_ibkr_for_intraday: If True, prefer IBKR for price/volume (with x100 volume multiplier).

    Returns:
        DataFrame with columns:
            [timestamp, ticker, price, volume, sentiment_score, source_origin]
        ready for weekly rebalancing logic.
    """
    logger.info(f"Multi-source get_data for {ticker} from {start_date} to {end_date}")

    # Ensure yfinance cache is ready before any price calls
    _init_yfinance_cache()

    price_df = _fetch_price(ticker, start_date, end_date, use_ibkr_for_intraday)
    if price_df.empty:
        logger.warning(f"No price data available for {ticker}.")
        return pd.DataFrame(columns=["timestamp", "ticker", "price", "volume", "sentiment_score", "source_origin"])

    news_df: Optional[pd.DataFrame] = None
    if include_news:
        news_df = _fetch_news_with_sentiment(ticker, start_date, end_date)

    merged = _merge_price_and_news(price_df, news_df)

    # Self-healing historical storage
    _append_to_historical(ticker, merged)

    return merged
