"""
Multi-Strategy News Alpha Engine.
- Sentiment: FinBERT (ProsusAI/finbert) on headlines/bodies from data/news/{ticker}_news.json.
- Events: spacy en_core_web_md + EventDetector (Earnings, M&A, Lawsuit, FDA, CEO Change).
- Strategies: A Buzz (24h count > 2*std above 20d mean), B Surprise (current - 30d baseline),
  C Sector-relative (top 10%), D Event-driven (48h priority weight).
- Deduplication: Levenshtein fuzzy match on headlines (DualStream / Marketaux + Tiingo).
- News warm-up: Strategy B uses 30-day baseline; cold start = neutral (0.5).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional: FinBERT (transformers). Offline: use ./models/finbert if present.
# ---------------------------------------------------------------------------
try:
    from transformers import pipeline as hf_pipeline
    HAS_FINBERT = True
except ImportError:
    HAS_FINBERT = False

_FINBERT_PIPELINE = None
_FINBERT_LOCAL_PATH = None  # Set once: Path to models/finbert if exists


def _finbert_local_path() -> Path | None:
    """Check for local FinBERT cache (e.g. ./models/finbert) for offline use."""
    for base in (Path(__file__).resolve().parent.parent.parent, Path(".").resolve()):
        candidate = base / "models" / "finbert"
        if (candidate / "config.json").exists():
            return candidate
    return None


def _get_finbert_pipeline():
    global _FINBERT_PIPELINE, _FINBERT_LOCAL_PATH
    if _FINBERT_PIPELINE is not None:
        return _FINBERT_PIPELINE
    if not HAS_FINBERT:
        return None
    # Prefer local offline cache to avoid network hang
    if _FINBERT_LOCAL_PATH is None:
        _FINBERT_LOCAL_PATH = _finbert_local_path()
    model_id = str(_FINBERT_LOCAL_PATH) if _FINBERT_LOCAL_PATH else "ProsusAI/finbert"
    try:
        if _FINBERT_LOCAL_PATH:
            _FINBERT_PIPELINE = hf_pipeline(
                "sentiment-analysis",
                model=model_id,
                tokenizer=model_id,
                truncation=True,
                max_length=512,
                model_kwargs={"local_files_only": True},
                tokenizer_kwargs={"local_files_only": True},
            )
            logger.info("FinBERT loaded from local %s", model_id)
        else:
            _FINBERT_PIPELINE = hf_pipeline(
                "sentiment-analysis",
                model="ProsusAI/finbert",
                tokenizer="ProsusAI/finbert",
                truncation=True,
                max_length=512,
            )
    except Exception as e:
        logger.warning("FinBERT pipeline failed: %s", e)
        _FINBERT_PIPELINE = None  # ensure we don't retry on next call
        if not _FINBERT_LOCAL_PATH:
            logger.info(
                "To run offline, download FinBERT to ./models/finbert (e.g. clone HuggingFace ProsusAI/finbert)."
            )
    return _FINBERT_PIPELINE


def sentiment_finbert(text: str) -> float:
    """
    Run FinBERT on a single text (headline or body). Returns sentiment in [0, 1]
    (0=negative, 0.5=neutral, 1=positive). Raw FinBERT labels: positive/negative/neutral.
    """
    pipe = _get_finbert_pipeline()
    if pipe is None or not text or not str(text).strip():
        return 0.5
    try:
        out = pipe(str(text)[:4000], truncation=True, max_length=512)
        if not out:
            return 0.5
        res = out[0]
        label = (res.get("label") or "").lower()
        score = float(res.get("score", 0.5))
        if "positive" in label:
            return 0.5 + 0.5 * score
        if "negative" in label:
            return 0.5 - 0.5 * score
        return 0.5
    except Exception as e:
        logger.debug("FinBERT error: %s", e)
        return 0.5


# ---------------------------------------------------------------------------
# Optional: spacy EventDetector
# ---------------------------------------------------------------------------
try:
    import spacy
    HAS_SPACY = True
except ImportError:
    HAS_SPACY = False

_NLP = None

# High-impact phrases for Strategy D (institutional-grade Event-Driven; override technical choppiness for 48h)
# Earnings: beat/miss, guidance, earnings call
EARNINGS_PHRASES = [
    "beat estimates", "missed revenue", "guidance hike", "earnings call",
    "earnings announcement", "earnings report", "quarterly earnings",
]
# M&A: acquisition, merger, buyout, takeover bid
MA_PHRASES = ["acquisition", "merger", "buyout", "takeover bid", "m&a", "takeover"]
# Leadership: CEO/CFO/board
LEADERSHIP_PHRASES = ["ceo step down", "new cfo", "board reshuffle", "ceo change", "ceo resignation", "new ceo", "chief executive"]
HIGH_IMPACT_PHRASES: list[str] = (
    EARNINGS_PHRASES
    + MA_PHRASES
    + ["lawsuit", "litigation", "fda approval", "fda rejection"]
    + LEADERSHIP_PHRASES
)
EVENT_LABELS = {"Earnings", "M&A", "Lawsuit", "FDA", "Leadership"}


class EventDetector:
    """
    Flag events: Earnings, M&A, Lawsuit, FDA using NER and phrase matching.
    Uses spacy en_core_web_md. Call load_nlp() once (e.g. at module load or first use).
    """

    def __init__(self, model: str = "en_core_web_md"):
        self.model_name = model
        self._nlp = None

    def load_nlp(self) -> bool:
        if not HAS_SPACY:
            return False
        global _NLP
        if _NLP is None:
            try:
                _NLP = spacy.load(self.model_name)
            except OSError:
                try:
                    import subprocess
                    subprocess.run(["python", "-m", "spacy", "download", self.model_name], check=True)
                    _NLP = spacy.load(self.model_name)
                except Exception as e:
                    logger.warning("spacy load failed: %s", e)
                    return False
        self._nlp = _NLP
        return self._nlp is not None

    def detect(self, text: str) -> dict[str, bool]:
        """
        Returns dict: {"Earnings": bool, "M&A": bool, "Lawsuit": bool, "FDA": bool, "Leadership": bool, "high_impact": bool}.
        high_impact = True if any HIGH_IMPACT_PHRASES match or NER suggests catalyst.
        Institutional-grade phrase mappings: Earnings (beat estimates, guidance hike, earnings call),
        M&A (acquisition, merger, buyout, takeover bid), Leadership (CEO step down, new CFO, board reshuffle).
        """
        result = {k: False for k in EVENT_LABELS}
        result["high_impact"] = False
        if not text or not str(text).strip():
            return result
        text_lower = (text or "")[:10000].lower()
        # Phrase matching (Earnings, M&A, Leadership, Lawsuit, FDA)
        if any(phrase in text_lower for phrase in EARNINGS_PHRASES):
            result["Earnings"] = True
        if any(phrase in text_lower for phrase in MA_PHRASES):
            result["M&A"] = True
        if any(phrase in text_lower for phrase in LEADERSHIP_PHRASES):
            result["Leadership"] = True
        if any(x in text_lower for x in ("lawsuit", "litigation", "sued")):
            result["Lawsuit"] = True
        if "fda" in text_lower and any(x in text_lower for x in ("approval", "rejection", "approve", "reject")):
            result["FDA"] = True
        for phrase in HIGH_IMPACT_PHRASES:
            if phrase in text_lower:
                result["high_impact"] = True
                break
        if any(result[k] for k in EVENT_LABELS):
            result["high_impact"] = True
        # NER (optional): ORG, EVENT, etc. can reinforce
        if self._nlp is None:
            self.load_nlp()
        if self._nlp is not None:
            try:
                doc = self._nlp(text_lower[:2000])
                for ent in doc.ents:
                    if ent.label_ == "EVENT" and "earnings" in ent.text.lower():
                        result["Earnings"] = True
                        result["high_impact"] = True
            except Exception:
                pass
        return result


# ---------------------------------------------------------------------------
# Deduplication (Levenshtein)
# ---------------------------------------------------------------------------
try:
    import Levenshtein
    HAS_LEVENSHTEIN = True
except ImportError:
    HAS_LEVENSHTEIN = False

DEDUP_SIMILARITY_THRESHOLD = 0.85  # ratio; above = duplicate


def _headline_similarity(a: str, b: str) -> float:
    if not HAS_LEVENSHTEIN or not a or not b:
        return 0.0
    a, b = str(a).strip(), str(b).strip()
    if a == b:
        return 1.0
    return Levenshtein.ratio(a, b)


def deduplicate_articles(articles: list[dict], headline_key: str = "title") -> list[dict]:
    """
    Deduplicate by headline fuzzy matching (Levenshtein). Keeps first occurrence.
    Used for DualStream (Marketaux + Tiingo) to avoid double-counting.
    """
    if not articles or not HAS_LEVENSHTEIN:
        return articles
    out = []
    for art in articles:
        h = (art.get(headline_key) or "").strip()
        is_dup = False
        for kept in out:
            if _headline_similarity(h, (kept.get(headline_key) or "").strip()) >= DEDUP_SIMILARITY_THRESHOLD:
                is_dup = True
                break
        if not is_dup:
            out.append(art)
    return out


# ---------------------------------------------------------------------------
# Load news from data/news/{ticker}_news.json
# ---------------------------------------------------------------------------
def load_ticker_news(news_dir: Path | str, ticker: str, dedupe: bool = True) -> list[dict]:
    """
    Load articles for a ticker from data/news/{ticker}_news.json.
    When dedupe=True (default), Levenshtein fuzzy matching on headlines is applied
    so we do not process redundant data (e.g. DualStream Marketaux + Tiingo duplicates).
    """
    path = Path(news_dir) / f"{ticker}_news.json"
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Load news %s: %s", path, e)
        return []
    if not isinstance(data, list):
        data = [data] if isinstance(data, dict) else []
    if dedupe:
        data = deduplicate_articles(data, headline_key="title")
    return data


def _parse_date(published: Any) -> Optional[pd.Timestamp]:
    if published is None:
        return None
    try:
        return pd.to_datetime(published)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Strategy A: News Momentum (Buzz)
# ---------------------------------------------------------------------------
def strategy_buzz(
    articles: list[dict],
    as_of: pd.Timestamp,
    window_24h: bool = True,
    mean_days: int = 20,
    std_threshold: float = 2.0,
) -> tuple[float, bool]:
    """
    Rolling 24h count of news items. Signal: Buzz Multiplier active if current count
    > 2 std above 20-day mean. Returns (normalized_buzz_ratio, multiplier_active).
    """
    if not articles:
        return 0.0, False
    dates = [_parse_date(a.get("publishedAt")) for a in articles]
    valid = [(a, d) for a, d in zip(articles, dates) if d is not None]
    if not valid:
        return 0.0, False
    as_of = pd.Timestamp(as_of)
    # Last 24h count
    cutoff_24h = as_of - pd.Timedelta(hours=24)
    count_24h = sum(1 for _, d in valid if d >= cutoff_24h)
    # Last 20 days of daily counts (for mean/std)
    daily_counts = []
    for day_offset in range(mean_days):
        day_start = as_of - pd.Timedelta(days=day_offset + 1)
        day_end = as_of - pd.Timedelta(days=day_offset)
        daily_counts.append(sum(1 for _, d in valid if day_start <= d < day_end))
    if len(daily_counts) < 5:
        return (min(1.0, count_24h / 10.0)), False
    mean_c = np.mean(daily_counts)
    std_c = np.std(daily_counts) or 1e-6
    threshold = mean_c + std_threshold * std_c
    multiplier_active = count_24h > threshold
    # Normalized ratio for scoring: cap at 2x threshold
    ratio = count_24h / (threshold + 1e-6)
    normalized = min(1.0, ratio / 2.0)
    return normalized, multiplier_active


# ---------------------------------------------------------------------------
# Strategy B: News Surprise (Sentiment Delta)
# ---------------------------------------------------------------------------
SENTIMENT_BASELINE_DAYS = 30


def strategy_surprise(
    articles_with_sentiment: list[tuple[dict, float]],
    as_of: pd.Timestamp,
    baseline_days: int = SENTIMENT_BASELINE_DAYS,
    recent_days: int = 7,
) -> float:
    """
    Surprise = Current_Sentiment - Baseline_Sentiment.
    Surprise Lag Rule: Baseline uses the *previous* 30 days only (excludes as_of).
    Current = recent_days (e.g. 1 or 5) mean; Baseline = [as_of - 30d, as_of) exclusive.
    Cold start (< 5 baseline obs): return 0.5 (neutral). Returns value in [0, 1] (0.5 = no surprise).
    """
    if not articles_with_sentiment:
        return 0.5
    as_of = pd.Timestamp(as_of)
    cutoff_baseline = as_of - pd.Timedelta(days=baseline_days)
    cutoff_recent = as_of - pd.Timedelta(days=recent_days)
    # 1-day lag: baseline = previous 30 days only (exclude today/as_of)
    baseline_vals = [s for a, s in articles_with_sentiment if (d := _parse_date(a.get("publishedAt"))) is not None and cutoff_baseline <= d < as_of]
    recent_vals = [s for a, s in articles_with_sentiment if _parse_date(a.get("publishedAt")) is not None and _parse_date(a.get("publishedAt")) >= cutoff_recent]
    if len(baseline_vals) < 5:
        return 0.5
    baseline_mean = float(np.mean(baseline_vals))
    current_mean = float(np.mean(recent_vals)) if recent_vals else baseline_mean
    surprise = current_mean - baseline_mean
    # Map to [0,1]: 0.5 + clip(surprise, -0.5, 0.5)
    return float(np.clip(0.5 + surprise, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Strategy C: Cross-Sectional (Sector Relative)
# ---------------------------------------------------------------------------
# Standard sector mapping for relative sentiment: Tech/Software vs Semiconductors.
# Relative logic: e.g. NVDA sentiment 0.6 vs AMD 0.3 → NVDA gets sector bonus (top 10%).
DEFAULT_SECTOR_MAP: dict[str, str] = {
    "AAPL": "Tech/Software",
    "MSFT": "Tech/Software",
    "GOOGL": "Tech/Software",
    "META": "Tech/Software",
    "TSLA": "Tech/Software",
    "NVDA": "Semiconductors",
    "AMD": "Semiconductors",
}


def strategy_sector_relative(
    ticker_sentiments: dict[str, float],
    ticker: str,
    sector_map: Optional[dict[str, str]] = None,
    top_pct: float = 0.10,
) -> float:
    """
    Bonus if ticker is in top 10% of its sector by sentiment. If sector_map is None,
    use single group (all tickers). Returns 1.0 if top 10%, 0.0 else (or gradient).
    """
    if not ticker_sentiments or ticker not in ticker_sentiments:
        return 0.5
    sector_map = sector_map or {}
    sector = sector_map.get(ticker, "Default")
    sector_tickers = [t for t, s in sector_map.items() if sector_map.get(t) == sector]
    if not sector_tickers:
        sector_tickers = list(ticker_sentiments.keys())
    sector_sentiments = [ticker_sentiments[t] for t in sector_tickers if t in ticker_sentiments]
    if not sector_sentiments:
        return 0.5
    threshold = np.percentile(sector_sentiments, 100 * (1 - top_pct))
    return 1.0 if ticker_sentiments[ticker] >= threshold else 0.0


# ---------------------------------------------------------------------------
# Strategy D: Event-Driven (48h Priority Weight)
# ---------------------------------------------------------------------------
EVENT_PRIORITY_HOURS = 48


def strategy_event_priority(
    articles_with_events: list[tuple[dict, dict]],
    as_of: pd.Timestamp,
    priority_hours: int = EVENT_PRIORITY_HOURS,
) -> float:
    """
    If a high-impact event detected within last 48h, return 1.0 (priority weight);
    else 0.0. Overrides technical choppiness when 1.0.
    """
    as_of = pd.Timestamp(as_of)
    cutoff = as_of - pd.Timedelta(hours=priority_hours)
    for art, events in articles_with_events:
        d = _parse_date(art.get("publishedAt"))
        if d is not None and d >= cutoff and events.get("high_impact"):
            return 1.0
    return 0.0


# ---------------------------------------------------------------------------
# News Composite (combine A–D)
# ---------------------------------------------------------------------------
def compute_news_composite(
    news_dir: Path | str,
    ticker: str,
    as_of: pd.Timestamp,
    sector_sentiments: Optional[dict[str, float]] = None,
    sector_map: Optional[dict[str, str]] = None,
    use_finbert: bool = True,
    use_events: bool = True,
    signal_horizon_days: int = 5,
) -> dict[str, Any]:
    """
    Load ticker news, run FinBERT sentiment, EventDetector, then strategies A–D.
    signal_horizon_days: 1 = 1-day aggregation for current sentiment/surprise, 5 = 5-day (grid search: 1 vs 5).
    Returns dict: news_composite (0–1), buzz_active, surprise, sector_top10, event_priority,
    sentiment_current, sentiment_baseline, strategies.
    Warm-up: Strategy B uses 30-day baseline; cold start = 0.5.
    """
    news_dir = Path(news_dir)
    articles = load_ticker_news(news_dir, ticker, dedupe=True)
    if not articles:
        return {
            "news_composite": 0.5,
            "buzz_active": False,
            "surprise": 0.5,
            "sector_top10": 0.5,
            "event_priority": 0.0,
            "sentiment_current": 0.5,
            "sentiment_baseline": 0.5,
            "strategies": {},
        }
    # FinBERT on title + description (or content)
    articles_with_sentiment: list[tuple[dict, float]] = []
    articles_with_events: list[tuple[dict, dict]] = []
    detector = EventDetector()
    detector.load_nlp()
    for a in articles:
        title = (a.get("title") or "").strip()
        body = (a.get("description") or a.get("content") or "").strip()
        text = title + " " + (body[:500] if body else "")
        if use_finbert:
            sent = sentiment_finbert(text)
        else:
            sent = 0.5
        articles_with_sentiment.append((a, sent))
        if use_events:
            ev = detector.detect(text)
            articles_with_events.append((a, ev))
    # Strategy A
    buzz_norm, buzz_active = strategy_buzz(articles, as_of, window_24h=True, mean_days=20, std_threshold=2.0)
    # Strategy B (30-day baseline; current = signal_horizon_days for grid: 1 vs 5)
    surprise = strategy_surprise(
        articles_with_sentiment, as_of,
        baseline_days=SENTIMENT_BASELINE_DAYS,
        recent_days=signal_horizon_days,
    )
    # Strategy C (needs sector_sentiments for universe)
    sector_top10 = 0.5
    if sector_sentiments is not None:
        sector_top10 = strategy_sector_relative(sector_sentiments, ticker, sector_map=sector_map, top_pct=0.10)
    # Strategy D
    event_priority = strategy_event_priority(articles_with_events, as_of, priority_hours=EVENT_PRIORITY_HOURS)
    # Current / baseline for reporting (Surprise Lag Rule: baseline excludes as_of; recent = signal_horizon_days)
    as_of_ts = pd.Timestamp(as_of)
    baseline_cut = as_of_ts - pd.Timedelta(days=SENTIMENT_BASELINE_DAYS)
    recent_cut = as_of_ts - pd.Timedelta(days=signal_horizon_days)
    baseline_vals = [s for a, s in articles_with_sentiment if (d := _parse_date(a.get("publishedAt"))) is not None and baseline_cut <= d < as_of_ts]
    recent_vals = [s for a, s in articles_with_sentiment if (d := _parse_date(a.get("publishedAt"))) is not None and d >= recent_cut]
    sentiment_baseline = float(np.mean(baseline_vals)) if len(baseline_vals) >= 5 else 0.5
    sentiment_current = float(np.mean(recent_vals)) if recent_vals else sentiment_baseline
    # Composite: simple average of (buzz_norm, surprise, sector_top10, event_priority or 0.5)
    comp_vals = [buzz_norm, surprise, sector_top10, event_priority if event_priority > 0 else 0.5]
    news_composite = float(np.clip(np.mean(comp_vals), 0.0, 1.0))
    return {
        "news_composite": news_composite,
        "buzz_active": buzz_active,
        "surprise": surprise,
        "sector_top10": sector_top10,
        "event_priority": event_priority,
        "sentiment_current": sentiment_current,
        "sentiment_baseline": sentiment_baseline,
        "strategies": {"buzz": buzz_norm, "surprise": surprise, "sector": sector_top10, "event": event_priority},
    }
