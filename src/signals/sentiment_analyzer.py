"""
Sentiment Analyzer
Analyzes sentiment from news articles and creates time series
Calculates rolling averages and momentum
"""
import os
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
import logging

from src.utils.logger import setup_logger

logger = setup_logger()


class SentimentAnalyzer:
    """Analyzes sentiment from news articles and creates time series"""
    
    def __init__(self, data_dir: str = "data/news", output_dir: str = "data"):
        self.data_dir = data_dir
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize FinBERT for sentiment scoring
        try:
            from transformers import pipeline
            self.sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model="ProsusAI/finbert",
                device=-1  # CPU
            )
            logger.info("Initialized FinBERT sentiment analyzer")
        except Exception as e:
            logger.warning(f"Could not load FinBERT: {e}. Will use simple keyword-based sentiment.")
            self.sentiment_pipeline = None
    
    def score_sentiment_finbert(self, text: str) -> float:
        """Score sentiment using FinBERT (0=negative, 0.5=neutral, 1=positive)"""
        if not self.sentiment_pipeline:
            return self.score_sentiment_keyword(text)
        
        try:
            result = self.sentiment_pipeline(text)[0]
            label = result['label'].lower()
            score = result['score']
            
            # Map FinBERT labels to 0-1 scale
            if 'positive' in label:
                return 0.5 + (score * 0.5)  # 0.5 to 1.0
            elif 'negative' in label:
                return 0.5 - (score * 0.5)  # 0.0 to 0.5
            else:
                return 0.5  # Neutral
        except Exception as e:
            logger.warning(f"FinBERT scoring failed: {e}, using keyword fallback")
            return self.score_sentiment_keyword(text)
    
    def score_sentiment_keyword(self, text: str) -> float:
        """Simple keyword-based sentiment (fallback)"""
        text_lower = text.lower()
        
        positive_words = ['positive', 'growth', 'gain', 'rise', 'up', 'strong', 'beat', 'exceed']
        negative_words = ['negative', 'decline', 'fall', 'down', 'weak', 'miss', 'below', 'loss']
        
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        if pos_count > neg_count:
            return 0.7
        elif neg_count > pos_count:
            return 0.3
        else:
            return 0.5
    
    def score_article_sentiment(self, article: Dict) -> float:
        """Score sentiment for a single article"""
        title = article.get('title', '')
        description = article.get('description', '')
        content = article.get('content', '') or description
        
        text = f"{title}. {description}. {content}"
        
        if self.sentiment_pipeline:
            return self.score_sentiment_finbert(text)
        else:
            return self.score_sentiment_keyword(text)
    
    def create_sentiment_timeseries(self, ticker: str, articles: List[Dict]) -> pd.Series:
        """Create sentiment time series for a ticker"""
        if not articles:
            return pd.Series(dtype=float)
        
        # Score each article
        sentiment_data = []
        for article in articles:
            try:
                date_str = article.get('publishedAt', '')
                if not date_str:
                    continue
                
                date = pd.to_datetime(date_str).date()
                score = self.score_article_sentiment(article)
                
                sentiment_data.append({
                    'date': date,
                    'sentiment_score': score
                })
            except Exception as e:
                logger.warning(f"Error processing article for {ticker}: {e}")
                continue
        
        if not sentiment_data:
            return pd.Series(dtype=float)
        
        # Create DataFrame
        df = pd.DataFrame(sentiment_data)
        df = df.set_index('date').sort_index()
        
        # Aggregate by date (average if multiple articles per day)
        daily_sentiment = df.groupby('date')['sentiment_score'].mean()
        
        return daily_sentiment
    
    def calculate_rolling_metrics(self, sentiment_series: pd.Series, 
                                   short_window: int = 7, long_window: int = 30) -> pd.DataFrame:
        """Calculate rolling averages and momentum"""
        if sentiment_series.empty:
            return pd.DataFrame()
        
        # Create date range (fill missing dates with NaN)
        date_range = pd.date_range(
            start=sentiment_series.index.min(),
            end=sentiment_series.index.max(),
            freq='D'
        )
        
        # Reindex to fill missing dates
        full_series = sentiment_series.reindex(date_range)
        
        # Calculate rolling averages
        rolling_short = full_series.rolling(window=short_window, min_periods=1).mean()
        rolling_long = full_series.rolling(window=long_window, min_periods=1).mean()
        
        # Calculate momentum: (short_avg - long_avg) / long_avg
        momentum = (rolling_short - rolling_long) / (rolling_long + 1e-8)  # Avoid div by zero
        
        # Create DataFrame
        df = pd.DataFrame({
            'sentiment_score': full_series,
            'rolling_short': rolling_short,
            'rolling_long': rolling_long,
            'sentiment_momentum': momentum
        })
        
        return df
    
    def process_ticker(self, ticker: str, articles: List[Dict], 
                      short_window: int = 7, long_window: int = 30) -> pd.DataFrame:
        """Process all articles for a ticker and return sentiment time series"""
        # Create time series
        sentiment_series = self.create_sentiment_timeseries(ticker, articles)
        
        if sentiment_series.empty:
            return pd.DataFrame()
        
        # Calculate rolling metrics
        df = self.calculate_rolling_metrics(sentiment_series, short_window, long_window)
        df['ticker'] = ticker
        
        return df
    
    def process_all_tickers(self, tickers: List[str], articles_dict: Dict[str, List[Dict]],
                           short_window: int = 7, long_window: int = 30) -> pd.DataFrame:
        """Process all tickers and create combined sentiment time series"""
        all_data = []
        
        logger.info(f"Processing sentiment for {len(tickers)} tickers...")
        
        for ticker in tickers:
            articles = articles_dict.get(ticker, [])
            df = self.process_ticker(ticker, articles, short_window, long_window)
            
            if not df.empty:
                all_data.append(df)
        
        if not all_data:
            logger.warning("No sentiment data generated")
            return pd.DataFrame()
        
        # Combine all tickers
        combined = pd.concat(all_data, ignore_index=False)
        combined = combined.sort_index()
        
        # Save to parquet
        output_path = os.path.join(self.output_dir, "sentiment_timeseries.parquet")
        combined.to_parquet(output_path)
        logger.info(f"Saved sentiment time series to {output_path}")
        
        return combined


if __name__ == "__main__":
    # Test script
    logger = setup_logger()
    
    analyzer = SentimentAnalyzer()
    
    # Test with sample articles
    test_articles = [
        {
            'title': 'NVIDIA Reports Strong AI Chip Demand',
            'description': 'NVIDIA sees record demand for AI chips as companies scale up training.',
            'publishedAt': '2024-01-15T10:00:00Z'
        },
        {
            'title': 'Semiconductor Stocks Decline on Trade Concerns',
            'description': 'Chip stocks fall as trade tensions escalate.',
            'publishedAt': '2024-01-16T10:00:00Z'
        }
    ]
    
    result = analyzer.process_ticker('TEST', test_articles)
    print(f"\n✅ Sentiment analysis complete")
    print(result.head())
