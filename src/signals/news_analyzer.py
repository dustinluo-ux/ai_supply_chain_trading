"""
News Analyzer
Analyzes news articles using Gemini 2.5 Flash Lite API (Paid Tier) to extract supply chain relevance and sentiment
Reads from data/news/{ticker}_news.json format
Uses caching and returns None if no news found (no fallback values)

Now includes optional supply chain sentiment propagation.
"""
import os
import json
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
import logging
from pathlib import Path

from src.signals.gemini_news_analyzer import GeminiNewsAnalyzer
from src.signals.sentiment_propagator import SentimentPropagator, PropagatedSignal

logger = logging.getLogger(__name__)


class NewsAnalyzer:
    """
    Analyzes news articles for supply chain relevance and sentiment
    Wrapper around GeminiNewsAnalyzer for backward compatibility
    Returns None if no news found (no fallback/dummy values)
    """
    
    def __init__(
        self,
        news_dir: str = "data/news",
        cache_dir: str = "data/cache",
        lookback_days: int = 7,
        min_articles: int = 1,
        rate_limit_seconds: float = 0.5,
        enable_propagation: bool = True,
        propagation_tier1_weight: float = 0.5,
        propagation_tier2_weight: float = 0.2
    ):
        """
        Initialize News Analyzer
        
        Args:
            news_dir: Directory containing {ticker}_news.json files
            cache_dir: Directory for caching Gemini responses
            lookback_days: Number of days to look back for news analysis
            min_articles: Minimum number of articles required for analysis
            rate_limit_seconds: Delay between API calls (default 0.5s for ~300 RPM paid tier)
            enable_propagation: If True, propagate sentiment to related companies
            propagation_tier1_weight: Weight for direct relationships (default: 0.5)
            propagation_tier2_weight: Weight for indirect relationships (default: 0.2)
        """
        self.news_dir = Path(news_dir)
        self.lookback_days = lookback_days
        self.min_articles = min_articles
        self.enable_propagation = enable_propagation
        
        # Initialize Gemini News Analyzer (handles caching and rate limiting)
        try:
            self.gemini_analyzer = GeminiNewsAnalyzer(
                news_dir=news_dir,
                cache_dir=cache_dir,
                lookback_days=lookback_days,
                min_articles=min_articles,
                rate_limit_seconds=rate_limit_seconds
            )
            logger.info("NewsAnalyzer initialized with Gemini 2.5 Flash Lite (Paid Tier)")
        except Exception as e:
            logger.warning(f"Gemini not available: {e}. News analysis will return None.")
            self.gemini_analyzer = None
        
        # Initialize sentiment propagator if enabled
        if self.enable_propagation:
            try:
                self.propagator = SentimentPropagator(
                    tier1_weight=propagation_tier1_weight,
                    tier2_weight=propagation_tier2_weight,
                    max_degrees=2
                )
                logger.info("Sentiment propagation enabled")
            except Exception as e:
                logger.warning(f"Sentiment propagator not available: {e}. Propagation disabled.")
                self.propagator = None
                self.enable_propagation = False
        else:
            self.propagator = None
    
    def analyze_news_for_ticker(
        self, 
        ticker: str, 
        start_date: str, 
        end_date: str,
        include_propagated: bool = True
    ) -> Optional[Dict]:
        """
        Analyze news articles for a ticker and extract signals.
        Optionally propagates sentiment to related companies.
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            include_propagated: If True, include propagated signals in result
        
        Returns:
            Dict with keys: 
            - supply_chain_score, sentiment_score, confidence, relationship, reasoning (direct)
            - propagated_signals (list of propagated signals if include_propagated=True)
            Returns None if no articles found or analysis fails (NO FALLBACK VALUES)
        """
        if self.gemini_analyzer is None:
            logger.warning(f"Gemini analyzer not available for {ticker}, returning None")
            return None
        
        # Delegate to GeminiNewsAnalyzer (handles caching, rate limiting, and returns None if no news)
        result = self.gemini_analyzer.analyze_news_for_ticker(ticker, start_date, end_date)
        
        if result is None:
            logger.debug(f"No news analysis result for {ticker} from {start_date} to {end_date}")
            return None
        
        # Add source_type flag to distinguish direct vs propagated
        result['source_type'] = 'direct'
        
        # Propagate sentiment if enabled
        if self.enable_propagation and include_propagated and self.propagator:
            try:
                direct_signal, propagated_signals = self.propagator.propagate_from_news_result(
                    ticker, result
                )
                
                # Add propagated signals to result
                result['propagated_signals'] = [
                    self.propagator.to_dict(s) for s in propagated_signals
                ]
                
                logger.info(
                    f"Propagated {len(propagated_signals)} signals from {ticker} "
                    f"to related companies"
                )
            except Exception as e:
                logger.warning(f"Propagation failed for {ticker}: {e}")
                result['propagated_signals'] = []
        else:
            result['propagated_signals'] = []
        
        return result
    
    def get_all_signals(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> Tuple[Optional[Dict], List[Dict]]:
        """
        Get both direct and propagated signals for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            Tuple of (direct_signal, propagated_signals_list)
            - direct_signal: Dict with source_type='direct' or None
            - propagated_signals_list: List of propagated signal dicts
        """
        result = self.analyze_news_for_ticker(ticker, start_date, end_date, include_propagated=True)
        
        if result is None:
            return None, []
        
        direct_signal = {
            'ticker': ticker.upper(),
            'source_ticker': ticker.upper(),
            'sentiment_score': result.get('sentiment_score', 0.0),
            'supply_chain_score': result.get('supply_chain_score', 0.0),
            'source_type': 'direct',
            'confidence': result.get('confidence', 1.0),
            'relationship': result.get('relationship', 'Neutral'),
            'reasoning': result.get('reasoning', '')
        }
        
        propagated_signals = result.get('propagated_signals', [])
        
        return direct_signal, propagated_signals
