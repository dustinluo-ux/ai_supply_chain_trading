"""
Price data fetcher for Russell 2000 stocks with market cap filtering
Fetches OHLCV data from yfinance and stores as parquet
"""
import os
import sys
import yfinance as yf
import pandas as pd
import numpy as np
from typing import List, Optional, Dict
import logging
from datetime import datetime
from tqdm import tqdm
import time

# Add src to path for imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

from src.utils.ticker_utils import get_russell2000_tickers

logger = logging.getLogger(__name__)


class PriceFetcher:
    """Fetches price data for Russell 2000 stocks with market cap filtering"""
    
    def __init__(self, data_dir: str = "data/prices", min_market_cap: int = 500_000_000, 
                 max_market_cap: int = 5_000_000_000):
        self.data_dir = data_dir
        self.min_market_cap = min_market_cap
        self.max_market_cap = max_market_cap
        try:
            os.makedirs(data_dir, exist_ok=True)
            logger.info(f"PriceFetcher initialized: market cap filter ${min_market_cap:,} - ${max_market_cap:,}")
            logger.debug(f"Data directory: {os.path.abspath(data_dir)}")
        except Exception as e:
            logger.error(f"Error creating data directory {data_dir}: {e}")
            raise
    
    def get_russell2000_tickers(self) -> List[str]:
        """
        Get Russell 2000 ticker list
        Uses ticker_utils to get from file, web, or fallback list
        """
        tickers = get_russell2000_tickers(use_file=True)
        logger.info(f"Retrieved {len(tickers)} tickers for Russell 2000 universe")
        return tickers
    
    def get_market_cap(self, ticker: str) -> Optional[float]:
        """Get current market cap for a ticker"""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            market_cap = info.get('marketCap', None)
            if market_cap is None:
                # Try alternative field
                market_cap = info.get('enterpriseValue', None)
            return market_cap
        except Exception as e:
            logger.warning(f"Could not get market cap for {ticker}: {e}")
            return None
    
    def filter_by_market_cap(self, tickers: List[str]) -> List[str]:
        """Filter tickers by market cap range"""
        filtered = []
        logger.info(f"Filtering {len(tickers)} tickers by market cap...")
        
        for ticker in tqdm(tickers, desc="Checking market caps"):
            try:
                market_cap = self.get_market_cap(ticker)
                if market_cap and self.min_market_cap <= market_cap <= self.max_market_cap:
                    filtered.append(ticker)
                    logger.debug(f"{ticker}: ${market_cap:,.0f} - PASS")
                elif market_cap:
                    logger.debug(f"{ticker}: ${market_cap:,.0f} - FAIL (outside range)")
                else:
                    logger.debug(f"{ticker}: Market cap unavailable - SKIP")
                time.sleep(0.1)  # Rate limiting
            except Exception as e:
                logger.warning(f"Error checking {ticker}: {e}")
                continue
        
        logger.info(f"Filtered to {len(filtered)} tickers in market cap range")
        return filtered
    
    def fetch_price_data(self, ticker: str, start_date: str, end_date: str, max_retries: int = 3) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data for a single ticker with retry logic
        
        Args:
            ticker: Ticker symbol
            start_date: Start date
            end_date: End date
            max_retries: Number of retry attempts (default: 3)
        """
        for attempt in range(max_retries):
            try:
                stock = yf.Ticker(ticker)
                df = stock.history(start=start_date, end=end_date, interval="1d")
                
                if df.empty:
                    if attempt < max_retries - 1:
                        logger.warning(f"No data returned for {ticker}, retrying ({attempt + 1}/{max_retries})...")
                        time.sleep(5)  # Wait 5 seconds before retry
                        continue
                    logger.warning(f"No data returned for {ticker} after {max_retries} attempts")
                    return None
                
                # Standardize column names
                df.columns = [col.lower() for col in df.columns]
                
                # Ensure we have required columns
                required_cols = ['open', 'high', 'low', 'close', 'volume']
                if not all(col in df.columns for col in required_cols):
                    if attempt < max_retries - 1:
                        logger.warning(f"Missing required columns for {ticker}, retrying ({attempt + 1}/{max_retries})...")
                        time.sleep(5)
                        continue
                    logger.warning(f"Missing required columns for {ticker} after {max_retries} attempts")
                    return None
                
                # Add ticker column
                df['ticker'] = ticker
                
                return df[['ticker'] + required_cols]
            
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Error fetching {ticker} (attempt {attempt + 1}/{max_retries}): {e}, retrying in 5 seconds...")
                    time.sleep(5)
                    continue
                logger.error(f"Error fetching data for {ticker} after {max_retries} attempts: {e}")
                return None
        
        return None
    
    def get_existing_tickers(self, start_date: str, end_date: str) -> set:
        """
        Get set of tickers that already have valid data files
        
        Args:
            start_date: Required start date
            end_date: Required end date
            
        Returns:
            Set of ticker symbols that already have complete data
        """
        existing = set()
        
        try:
            logger.info(f"Checking data/prices/ directory...")
            
            # Ensure directory exists
            if not os.path.exists(self.data_dir):
                logger.info(f"Directory {self.data_dir} does not exist, creating it...")
                os.makedirs(self.data_dir, exist_ok=True)
                logger.info(f"Created directory: {self.data_dir}")
                return existing
            
            # Check if it's actually a directory
            if not os.path.isdir(self.data_dir):
                logger.warning(f"{self.data_dir} exists but is not a directory")
                return existing
            
            # List files in directory
            try:
                files = os.listdir(self.data_dir)
                parquet_files = [f for f in files if f.endswith('.parquet')]
                logger.info(f"Found {len(parquet_files)} existing .parquet files")
            except PermissionError as e:
                logger.error(f"Permission denied accessing {self.data_dir}: {e}")
                return existing
            except Exception as e:
                logger.error(f"Error listing files in {self.data_dir}: {e}")
                return existing
            
            if len(parquet_files) == 0:
                logger.info("No existing .parquet files found")
                return existing
            
            # Parse date range
            try:
                req_start = pd.to_datetime(start_date)
                req_end = pd.to_datetime(end_date)
            except Exception as e:
                logger.error(f"Error parsing date range: {e}")
                return existing
            
            # Check each parquet file
            valid_count = 0
            for file in parquet_files:
                ticker = file.replace('.parquet', '')
                cache_path = os.path.join(self.data_dir, file)
                
                try:
                    df = pd.read_parquet(cache_path)
                    if not df.empty:
                        df_start = df.index.min()
                        df_end = df.index.max()
                        
                        # Check if cached data covers our date range
                        if df_start <= req_start and df_end >= req_end:
                            existing.add(ticker)
                            valid_count += 1
                except Exception as e:
                    logger.debug(f"Error checking cache for {ticker}: {e}")
                    continue
            
            logger.info(f"Found {valid_count} valid existing tickers with complete data")
            
        except Exception as e:
            logger.error(f"Unexpected error in get_existing_tickers: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            # Return empty set on any error - will download everything
            return existing
        
        return existing
    
    def fetch_all_tickers(self, tickers: List[str], start_date: str, end_date: str, 
                          use_cache: bool = True, save_progress_every: int = 10) -> Dict[str, pd.DataFrame]:
        """
        Fetch price data for all tickers with resumable downloads
        
        Args:
            tickers: List of ticker symbols
            start_date: Start date for price data
            end_date: End date for price data
            use_cache: Whether to use cached data
            save_progress_every: Save progress after every N tickers (default: 10)
            
        Returns:
            Dict of {ticker: DataFrame}
        """
        results = {}
        failed = []
        cached_count = 0
        
        # Get existing tickers
        existing_tickers = set()
        if use_cache:
            existing_tickers = self.get_existing_tickers(start_date, end_date)
            logger.info(f"Found {len(existing_tickers)} existing tickers with valid data")
        
        # Filter out already downloaded tickers
        tickers_to_download = [t for t in tickers if t not in existing_tickers]
        
        if existing_tickers:
            # Load existing data
            for ticker in existing_tickers:
                cache_path = os.path.join(self.data_dir, f"{ticker}.parquet")
                try:
                    df = pd.read_parquet(cache_path)
                    if not df.empty:
                        results[ticker] = df
                        cached_count += 1
                except Exception as e:
                    logger.warning(f"Error loading existing data for {ticker}: {e}")
        
        total_tickers = len(tickers)
        remaining = len(tickers_to_download)
        
        logger.info(f"Tickers to process: {total_tickers}")
        logger.info(f"  - Already downloaded: {len(existing_tickers)} (skipping)")
        logger.info(f"  - Remaining to download: {remaining}")
        
        if remaining == 0:
            logger.info("All tickers already downloaded!")
            return results
        
        logger.info(f"Downloading price data for {remaining} tickers from {start_date} to {end_date}")
        
        for idx, ticker in enumerate(tqdm(tickers_to_download, desc="Fetching prices"), 1):
            cache_path = os.path.join(self.data_dir, f"{ticker}.parquet")
            
            # Fetch new data with retry logic
            logger.info(f"[{idx}/{remaining}] Fetching {ticker}...")
            df = self.fetch_price_data(ticker, start_date, end_date, max_retries=3)
            
            if df is not None and not df.empty:
                results[ticker] = df
                # Save to cache immediately
                try:
                    df.to_parquet(cache_path)
                    logger.debug(f"Saved {ticker} to cache ({len(df)} rows)")
                except Exception as e:
                    logger.warning(f"Error saving cache for {ticker}: {e}")
            else:
                failed.append(ticker)
                logger.warning(f"[{idx}/{remaining}] Failed to fetch {ticker}")
            
            # Rate limiting: wait 1 second between tickers
            time.sleep(1.0)
            
            # Save progress after every N tickers
            if idx % save_progress_every == 0:
                logger.info(f"Progress: {idx}/{remaining} tickers downloaded ({len(results)} total, {cached_count} cached, {len(failed)} failed)")
                # Save intermediate results
                try:
                    for saved_ticker, saved_df in results.items():
                        if saved_ticker not in existing_tickers:  # Only save newly downloaded
                            save_path = os.path.join(self.data_dir, f"{saved_ticker}.parquet")
                            if not os.path.exists(save_path):
                                saved_df.to_parquet(save_path)
                except Exception as e:
                    logger.warning(f"Error saving intermediate progress: {e}")
        
        logger.info(f"\n✅ Successfully fetched {len(results)}/{total_tickers} tickers")
        logger.info(f"   - Already had: {cached_count}")
        logger.info(f"   - New downloads: {len(results) - cached_count}")
        logger.info(f"   - Failed: {len(failed)}")
        
        if failed:
            logger.warning(f"Failed tickers ({len(failed)}): {', '.join(failed[:20])}{'...' if len(failed) > 20 else ''}")
        
        return results
    
    def run(self, start_date: str = "2023-01-01", end_date: str = "2024-12-31", 
            use_market_cap_filter: bool = True, ticker_list: Optional[List[str]] = None) -> Dict[str, pd.DataFrame]:
        """
        Main entry point: Get tickers, filter by market cap, fetch data
        
        Args:
            start_date: Start date for price data
            end_date: End date for price data
            use_market_cap_filter: Whether to filter by market cap
            ticker_list: Optional pre-defined list of tickers (skips ticker fetching)
        """
        logger.info("Starting price data fetch pipeline...")
        
        # Get tickers
        if ticker_list is None:
            tickers = self.get_russell2000_tickers()
        else:
            tickers = ticker_list
            logger.info(f"Using provided ticker list: {len(tickers)} tickers")
        
        # Filter by market cap if requested
        if use_market_cap_filter:
            tickers = self.filter_by_market_cap(tickers)
        
        # Fetch data
        results = self.fetch_all_tickers(tickers, start_date, end_date)
        
        # Save summary
        summary_path = os.path.join(self.data_dir, "fetch_summary.txt")
        with open(summary_path, 'w') as f:
            f.write(f"Price Data Fetch Summary\n")
            f.write(f"Date: {datetime.now()}\n")
            f.write(f"Date Range: {start_date} to {end_date}\n")
            f.write(f"Market Cap Filter: ${self.min_market_cap:,} - ${self.max_market_cap:,}\n")
            f.write(f"Total Tickers Fetched: {len(results)}\n")
            f.write(f"Tickers: {', '.join(results.keys())}\n")
        
        logger.info(f"Price fetch complete. Results saved to {self.data_dir}")
        return results


if __name__ == "__main__":
    # Test script
    logging.basicConfig(level=logging.INFO)
    fetcher = PriceFetcher()
    results = fetcher.run()
    print(f"\n✅ Fetched data for {len(results)} tickers")
