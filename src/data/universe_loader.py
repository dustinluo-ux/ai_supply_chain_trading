"""
Universe Loader
Loads and filters stock tickers from historical data directory
Supports multiple data sources (NASDAQ, S&P500, etc.) and formats (CSV, Parquet)
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import yaml
import logging
import random
from datetime import datetime

logger = logging.getLogger(__name__)


class UniverseLoader:
    """Loads and filters stock tickers from historical data directory"""
    
    def __init__(self, config_path: str = "config/data_config.yaml"):
        """
        Initialize Universe Loader
        
        Args:
            config_path: Path to data configuration YAML file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.data_dir = Path(self.config['data_sources']['data_dir'])
        self.file_format = self.config['data_sources'].get('file_format', 'auto')
        
        logger.info(f"UniverseLoader initialized with data_dir: {self.data_dir}")
    
    def _load_config(self) -> dict:
        """Load configuration from YAML file"""
        if not self.config_path.exists():
            logger.warning(f"Config file not found: {self.config_path}, using defaults")
            return self._default_config()
        
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            logger.error(f"Error loading config: {e}, using defaults")
            return self._default_config()
    
    def _default_config(self) -> dict:
        """Return default configuration"""
        return {
            'data_sources': {
                'data_dir': 'data/prices',
                'file_format': 'auto',
                'subdirectories': []
            },
            'universe_selection': {
                'source': 'all',
                'max_tickers': 50,
                'min_data_points': 252,
                'date_range': {
                    'start': '2023-01-01',
                    'end': '2024-12-31'
                }
            },
            'filtering': {
                'exclude_tickers': [],
                'require_news': False,
                'min_price': 1.0,
                'max_missing_days_ratio': 0.1
            }
        }
    
    def find_data_files(self) -> List[Path]:
        """
        Find all data files in the data directory
        
        Returns:
            List of file paths
        """
        files = []
        
        # Get subdirectories to search
        subdirs = self.config['data_sources'].get('subdirectories', [])
        if subdirs:
            search_dirs = [self.data_dir / subdir for subdir in subdirs]
        else:
            search_dirs = [self.data_dir]
        
        # Determine file extension
        if self.file_format == 'auto':
            # Try both CSV and parquet
            extensions = ['.csv', '.parquet']
        elif self.file_format == 'csv':
            extensions = ['.csv']
        elif self.file_format == 'parquet':
            extensions = ['.parquet']
        else:
            extensions = ['.csv', '.parquet']
        
        # Track files by ticker to avoid duplicates efficiently
        ticker_to_file = {}  # ticker -> (file_path, source_dir)
        
        # Search for files
        for search_dir in search_dirs:
            search_path = Path(search_dir)
            if not search_path.exists():
                logger.warning(f"Directory does not exist: {search_path}")
                print(f"  [WARNING] Directory does not exist: {search_path}", flush=True)
                continue
            
            for ext in extensions:
                found_files = list(search_path.glob(f"*{ext}"))
                for file_path in found_files:
                    ticker = file_path.stem  # Get ticker from filename
                    # Only add if we haven't seen this ticker before
                    # This prevents duplicates across directories (e.g., AAPL in both nasdaq and sp500)
                    if ticker not in ticker_to_file:
                        ticker_to_file[ticker] = (file_path, search_dir)
                
                if found_files:
                    print(f"  [DEBUG] Found {len(found_files)} {ext} files in {search_path}", flush=True)
        
        # Convert to list of unique files
        files = [file_path for file_path, _ in ticker_to_file.values()]
        duplicates_removed = sum(len(list(search_path.glob(f"*{ext}"))) for search_path in search_dirs for ext in extensions) - len(files)
        if duplicates_removed > 0:
            print(f"  [DEBUG] Removed {duplicates_removed} duplicate tickers across directories", flush=True)
        
        logger.info(f"Found {len(files)} unique data files (removed {duplicates_removed} duplicates)")
        
        return files
    
    def validate_ticker_data(self, file_path: Path, stats: Dict = None, sample_errors: List = None) -> Tuple[bool, Optional[Dict]]:
        """
        Validate a ticker's data file
        
        Args:
            file_path: Path to data file
            
        Returns:
            Tuple of (is_valid, metadata_dict)
        """
        try:
            # Load data
            if file_path.suffix == '.csv':
                # Try reading CSV - handle different formats
                try:
                    # First try: assume first column is date index, try dayfirst=True for DD-MM-YYYY format
                    df = pd.read_csv(file_path, index_col=0, parse_dates=True, dayfirst=True)
                except Exception as e1:
                    try:
                        # Second try: read without index, find date column
                        df_temp = pd.read_csv(file_path, nrows=5)
                        date_col = None
                        for col in df_temp.columns:
                            if 'date' in col.lower() or 'time' in col.lower():
                                date_col = col
                                break
                        
                        if date_col:
                            df = pd.read_csv(file_path, index_col=date_col, parse_dates=True)
                        else:
                            # Third try: use first column as index
                            df = pd.read_csv(file_path)
                            if len(df.columns) > 0:
                                df = df.set_index(df.columns[0])
                                # Try to parse index as dates
                                try:
                                    df.index = pd.to_datetime(df.index)
                                except:
                                    pass
                    except Exception as e2:
                        logger.debug(f"{file_path.stem}: Error loading CSV: {e1}, {e2}")
                        return False, None
            elif file_path.suffix == '.parquet':
                df = pd.read_parquet(file_path)
            else:
                return False, None
            
            if df.empty:
                return False, None
            
            # Ensure datetime index
            if not isinstance(df.index, pd.DatetimeIndex):
                if 'Date' in df.columns:
                    df = df.set_index('Date')
                elif 'date' in df.columns:
                    df = df.set_index('date')
                else:
                    # Try to convert index to datetime
                    try:
                        df.index = pd.to_datetime(df.index)
                    except:
                        logger.debug(f"{file_path.stem}: Cannot convert index to datetime")
                        return False, None
            
            # Normalize column names
            df.columns = [col.lower().strip() for col in df.columns]
            
            # Check required columns - try common variations
            # After normalization, "Close" becomes "close", so this should work
            if 'close' not in df.columns:
                # Try other common names (case-insensitive check)
                col_lower = {col.lower(): col for col in df.columns}
                if 'adj close' in col_lower or 'adjusted close' in col_lower:
                    close_col = col_lower.get('adj close') or col_lower.get('adjusted close')
                    df['close'] = df[close_col]
                elif 'adj_close' in col_lower:
                    df['close'] = df[col_lower['adj_close']]
                elif 'closing price' in col_lower:
                    df['close'] = df[col_lower['closing price']]
                elif 'price' in col_lower:
                    df['close'] = df[col_lower['price']]
                else:
                    # DEBUG: This is likely the issue - columns aren't being normalized correctly
                    if stats and sample_errors is not None and len(sample_errors) < 5:
                        sample_errors.append(f"{file_path.stem}: No 'close' after norm. Original cols: {[c for c in df.columns if 'close' in c.lower()]}")
                    return False, None
            
            # Filter to date range
            date_range = self.config['universe_selection']['date_range']
            start_date = pd.to_datetime(date_range['start'])
            end_date = pd.to_datetime(date_range['end'])
            
            # Check what date range we actually have
            data_start = df.index.min()
            data_end = df.index.max()
            
            # Filter to requested range
            df_filtered = df[(df.index >= start_date) & (df.index <= end_date)]
            
            if df_filtered.empty:
                # If no data in exact range, try to use whatever recent data we have
                # This handles cases where data doesn't exactly match the requested range
                recent_cutoff = pd.to_datetime('2019-01-01')
                df_recent = df[df.index >= recent_cutoff]
                
                if df_recent.empty or len(df_recent) < min_points:
                    # DEBUG: Log why filtering failed - but only for first few files to avoid spam
                    if not hasattr(self, '_debug_count'):
                        self._debug_count = 0
                    self._debug_count += 1
                    
                    if self._debug_count <= 3:
                        logger.debug(f"{file_path.stem}: No data in range {start_date.date()} to {end_date.date()}. Data range: {data_start.date()} to {data_end.date()}")
                    return False, None
                else:
                    # Use recent data even if not in exact requested range
                    df_filtered = df_recent
            
            # Check minimum data points (already checked above if using recent data)
            min_points = self.config['universe_selection']['min_data_points']
            if len(df_filtered) < min_points:
                if stats and sample_errors is not None and len(sample_errors) < 5:
                    sample_errors.append(f"{file_path.stem}: Only {len(df_filtered)} points (need {min_points})")
                return False, None
            
            # Check for missing days (gaps) - be more lenient
            max_missing_ratio = self.config['filtering']['max_missing_days_ratio']
            # Use actual date range of filtered data, not requested range
            date_range_days = (df_filtered.index.max() - df_filtered.index.min()).days
            expected_trading_days = max(1, int(date_range_days * 0.7))  # ~70% are trading days
            if expected_trading_days > 0:
                missing_ratio = 1.0 - (len(df_filtered) / expected_trading_days)
                if missing_ratio > max_missing_ratio:
                    if stats and sample_errors is not None and len(sample_errors) < 5:
                        sample_errors.append(f"{file_path.stem}: Too many gaps ({missing_ratio:.1%} > {max_missing_ratio:.1%})")
                    return False, None
            
            # Check minimum price
            min_price = self.config['filtering']['min_price']
            min_close = df_filtered['close'].min()
            if min_close < min_price:
                if stats and sample_errors is not None and len(sample_errors) < 5:
                    sample_errors.append(f"{file_path.stem}: Price too low (min={min_close:.2f} < {min_price})")
                return False, None
            
            # Extract metadata
            metadata = {
                'ticker': file_path.stem,
                'file_path': str(file_path),
                'date_range': (df_filtered.index.min(), df_filtered.index.max()),
                'data_points': len(df_filtered),
                'has_volume': 'volume' in df.columns,
                'avg_price': df_filtered['close'].mean(),
                'price_range': (df_filtered['close'].min(), df_filtered['close'].max())
            }
            
            return True, metadata
            
        except Exception as e:
            logger.debug(f"Error validating {file_path}: {e}")
            return False, None
    
    def check_news_data(self, ticker: str, news_dir: Path = None) -> bool:
        """
        Check if news data exists for a ticker
        
        Args:
            ticker: Stock ticker symbol
            news_dir: Directory containing news data (default: data/news)
            
        Returns:
            True if news data exists
        """
        if news_dir is None:
            news_dir = Path("data/news")
        
        # Check for main news file
        news_file = news_dir / f"{ticker}_news.json"
        if news_file.exists():
            return True
        
        # Check for monthly files
        monthly_files = list(news_dir.glob(f"{ticker}_2023_*.json")) + list(news_dir.glob(f"{ticker}_2024_*.json"))
        if monthly_files:
            return True
        
        return False
    
    def load_universe(self, max_tickers: Optional[int] = None, 
                     require_news: Optional[bool] = None,
                     rank_by_supply_chain: bool = True,
                     supply_chain_pool_size: Optional[int] = None) -> List[Dict]:
        """
        Load and filter universe of tickers
        
        Args:
            max_tickers: Maximum number of tickers (overrides config)
            require_news: Require news data (overrides config)
            rank_by_supply_chain: If True, rank stocks by supply chain relevance before selecting top N
            supply_chain_pool_size: Number of stocks to analyze for supply chain (default: 3x max_tickers)
            
        Returns:
            List of ticker metadata dictionaries
        """
        # Get configuration
        max_tickers = max_tickers or self.config['universe_selection']['max_tickers']
        require_news = require_news if require_news is not None else self.config['filtering']['require_news']
        exclude_tickers = set(self.config['filtering']['exclude_tickers'])
        news_dir = Path("data/news")
        
        # Determine pool size for supply chain analysis
        if rank_by_supply_chain:
            pool_size = supply_chain_pool_size or (max_tickers * 3)  # Default: analyze 3x the final size
        else:
            pool_size = max_tickers
        
        # Find all data files
        files = self.find_data_files()
        
        if not files:
            logger.warning("No data files found!")
            return []
        
        # Validate each file
        valid_tickers = []
        validation_stats = {
            'total': len(files), 
            'excluded': 0, 
            'invalid': 0, 
            'valid': 0,
            'reasons': {'no_close': 0, 'no_data_range': 0, 'insufficient_points': 0, 'too_many_gaps': 0, 'price_too_low': 0, 'other': 0}
        }
        
        sample_errors = []  # Store first 5 errors for debugging
        
        for file_path in files:
            ticker = file_path.stem
            
            # Skip excluded tickers
            if ticker in exclude_tickers:
                validation_stats['excluded'] += 1
                continue
            
            # Validate data
            is_valid, metadata = self.validate_ticker_data(file_path, validation_stats, sample_errors)
            if not is_valid:
                validation_stats['invalid'] += 1
                continue
            
            validation_stats['valid'] += 1
            
            # Check news requirement
            if require_news:
                has_news = self.check_news_data(ticker, news_dir)
                if not has_news:
                    continue
                metadata['has_news'] = True
            else:
                metadata['has_news'] = self.check_news_data(ticker, news_dir)
            
            valid_tickers.append(metadata)
        
        # Sort by ticker name for consistency (before any ranking)
        valid_tickers.sort(key=lambda x: x['ticker'])
        
        # DEBUG: Print before limiting
        print(f"  [DEBUG] Before limiting: {len(valid_tickers)} valid tickers found", flush=True)
        print(f"  [DEBUG] max_tickers parameter: {max_tickers}", flush=True)
        
        # If ranking by supply chain, analyze larger pool first
        if rank_by_supply_chain and len(valid_tickers) > max_tickers:
            print(f"  [INFO] Ranking stocks by supply chain relevance (analyzing {min(pool_size, len(valid_tickers))} stocks)...", flush=True)
            
            # Prioritize tickers with news for supply chain analysis
            with_news = [t for t in valid_tickers if t.get('has_news', False)]
            without_news = [t for t in valid_tickers if not t.get('has_news', False)]
            
            # FIX: Use stratified sampling instead of alphabetical slice
            # Strategy: Always include known AI stocks, then sample from rest
            random.seed(42)  # Reproducible sampling
            
            # Known AI supply chain leaders (always include if available)
            known_ai_stocks = ['NVDA', 'AMD', 'TSM', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 
                             'INTC', 'QCOM', 'AVGO', 'MU', 'LRCX', 'KLAC', 'AMAT', 'SNPS', 'CDNS']
            
            # Separate known AI stocks from others
            known_ai_in_pool = [t for t in with_news if t['ticker'] in known_ai_stocks]
            other_with_news = [t for t in with_news if t['ticker'] not in known_ai_stocks]
            
            # Stratified sampling: Group by first letter, sample proportionally
            remaining_slots = pool_size - len(known_ai_in_pool)
            
            if remaining_slots > 0 and len(other_with_news) > 0:
                # Group by first letter
                by_letter = {}
                for ticker in other_with_news:
                    first_letter = ticker['ticker'][0].upper()
                    if first_letter not in by_letter:
                        by_letter[first_letter] = []
                    by_letter[first_letter].append(ticker)
                
                # Sample proportionally from each letter group
                sampled = []
                letters = sorted(by_letter.keys())
                if len(letters) > 0:
                    samples_per_letter = max(1, remaining_slots // len(letters))
                    
                    for letter in letters:
                        if len(sampled) >= remaining_slots:
                            break
                        letter_stocks = by_letter[letter]
                        if len(letter_stocks) <= samples_per_letter:
                            sampled.extend(letter_stocks)
                        else:
                            sampled.extend(random.sample(letter_stocks, samples_per_letter))
                
                # If we still need more, fill randomly from remaining
                if len(sampled) < remaining_slots:
                    remaining = [t for t in other_with_news if t not in sampled]
                    needed = remaining_slots - len(sampled)
                    if len(remaining) >= needed:
                        sampled.extend(random.sample(remaining, needed))
                    else:
                        sampled.extend(remaining)
                
                pool_tickers = known_ai_in_pool + sampled[:remaining_slots]
            elif len(known_ai_in_pool) >= pool_size:
                # If we have enough known AI stocks, just use those
                pool_tickers = known_ai_in_pool[:pool_size]
            else:
                # Fallback: random sample from all with news
                if len(with_news) >= pool_size:
                    pool_tickers = random.sample(with_news, pool_size)
                else:
                    pool_tickers = with_news + random.sample(without_news, min(pool_size - len(with_news), len(without_news)))
            
            # Ensure we have exactly pool_size (or all available)
            if len(pool_tickers) > pool_size:
                pool_tickers = pool_tickers[:pool_size]
            
            print(f"    [INFO] Pool includes {len(known_ai_in_pool)} known AI stocks: {[t['ticker'] for t in known_ai_in_pool]}", flush=True)
            print(f"    [INFO] Pool total: {len(pool_tickers)} stocks (stratified sampling)", flush=True)
            
            # Rank by supply chain scores
            ranked_tickers = self._rank_by_supply_chain([t['ticker'] for t in pool_tickers])
            
            # Map ranked tickers back to metadata
            ranked_dict = {t['ticker']: t for t in pool_tickers}
            valid_tickers = [ranked_dict[ticker] for ticker in ranked_tickers if ticker in ranked_dict]
            
            # Select top N
            valid_tickers = valid_tickers[:max_tickers]
            print(f"  [INFO] Selected top {len(valid_tickers)} stocks by supply chain relevance", flush=True)
            
        elif len(valid_tickers) > max_tickers:
            # Fallback: Prioritize tickers with news data if available
            with_news = [t for t in valid_tickers if t.get('has_news', False)]
            without_news = [t for t in valid_tickers if not t.get('has_news', False)]
            
            print(f"  [DEBUG] Tickers with news: {len(with_news)}, without news: {len(without_news)}", flush=True)
            
            if len(with_news) >= max_tickers:
                valid_tickers = with_news[:max_tickers]
                print(f"  [DEBUG] Using only tickers with news (limited to {max_tickers})", flush=True)
            else:
                valid_tickers = with_news + without_news[:max_tickers - len(with_news)]
                print(f"  [DEBUG] Using {len(with_news)} with news + {max_tickers - len(with_news)} without news", flush=True)
        else:
            print(f"  [DEBUG] Not limiting: {len(valid_tickers)} <= {max_tickers}", flush=True)
        
        # Print validation stats
        print(f"  Validation: {validation_stats['valid']} valid, {validation_stats['invalid']} invalid, {validation_stats['excluded']} excluded out of {validation_stats['total']} files", flush=True)
        print(f"  [DEBUG] Returning {len(valid_tickers)} tickers from load_universe()", flush=True)
        
        if sample_errors:
            print(f"  Sample validation errors (first 5):", flush=True)
            for error in sample_errors[:5]:
                print(f"    {error}", flush=True)
        
        logger.info(f"Loaded {len(valid_tickers)} valid tickers from {len(files)} files")
        
        if len(valid_tickers) == 0 and len(files) > 0:
            print(f"  [WARNING] No valid tickers found! Check date range and filtering criteria.", flush=True)
            print(f"  [DEBUG] Date range: {self.config['universe_selection']['date_range']}", flush=True)
            print(f"  [DEBUG] Min data points: {self.config['universe_selection']['min_data_points']}", flush=True)
            print(f"  [DEBUG] Try: 1) Adjust date_range in config, 2) Reduce min_data_points, 3) Check CSV format", flush=True)
        
        return valid_tickers
    
    def _rank_by_supply_chain(self, tickers: List[str]) -> List[str]:
        """
        Rank tickers by supply chain relevance (AI exposure).
        
        Args:
            tickers: List of ticker symbols to rank
            
        Returns:
            List of tickers ranked by supply chain score (highest first)
        """
        try:
            from src.signals.supply_chain_scanner import SupplyChainScanner
            
            print(f"    [INFO] Analyzing {len(tickers)} stocks for supply chain relevance...", flush=True)
            # Use Gemini instead of FinBERT - it can actually extract relationships
            # FinBERT only does sentiment and has false positives (e.g., "AAL" matches "ai")
            scanner = SupplyChainScanner(llm_provider="gemini", llm_model="gemini-2.5-flash-lite")
            df = scanner.scan_all_tickers(tickers, use_cache=True)
            
            if df.empty:
                logger.warning("No supply chain scores generated, using alphabetical order")
                return sorted(tickers)
            
            # Rank by supply_chain_score (descending)
            df_sorted = df.sort_values('supply_chain_score', ascending=False)
            ranked = df_sorted['ticker'].tolist()
            
            # Add any tickers that weren't scored (no news/articles)
            scored_tickers = set(ranked)
            unscored = [t for t in tickers if t not in scored_tickers]
            ranked.extend(sorted(unscored))  # Add unscored at end, alphabetically
            
            top5 = ranked[:5]
            print(f"    [INFO] Top 5 by supply chain score: {top5}", flush=True)
            # Log scores for top 5 (for verification / debugging)
            score_col = df_sorted.set_index('ticker')['supply_chain_score']
            for t in top5:
                if t in score_col.index:
                    print(f"    [INFO]   {t}: supply_chain_score={float(score_col[t]):.4f}", flush=True)
            return ranked
            
        except Exception as e:
            logger.error(f"Error ranking by supply chain: {e}")
            logger.warning("Falling back to alphabetical order")
            return sorted(tickers)
    
    def get_universe_summary(self, tickers: List[Dict]) -> Dict:
        """
        Generate summary statistics for the universe
        
        Args:
            tickers: List of ticker metadata dictionaries
            
        Returns:
            Summary dictionary
        """
        if not tickers:
            return {
                'count': 0,
                'with_news': 0,
                'date_range': None,
                'avg_data_points': 0
            }
        
        with_news = sum(1 for t in tickers if t.get('has_news', False))
        date_ranges = [t['date_range'] for t in tickers if 'date_range' in t]
        data_points = [t['data_points'] for t in tickers if 'data_points' in t]
        
        if date_ranges:
            min_date = min(d[0] for d in date_ranges)
            max_date = max(d[1] for d in date_ranges)
        else:
            min_date = max_date = None
        
        return {
            'count': len(tickers),
            'with_news': with_news,
            'without_news': len(tickers) - with_news,
            'news_coverage': with_news / len(tickers) if tickers else 0.0,
            'date_range': (min_date, max_date) if min_date else None,
            'avg_data_points': np.mean(data_points) if data_points else 0,
            'min_data_points': min(data_points) if data_points else 0,
            'max_data_points': max(data_points) if data_points else 0
        }
