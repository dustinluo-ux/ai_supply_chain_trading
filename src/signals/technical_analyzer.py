"""
Technical Analyzer
Calculates technical indicators (momentum, volume, RSI) for a ticker at a specific date
Reuses existing TechnicalIndicators class
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path
import logging

from src.signals.technical_indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """Calculates technical signals for a ticker at a specific date"""
    
    def __init__(self, data_dir: str = "data/prices", 
                 momentum_period: int = 20,
                 volume_period: int = 30,
                 rsi_period: int = 14):
        """
        Initialize Technical Analyzer
        
        Args:
            data_dir: Directory containing price data (CSV or parquet files)
            momentum_period: Period for momentum calculation (long period)
            volume_period: Period for volume rolling average
            rsi_period: Period for RSI calculation
        """
        self.data_dir = Path(data_dir)
        self.momentum_period = momentum_period
        self.volume_period = volume_period
        self.rsi_period = rsi_period
        
        # Initialize TechnicalIndicators (for parquet files)
        self.tech_indicators = TechnicalIndicators(data_dir=data_dir, output_dir="data")
        
        logger.info("TechnicalAnalyzer initialized")
    
    def load_price_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """Load price data for a ticker (tries CSV first, then parquet)"""
        # Try CSV first (from simple_backtest_v2.py format)
        csv_file = self.data_dir / f"{ticker}.csv"
        if csv_file.exists():
            try:
                df = pd.read_csv(csv_file, index_col=0, parse_dates=True)
                df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
                df.columns = [col.lower() for col in df.columns]
                # DEBUG: Log available columns
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Loaded {ticker}: columns={df.columns.tolist()}, shape={df.shape}")
                return df
            except Exception as e:
                logger.warning(f"Error loading CSV for {ticker}: {e}")
        
        # Try parquet (from TechnicalIndicators format)
        return self.tech_indicators.load_price_data(ticker)
    
    def calculate_technical_signals(self, ticker: str, date: str) -> Dict:
        """
        Calculate technical signals for a ticker at a specific date
        
        Args:
            ticker: Stock ticker symbol
            date: Date string (YYYY-MM-DD)
        
        Returns:
            Dict with keys: momentum_score, volume_score, rsi_score
            Returns default values if calculation fails
        """
        # Load price data
        df = self.load_price_data(ticker)
        
        if df is None or df.empty:
            logger.debug(f"No price data for {ticker}")
            return {
                'momentum_score': 0.0,
                'volume_score': 0.0,
                'rsi_score': 0.5  # Neutral RSI
            }
        
        # Ensure datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'date' in df.columns:
                df = df.set_index('date')
            else:
                logger.warning(f"Could not set datetime index for {ticker}")
                return {
                    'momentum_score': 0.0,
                    'volume_score': 0.0,
                    'rsi_score': 0.5
                }
        
        # Filter to date or before
        date_dt = pd.to_datetime(date)
        df_filtered = df[df.index <= date_dt]
        
        if df_filtered.empty:
            logger.debug(f"No price data before {date} for {ticker}")
            return {
                'momentum_score': 0.0,
                'volume_score': 0.0,
                'rsi_score': 0.5
            }
        
        # Get most recent data point
        latest = df_filtered.iloc[-1]
        
        # Calculate momentum (using simple_backtest_v2.py logic)
        if 'close' in df_filtered.columns:
            close = df_filtered['close']
            # Momentum: (close[-5] - close[-20]) / close[-20]
            if len(close) >= self.momentum_period:
                close_short = close.iloc[-5] if len(close) >= 5 else close.iloc[-1]
                close_long = close.iloc[-self.momentum_period]
                momentum = (close_short - close_long) / (close_long + 1e-8)
                # DEBUG: Log momentum calculation for first few tickers
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"{ticker} momentum: short={close_short:.2f}, long={close_long:.2f}, momentum={momentum:.6f}")
            else:
                momentum = 0.0
                logger.debug(f"{ticker} insufficient data for momentum (need {self.momentum_period}, have {len(close)})")
        else:
            momentum = 0.0
            logger.warning(f"{ticker} no 'close' column in data")
        
        # Calculate volume ratio
        if 'volume' in df_filtered.columns:
            volume = df_filtered['volume']
            if len(volume) >= self.volume_period:
                volume_mean = volume.rolling(self.volume_period, min_periods=1).mean().iloc[-1]
                volume_latest = volume.iloc[-1]
                if volume_mean > 0:
                    volume_ratio = volume_latest / volume_mean
                else:
                    volume_ratio = 1.0  # Neutral if no volume data
            else:
                volume_ratio = 1.0  # Neutral
        else:
            # Volume column missing - use a default neutral value
            volume_ratio = 1.0
            logger.debug(f"No volume column for {ticker}, using neutral 1.0")
        
        # Calculate RSI (using simple_backtest_v2.py logic)
        if 'close' in df_filtered.columns:
            close = df_filtered['close']
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(self.rsi_period, min_periods=1).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(self.rsi_period, min_periods=1).mean()
            if len(gain) > 0 and len(loss) > 0:
                rs = gain.iloc[-1] / (loss.iloc[-1] + 1e-8)
                rsi = 100 - (100 / (1 + rs))
                # Normalize RSI to 0-1 (30->0, 70->1)
                rsi_score = ((rsi - 30) / 40).clip(0, 1)
            else:
                rsi_score = 0.5  # Neutral
        else:
            rsi_score = 0.5
        
        return {
            'momentum_score': float(momentum),
            'volume_score': float(volume_ratio),
            'rsi_score': float(rsi_score)
        }
