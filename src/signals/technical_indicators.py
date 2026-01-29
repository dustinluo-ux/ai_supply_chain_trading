"""
Technical Indicators
Calculates momentum, volume, RSI, Bollinger Bands using pandas-ta
"""
import os
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

try:
    import pandas_ta as ta
except ImportError:
    raise ImportError("pandas_ta required. Install with: pip install pandas-ta")

from src.utils.logger import setup_logger

logger = setup_logger()


class TechnicalIndicators:
    """Calculates technical indicators for price data"""
    
    def __init__(self, data_dir: str = "data/prices", output_dir: str = "data"):
        self.data_dir = data_dir
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        logger.info("TechnicalIndicators initialized")
    
    def load_price_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """Load price data for a ticker"""
        price_path = os.path.join(self.data_dir, f"{ticker}.parquet")
        
        if not os.path.exists(price_path):
            logger.debug(f"No price data found for {ticker}")
            return None
        
        try:
            df = pd.read_parquet(price_path)
            return df
        except Exception as e:
            logger.error(f"Error loading price data for {ticker}: {e}")
            return None
    
    def calculate_price_momentum(self, df: pd.DataFrame, short: int = 5, long: int = 20) -> pd.Series:
        """Calculate price momentum: (close_short - close_long) / close_long"""
        if 'close' not in df.columns:
            logger.warning("No 'close' column found")
            return pd.Series(dtype=float)
        
        close_short = df['close'].shift(short)
        close_long = df['close'].shift(long)
        
        momentum = (close_short - close_long) / (close_long + 1e-8)
        return momentum
    
    def calculate_volume_spike(self, df: pd.DataFrame, window: int = 30) -> pd.Series:
        """Calculate volume spike: current_volume / rolling_avg_volume"""
        if 'volume' not in df.columns:
            logger.warning("No 'volume' column found")
            return pd.Series(dtype=float)
        
        rolling_avg = df['volume'].rolling(window=window, min_periods=1).mean()
        volume_spike = df['volume'] / (rolling_avg + 1e-8)
        
        return volume_spike
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate RSI using pandas-ta"""
        if 'close' not in df.columns:
            logger.warning("No 'close' column found")
            return pd.Series(dtype=float)
        
        try:
            rsi = ta.rsi(df['close'], length=period)
            return rsi
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return pd.Series(dtype=float)
    
    def calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
        """Calculate Bollinger Bands"""
        if 'close' not in df.columns:
            logger.warning("No 'close' column found")
            return pd.DataFrame()
        
        try:
            bb = ta.bbands(df['close'], length=period, std=std)
            return bb
        except Exception as e:
            logger.error(f"Error calculating Bollinger Bands: {e}")
            return pd.DataFrame()
    
    def calculate_all_indicators(self, ticker: str, short_momentum: int = 5, 
                                long_momentum: int = 20, volume_window: int = 30,
                                rsi_period: int = 14, bb_period: int = 20, bb_std: float = 2.0) -> pd.DataFrame:
        """Calculate all technical indicators for a ticker"""
        df = self.load_price_data(ticker)
        
        if df is None or df.empty:
            logger.debug(f"No price data for {ticker}")
            return pd.DataFrame()
        
        # Ensure index is datetime
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'date' in df.columns:
                df = df.set_index('date')
            else:
                logger.warning(f"Could not set datetime index for {ticker}")
                return pd.DataFrame()
        
        # Calculate indicators
        indicators = pd.DataFrame(index=df.index)
        indicators['ticker'] = ticker
        indicators['close'] = df['close']
        indicators['volume'] = df.get('volume', 0)
        
        # Price momentum
        indicators['price_momentum'] = self.calculate_price_momentum(df, short_momentum, long_momentum)
        
        # Volume spike
        indicators['volume_spike'] = self.calculate_volume_spike(df, volume_window)
        
        # RSI
        indicators['rsi'] = self.calculate_rsi(df, rsi_period)
        
        # Bollinger Bands
        bb = self.calculate_bollinger_bands(df, bb_period, bb_std)
        if not bb.empty:
            indicators['bb_upper'] = bb.get(f'BBU_{bb_period}_{bb_std}.0', np.nan)
            indicators['bb_middle'] = bb.get(f'BBM_{bb_period}_{bb_std}.0', np.nan)
            indicators['bb_lower'] = bb.get(f'BBL_{bb_period}_{bb_std}.0', np.nan)
            
            # Bollinger Band position (0 = lower, 1 = upper)
            indicators['bb_position'] = (
                (df['close'] - indicators['bb_lower']) / 
                (indicators['bb_upper'] - indicators['bb_lower'] + 1e-8)
            )
        
        return indicators
    
    def process_all_tickers(self, tickers: List[str], **indicator_params) -> pd.DataFrame:
        """Calculate indicators for all tickers"""
        all_data = []
        total_tickers = len(tickers)
        
        logger.info(f"Calculating technical indicators for {total_tickers} tickers...")
        print(f"Calculating technical indicators for {total_tickers} tickers...", flush=True)
        
        successful_count = 0
        failed_count = 0
        
        for idx, ticker in enumerate(tickers, 1):
            print(f"[{idx}/{total_tickers}] Processing {ticker}...", flush=True)
            logger.info(f"[{idx}/{total_tickers}] Processing {ticker}...")
            
            try:
                indicators = self.calculate_all_indicators(ticker, **indicator_params)
                
                if not indicators.empty:
                    all_data.append(indicators)
                    successful_count += 1
                    print(f"  ✓ {ticker} completed successfully", flush=True)
                else:
                    logger.warning(f"  ⚠ {ticker} returned empty indicators")
                    print(f"  ⚠ {ticker} returned empty indicators", flush=True)
                    failed_count += 1
                    
            except Exception as e:
                failed_count += 1
                error_msg = f"  ✗ {ticker} failed: {str(e)}"
                logger.error(error_msg)
                logger.error(f"Traceback for {ticker}:", exc_info=True)
                print(error_msg, flush=True)
                continue
        
        print(f"\nCompleted: {successful_count} successful, {failed_count} failed", flush=True)
        logger.info(f"Completed: {successful_count} successful, {failed_count} failed")
        
        if not all_data:
            logger.warning("No technical indicator data generated")
            print("No technical indicator data generated", flush=True)
            return pd.DataFrame()
        
        # Combine all tickers
        print("Combining indicator data...", flush=True)
        logger.info("Combining indicator data...")
        try:
            combined = pd.concat(all_data, ignore_index=False)
            combined = combined.sort_index()
        except Exception as e:
            logger.error(f"Error combining indicator data: {e}")
            print(f"Error combining indicator data: {e}", flush=True)
            raise
        
        # Save to parquet
        output_path = os.path.join(self.output_dir, "technical_indicators.parquet")
        print(f"Saving technical indicators to {output_path}...", flush=True)
        logger.info(f"Saving technical indicators to {output_path}...")
        try:
            combined.to_parquet(output_path)
            logger.info(f"Saved technical indicators to {output_path}")
            print(f"✓ Saved technical indicators to {output_path}", flush=True)
        except Exception as e:
            logger.error(f"Error saving technical indicators: {e}")
            print(f"Error saving technical indicators: {e}", flush=True)
            raise
        
        return combined


if __name__ == "__main__":
    # Test script
    logger = setup_logger()
    
    # This requires price data to be fetched first
    # Run: python src/data/price_fetcher.py
    
    indicator_calc = TechnicalIndicators()
    
    # Test with a sample ticker (if data exists)
    test_tickers = ['NVDA', 'AMD']
    result = indicator_calc.process_all_tickers(test_tickers)
    
    if not result.empty:
        print(f"\n✅ Technical indicators calculated")
        print(result.head())
    else:
        print("No price data found. Run price_fetcher.py first.")
