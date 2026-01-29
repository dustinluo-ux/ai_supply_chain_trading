"""
Signal Combiner
Combines supply chain score, sentiment momentum, price momentum, volume spike
into composite signal and ranks stocks
"""
import os
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
import logging

from src.utils.logger import setup_logger

logger = setup_logger()


class SignalCombiner:
    """Combines multiple signals into composite trading signal"""
    
    def __init__(self, data_dir: str = "data", output_dir: str = "data/signals"):
        self.data_dir = data_dir
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # Default weights (can be overridden)
        self.weights = {
            'supply_chain_score': 0.4,
            'sentiment_momentum': 0.3,
            'price_momentum': 0.2,
            'volume_spike': 0.1
        }
        
        logger.info("SignalCombiner initialized")
    
    def load_supply_chain_scores(self) -> pd.DataFrame:
        """Load supply chain scores"""
        path = os.path.join(self.data_dir, "supply_chain_mentions.csv")
        
        if not os.path.exists(path):
            logger.warning("Supply chain scores not found")
            return pd.DataFrame()
        
        try:
            df = pd.read_csv(path)
            return df[['ticker', 'supply_chain_score']]
        except Exception as e:
            logger.error(f"Error loading supply chain scores: {e}")
            return pd.DataFrame()
    
    def load_sentiment_data(self, date: Optional[str] = None) -> pd.DataFrame:
        """Load sentiment time series data"""
        path = os.path.join(self.data_dir, "sentiment_timeseries.parquet")
        
        if not os.path.exists(path):
            logger.warning("Sentiment time series not found")
            return pd.DataFrame()
        
        try:
            df = pd.read_parquet(path)
            
            # Filter by date if provided
            if date:
                date_dt = pd.to_datetime(date)
                df = df[df.index <= date_dt]
                # Get most recent value per ticker
                df = df.groupby('ticker').last().reset_index()
            
            return df[['ticker', 'sentiment_momentum']]
        except Exception as e:
            logger.error(f"Error loading sentiment data: {e}")
            return pd.DataFrame()
    
    def load_technical_indicators(self, date: Optional[str] = None, include_rsi: bool = False) -> pd.DataFrame:
        """Load technical indicators"""
        path = os.path.join(self.data_dir, "technical_indicators.parquet")
        
        if not os.path.exists(path):
            logger.warning("Technical indicators not found")
            return pd.DataFrame()
        
        try:
            df = pd.read_parquet(path)
            
            # Filter by date if provided
            if date:
                date_dt = pd.to_datetime(date)
                df = df[df.index <= date_dt]
                # Get most recent value per ticker
                df = df.groupby('ticker').last().reset_index()
            
            columns = ['ticker', 'price_momentum', 'volume_spike']
            if include_rsi and 'rsi' in df.columns:
                columns.append('rsi')
            
            return df[columns]
        except Exception as e:
            logger.error(f"Error loading technical indicators: {e}")
            return pd.DataFrame()
    
    def normalize_signal(self, series: pd.Series) -> pd.Series:
        """Normalize signal to 0-1 range using z-score then sigmoid"""
        if series.empty or series.std() == 0:
            return pd.Series(0.5, index=series.index)
        
        z_score = (series - series.mean()) / (series.std() + 1e-8)
        # Sigmoid to 0-1 range
        normalized = 1 / (1 + np.exp(-z_score))
        
        return normalized
    
    def calculate_technical_only_signal(self, date: Optional[str] = None,
                                       min_price_momentum: float = 0.0) -> pd.DataFrame:
        """
        Calculate signal using ONLY technical indicators (no news/LLM)
        
        Weights:
        - Price momentum: 50%
        - Volume spike: 30%
        - RSI score: 20%
        
        Args:
            date: Date to generate signals for (default: most recent)
            min_price_momentum: Minimum price momentum filter (only positive momentum)
        
        Returns:
            DataFrame with technical signal scores and rankings
        """
        logger.info(f"Calculating technical-only signals for date: {date or 'latest'}")
        
        # Load technical indicators
        technical = self.load_technical_indicators(date, include_rsi=True)
        
        if technical.empty:
            logger.error("No technical indicators available")
            return pd.DataFrame()
        
        # Normalize RSI to 0-1 scale (RSI is 0-100, higher RSI = higher signal)
        if 'rsi' in technical.columns:
            # RSI normalization: (RSI - 30) / (70 - 30) clipped to 0-1
            # This maps RSI 30->0, RSI 70->1, with clipping
            technical['rsi_score'] = ((technical['rsi'] - 30) / 40).clip(0, 1)
            technical['rsi_score'] = technical['rsi_score'].fillna(0.5)  # Neutral if missing
        else:
            technical['rsi_score'] = 0.5  # Neutral if RSI not available
        
        # Normalize each signal component
        technical['price_momentum_norm'] = self.normalize_signal(technical['price_momentum'])
        technical['volume_spike_norm'] = self.normalize_signal(technical['volume_spike'])
        technical['rsi_norm'] = technical['rsi_score']  # Already 0-1
        
        # Apply filter: only positive momentum stocks
        if min_price_momentum is not None:
            technical = technical[technical['price_momentum'] >= min_price_momentum]
            logger.info(f"Filtered to {len(technical)} stocks with positive momentum")
        
        # Calculate technical signal (using weights from config)
        technical_weights = {
            'price_momentum': 0.5,
            'volume_spike': 0.3,
            'rsi_score': 0.2
        }
        
        technical['technical_signal'] = (
            technical['price_momentum_norm'] * technical_weights['price_momentum'] +
            technical['volume_spike_norm'] * technical_weights['volume_spike'] +
            technical['rsi_norm'] * technical_weights['rsi_score']
        )
        
        # Rank stocks
        technical = technical.sort_values('technical_signal', ascending=False)
        technical['rank'] = range(1, len(technical) + 1)
        
        logger.info(f"Calculated technical signals for {len(technical)} stocks")
        return technical
    
    def combine_signals(self, date: Optional[str] = None, 
                       min_sentiment_momentum: float = 0.0,
                       min_market_cap: Optional[float] = None,
                       max_market_cap: Optional[float] = None,
                       mode: str = "full_with_news") -> pd.DataFrame:
        """
        Combine all signals into composite score
        
        Args:
            date: Date to generate signals for (default: most recent)
            min_sentiment_momentum: Minimum sentiment momentum filter
            min_market_cap: Minimum market cap filter
            max_market_cap: Maximum market cap filter
            mode: "technical_only" or "full_with_news"
        
        Returns:
            DataFrame with composite signals and rankings
        """
        # Check if technical-only mode
        if mode == "technical_only":
            return self.calculate_technical_only_signal(date, min_price_momentum=0.0)
        
        logger.info(f"Combining signals for date: {date or 'latest'} (mode: {mode})")
        
        # Load all signal components
        supply_chain = self.load_supply_chain_scores()
        sentiment = self.load_sentiment_data(date)
        technical = self.load_technical_indicators(date)
        
        if supply_chain.empty:
            logger.error("No supply chain scores available")
            return pd.DataFrame()
        
        # Merge all signals
        combined = supply_chain.copy()
        
        if not sentiment.empty:
            combined = combined.merge(sentiment, on='ticker', how='left')
        else:
            combined['sentiment_momentum'] = 0.0
        
        if not technical.empty:
            combined = combined.merge(technical, on='ticker', how='left')
        else:
            combined['price_momentum'] = 0.0
            combined['volume_spike'] = 1.0  # Neutral
        
        # Fill missing values
        combined['sentiment_momentum'] = combined['sentiment_momentum'].fillna(0.0)
        combined['price_momentum'] = combined['price_momentum'].fillna(0.0)
        combined['volume_spike'] = combined['volume_spike'].fillna(1.0)
        
        # Normalize each signal component
        combined['supply_chain_norm'] = self.normalize_signal(combined['supply_chain_score'])
        combined['sentiment_norm'] = self.normalize_signal(combined['sentiment_momentum'])
        combined['price_norm'] = self.normalize_signal(combined['price_momentum'])
        combined['volume_norm'] = self.normalize_signal(combined['volume_spike'])
        
        # Apply filters
        if min_sentiment_momentum is not None:
            combined = combined[combined['sentiment_momentum'] >= min_sentiment_momentum]
        
        # Market cap filter would require additional data source
        # For now, assume all tickers in supply_chain already passed market cap filter
        
        # Calculate composite signal
        combined['composite_signal'] = (
            combined['supply_chain_norm'] * self.weights['supply_chain_score'] +
            combined['sentiment_norm'] * self.weights['sentiment_momentum'] +
            combined['price_norm'] * self.weights['price_momentum'] +
            combined['volume_norm'] * self.weights['volume_spike']
        )
        
        # Rank stocks
        combined = combined.sort_values('composite_signal', ascending=False)
        combined['rank'] = range(1, len(combined) + 1)
        
        return combined
    
    def get_top_stocks(self, date: Optional[str] = None, top_n: int = 10, mode: str = "full_with_news", **filter_kwargs) -> pd.DataFrame:
        """Get top N stocks by composite signal"""
        combined = self.combine_signals(date, mode=mode, **filter_kwargs)
        
        if combined.empty:
            return pd.DataFrame()
        
        # Get signal column name based on mode
        if mode == "technical_only":
            signal_col = 'technical_signal'
        else:
            signal_col = 'composite_signal'
        
        top_stocks = combined.head(top_n)
        
        # Save results
        mode_suffix = "_technical" if mode == "technical_only" else ""
        output_path = os.path.join(self.output_dir, f"top_stocks_{date or 'latest'}{mode_suffix}.csv")
        top_stocks.to_csv(output_path, index=False)
        logger.info(f"Saved top {len(top_stocks)} stocks to {output_path}")
        
        return top_stocks
    
    def combine_signals_direct(self, technical_signals: Dict, news_signals: Dict, 
                               weights: Dict[str, float]) -> float:
        """
        Combine technical and news signals directly (without loading from files)
        
        Args:
            technical_signals: Dict with keys: momentum_score, volume_score, rsi_score
            news_signals: Dict with keys: supply_chain_score, sentiment_score, confidence
            weights: Dict with keys: supply_chain, sentiment, momentum, volume
        
        Returns:
            Combined score (0-1)
        """
        # Normalize technical signals to 0-1 range
        momentum = technical_signals.get('momentum_score', 0.0)
        volume = technical_signals.get('volume_score', 1.0)  # Default to neutral
        rsi = technical_signals.get('rsi_score', 0.5)
        
        # CRITICAL FIX: Use z-score normalization for momentum to create more variance
        # Instead of sigmoid which clusters values, use percentile-based normalization
        # This ensures different momentum values produce meaningfully different scores
        
        # Normalize momentum using tanh (preserves sign, creates more spread)
        # Momentum typically ranges from -0.3 to +0.3, scale to create more differentiation
        if abs(momentum) > 1e-6:
            # Use tanh to map to [-1, 1] then to [0, 1]
            # Scale factor of 5 makes small differences more visible
            momentum_scaled = momentum * 5
            momentum_norm = (np.tanh(momentum_scaled) + 1.0) / 2.0
        else:
            momentum_norm = 0.5
        
        # Normalize volume (ratio, map to 0-1)
        # Volume ratio typically ranges from 0.5 to 3.0, but if all are 1.0, we need to handle that
        # Use log scale to create more differentiation when values are close
        if volume > 0 and volume != 1.0:
            # Log scale: log(volume) / log(3.0) maps 0.5->0.0, 1.0->0.5, 3.0->1.0
            volume_norm = np.log(volume) / np.log(3.0)
            volume_norm = max(0.0, min(1.0, volume_norm))
        elif volume == 1.0:
            # If volume is exactly 1.0 (neutral), use 0.5
            volume_norm = 0.5
        else:
            volume_norm = 0.5
        
        # RSI is already 0-1 (from technical_analyzer)
        # But we're not using RSI here since it's combined with momentum before calling this
        
        # Get news signals
        supply_chain = news_signals.get('supply_chain_score', 0.0)
        sentiment = news_signals.get('sentiment_score', 0.0)
        
        # Normalize sentiment (-1 to +1) to (0 to 1)
        # CRITICAL FIX: If sentiment is 0.0 (no news), keep it as 0.0, not 0.5
        # This prevents adding a constant offset that makes all stocks identical
        if abs(sentiment) < 0.001:
            sentiment_norm = 0.0  # No news = 0.0, not neutral 0.5
        else:
            sentiment_norm = (sentiment + 1.0) / 2.0
        
        # Get weights (ensure they exist)
        w_supply = weights.get('supply_chain', 0.0)
        w_sentiment = weights.get('sentiment', 0.0)
        w_momentum = weights.get('momentum', 0.0)
        w_volume = weights.get('volume', 0.0)
        
        # DEBUG: Log weights and signals
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"combine_signals_direct: weights={weights}, tech={technical_signals}, news={news_signals}")
        
        # Normalize weights to sum to 1.0 if they don't already
        total_weight = w_supply + w_sentiment + w_momentum + w_volume
        
        # CRITICAL FIX: If total_weight is 0, return 0.5 (neutral) instead of crashing
        if total_weight == 0:
            logger.warning("All weights are zero in combine_signals_direct! Returning neutral score.")
            return 0.5
        
        # Normalize weights
        w_supply = w_supply / total_weight
        w_sentiment = w_sentiment / total_weight
        w_momentum = w_momentum / total_weight
        w_volume = w_volume / total_weight
        
        # Apply weights and combine
        combined = (
            supply_chain * w_supply +
            sentiment_norm * w_sentiment +
            momentum_norm * w_momentum +
            volume_norm * w_volume
        )
        
        # Clip to 0-1
        result = max(0.0, min(1.0, combined))
        
        return result
    
    def set_weights(self, weights: Dict[str, float]):
        """Update signal weights"""
        # Validate weights sum to 1.0
        total = sum(weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Weights sum to {total}, normalizing to 1.0")
            weights = {k: v / total for k, v in weights.items()}
        
        self.weights = weights
        logger.info(f"Updated signal weights: {weights}")


if __name__ == "__main__":
    # Test script
    logger = setup_logger()
    
    combiner = SignalCombiner()
    
    # Get top 10 stocks
    top_stocks = combiner.get_top_stocks(date="2024-01-15", top_n=10)
    
    if not top_stocks.empty:
        print(f"\n✅ Top {len(top_stocks)} stocks:")
        print(top_stocks[['ticker', 'composite_signal', 'rank']].head())
    else:
        print("No signals available. Run previous pipeline steps first.")
