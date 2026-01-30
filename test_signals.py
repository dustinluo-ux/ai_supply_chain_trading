"""
Test different signal combinations: technical-only, news-only, and combined
Compares Sharpe ratios to find best approach

OPTIMIZED: Loads data once and reuses it across all 3 backtests
"""
import pandas as pd
import numpy as np
import yaml
import time
import argparse
import sys
import json
from pathlib import Path
from datetime import timedelta, datetime
import yaml

from src.data.universe_loader import UniverseLoader
from src.signals.news_analyzer import NewsAnalyzer
from src.signals.signal_combiner import SignalCombiner

# ============================================================================
# DEBUG MODE - Set to True for fast iteration
# ============================================================================
# ULTRA-MINIMAL VERIFICATION: 1 ticker, 1 week
DEBUG_MODE = False  # Set to False to test full universe
DEBUG_STOCKS = ['AAPL']  # Just 1 stock for verification
DEBUG_START_DATE = None  # Use auto-detected aligned date range
DEBUG_END_DATE = None    # Use auto-detected aligned date range
MAX_WEEKLY_ITERATIONS = 4  # Full month

if DEBUG_MODE:
    print("\n" + "=" * 60)
    print("[DEBUG MODE] Running limited test:")
    print(f"  Stocks: {DEBUG_STOCKS}")
    if DEBUG_START_DATE and DEBUG_END_DATE:
        print(f"  Period: {DEBUG_START_DATE} to {DEBUG_END_DATE}")
    else:
        print(f"  Period: Auto-detected (aligned with price/news data)")
    print(f"  Max iterations: {MAX_WEEKLY_ITERATIONS}")
    print("=" * 60 + "\n", flush=True)

# ============================================================================
# Setup file logging to capture all output
# ============================================================================
# Create outputs directory if it doesn't exist
outputs_dir = Path("outputs")
outputs_dir.mkdir(exist_ok=True)

# Create log file
log_filename = outputs_dir / f"backtest_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
log_file = open(log_filename, 'w', encoding='utf-8')

# Duplicate stdout to both console and file
class Logger:
    def __init__(self, terminal, file):
        self.terminal = terminal
        self.file = file
    def write(self, message):
        self.terminal.write(message)
        self.file.write(message)
    def flush(self):
        self.terminal.flush()
        self.file.flush()

# Save original stdout before replacing it
original_stdout = sys.stdout
sys.stdout = Logger(sys.stdout, log_file)
print(f"Logging to: {log_filename}")
print("=" * 60)

# Parse arguments
parser = argparse.ArgumentParser(description='Test signal combinations')
parser.add_argument('--universe-size', type=int, default=15, help='Maximum number of tickers (default: 15)')
parser.add_argument('--data-dir', type=str, default=None, help='Override data directory from config')
parser.add_argument('--top-n', type=int, default=10, help='Number of top stocks to select each week (default: 10)')
args = parser.parse_args()

print("=" * 60)
print("SIGNAL COMBINATION TESTING (OPTIMIZED)")
print("=" * 60)

# ============================================================================
# STEP 1: Load universe and price data ONCE
# ============================================================================
start_time = time.time()

print("\n[1/5] Loading universe...", flush=True)
universe_loader = UniverseLoader()
if args.data_dir:
    universe_loader.data_dir = Path(args.data_dir)
    universe_loader.config['data_sources']['data_dir'] = str(args.data_dir)

# Load universe with supply chain ranking enabled
ticker_metadata = universe_loader.load_universe(
    max_tickers=args.universe_size,
    rank_by_supply_chain=True,  # Enable supply chain ranking
    supply_chain_pool_size=args.universe_size * 3  # Analyze 3x the final size
)
summary = universe_loader.get_universe_summary(ticker_metadata)

# CRITICAL DEBUG: Check what was actually loaded
print(f"\n[CRITICAL DEBUG] Universe loading:", flush=True)
print(f"  Requested: {args.universe_size} tickers", flush=True)
print(f"  Actually loaded: {len(ticker_metadata)} tickers", flush=True)
print(f"  Ticker symbols: {[t['ticker'] for t in ticker_metadata]}", flush=True)

if summary['count'] == 0:
    print("ERROR: No tickers found! Check data_config.yaml and data directory.")
    print(f"  Data directory: {universe_loader.data_dir}")
    print(f"  Config path: {universe_loader.config_path}")
    exit(1)

TICKERS = [t['ticker'] for t in ticker_metadata]
ticker_file_map = {t['ticker']: Path(t['file_path']) for t in ticker_metadata}
DATA_DIR = universe_loader.data_dir

# Check supply chain database coverage
try:
    from src.data.supply_chain_manager import SupplyChainManager
    supply_chain_mgr = SupplyChainManager()
    coverage_status = supply_chain_mgr.ensure_coverage(
        TICKERS,
        max_age_months=6,
        auto_research=False  # Don't auto-download during backtest
    )
    
    # Warn if missing data
    missing = [t for t, s in coverage_status.items() if s in ['missing', 'stale']]
    if missing:
        print(f"\n[WARNING] Supply chain data missing/stale for {len(missing)} stocks:", flush=True)
        print(f"  Missing/stale: {missing[:10]}{'...' if len(missing) > 10 else ''}", flush=True)
        print(f"  Run: python scripts/expand_database_core_stocks.py", flush=True)
        print(f"  Or check: docs/RESEARCH_QUEUE.txt", flush=True)
    else:
        print(f"\n[OK] Supply chain database coverage: All {len(TICKERS)} stocks covered", flush=True)
except Exception as e:
    print(f"\n[WARNING] Could not check supply chain database: {e}", flush=True)

# Filter stocks in DEBUG_MODE
if DEBUG_MODE:
    original_count = len(TICKERS)
    TICKERS = [s for s in TICKERS if s in DEBUG_STOCKS]
    print(f"  [DEBUG] Limited to {len(TICKERS)} stocks: {TICKERS} (from {original_count} total)", flush=True)
    if len(TICKERS) == 0:
        print(f"  [ERROR] DEBUG_STOCKS {DEBUG_STOCKS} not found in universe!", flush=True)
        print(f"  Available stocks: {[t['ticker'] for t in ticker_metadata][:20]}...", flush=True)
        exit(1)

print(f"  [OK] Loaded {summary['count']} tickers", flush=True)
print(f"  [DEBUG] TICKERS list length: {len(TICKERS)}", flush=True)
print(f"  [DEBUG] TICKERS list: {TICKERS}", flush=True)
if summary['date_range']:
    print(f"  Date range: {summary['date_range'][0].strftime('%Y-%m-%d')} to {summary['date_range'][1].strftime('%Y-%m-%d')}", flush=True)
print(f"  News coverage: {summary['with_news']}/{summary['count']} tickers ({summary['news_coverage']:.1%})", flush=True)

# Load signal weights from config
config_path = Path("config/signal_weights.yaml")
if config_path.exists():
    with open(config_path, 'r') as f:
        signal_config = yaml.safe_load(f)
    weights = signal_config.get('signal_weights', {})
    tech_config = signal_config.get('technical_indicators', {})
    news_config = signal_config.get('news_analysis', {})
    weighting_method = signal_config.get('weighting_method', 'proportional')
else:
    weights = {'supply_chain': 0.4, 'sentiment': 0.3, 'momentum': 0.2, 'volume': 0.1}
    tech_config = {'momentum_period': 20, 'volume_period': 30, 'rsi_period': 14}
    news_config = {'enabled': True, 'lookback_days': 7, 'min_articles': 1}
    weighting_method = 'proportional'

# ============================================================================
# STEP 2: Load ALL price data ONCE
# ============================================================================
print(f"\n[2/5] Loading price data from {len(TICKERS)} files...", flush=True)
prices_dict = {}
for i, ticker in enumerate(TICKERS, 1):
    # Get file path from metadata - it should be the correct path from UniverseLoader
    file_path = None
    if ticker in ticker_file_map:
        file_path_str = str(ticker_file_map[ticker])
        # Handle both absolute and relative paths
        if Path(file_path_str).is_absolute():
            file_path = Path(file_path_str)
        else:
            # Try relative to current directory or DATA_DIR
            file_path = Path(file_path_str)
            if not file_path.exists():
                file_path = DATA_DIR / file_path_str
            if not file_path.exists():
                # Try just the filename
                file_path = DATA_DIR / Path(file_path_str).name
    
    # If still not found, try common locations (optimized to avoid searching all 4 dirs)
    # Use metadata to infer which directory to search first
    if file_path is None or not file_path.exists():
        # Infer directory from metadata path to avoid searching all 4
        if ticker in ticker_file_map:
            metadata_path_str = str(ticker_file_map[ticker]).lower()
            if 'nasdaq' in metadata_path_str:
                search_dirs = [DATA_DIR / "nasdaq" / "csv"]
            elif 'sp500' in metadata_path_str:
                search_dirs = [DATA_DIR / "sp500" / "csv"]
            elif 'nyse' in metadata_path_str:
                search_dirs = [DATA_DIR / "nyse" / "csv"]
            elif 'forbes' in metadata_path_str or 'fortune' in metadata_path_str:
                search_dirs = [DATA_DIR / "forbes2000" / "csv"]
            else:
                # Fallback: search all directories
                search_dirs = [
                    DATA_DIR / "nasdaq" / "csv",
                    DATA_DIR / "sp500" / "csv",
                    DATA_DIR / "nyse" / "csv",
                    DATA_DIR / "forbes2000" / "csv"
                ]
        else:
            # No metadata, search all directories
            search_dirs = [
                DATA_DIR / "nasdaq" / "csv",
                DATA_DIR / "sp500" / "csv",
                DATA_DIR / "nyse" / "csv",
                DATA_DIR / "forbes2000" / "csv"
            ]
        
        # Try each directory in order
        for search_dir in search_dirs:
            potential_path = search_dir / f"{ticker}.csv"
            if potential_path.exists():
                file_path = potential_path
                break
        
        # Final fallback: try root and data/prices
        if file_path is None or not file_path.exists():
            possible_paths = [
                DATA_DIR / f"{ticker}.csv",
                Path(f"data/prices/{ticker}.csv")
            ]
            for path in possible_paths:
                if path.exists():
                    file_path = path
                    break
    
    if file_path is None or not file_path.exists():
        print(f"  [WARNING] {ticker}: File not found (metadata path: {ticker_file_map.get(ticker, 'N/A')}), skipping", flush=True)
        continue
    
    try:
        df = pd.read_csv(file_path, index_col=0, parse_dates=True, dayfirst=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
        df.columns = [col.lower() for col in df.columns]
        
        # Determine actual date range from data
        data_start = df.index.min()
        data_end = df.index.max()
        
        # Try 2023 range first (to match news data which is 2023)
        try:
            df_filtered = df.loc['2023-01-01':'2023-12-31']
            if not df_filtered.empty:
                df = df_filtered
            else:
                # If no 2023 data, try 2022-2023 overlap
                df_filtered = df.loc['2022-01-01':'2023-12-31']
                if not df_filtered.empty:
                    df = df_filtered
                else:
                    # Use whatever data is available (at least 2020+)
                    df_filtered = df[df.index >= '2020-01-01']
                    if not df_filtered.empty:
                        df = df_filtered
        except Exception as e:
            # If date filtering fails, use all available data
            pass
        
        if not df.empty and 'close' in df.columns:
            prices_dict[ticker] = df
            # DEBUG: Check for volume column on first few tickers
            if i <= 3:
                has_volume = 'volume' in df.columns
                print(f"  [DEBUG] {ticker}: Columns={list(df.columns)}, Has volume={has_volume}", flush=True)
                if has_volume:
                    print(f"    Sample volume data (first 5 rows):", flush=True)
                    print(f"      {df[['close', 'volume']].head().to_string()}", flush=True)
                else:
                    print(f"    [WARNING] {ticker}: No 'volume' column! Volume signal will use default 1.0", flush=True)
            if i % 10 == 0 or i == len(TICKERS):
                print(f"  Progress: {i}/{len(TICKERS)} stocks loaded ({len(df)} rows each)...", flush=True)
        else:
            if df.empty:
                print(f"  [WARNING] {ticker}: DataFrame is empty after filtering, skipping", flush=True)
            elif 'close' not in df.columns:
                print(f"  [WARNING] {ticker}: No 'close' column found. Columns: {list(df.columns)}, skipping", flush=True)
    except Exception as e:
        print(f"  [ERROR] {ticker}: {e}", flush=True)

if not prices_dict:
    print("ERROR: No price data loaded!")
    exit(1)

data_load_time = time.time() - start_time
print(f"  [OK] Loaded {len(prices_dict)} stocks in {data_load_time:.1f}s", flush=True)

# ============================================================================
# SIGNAL STRENGTH REPORT (technical library - Master Score from indicators)
# ============================================================================
_report_ticker = "NVDA" if "NVDA" in prices_dict else (list(prices_dict.keys())[0] if prices_dict else None)
if _report_ticker:
    try:
        from src.signals.technical_library import (
            calculate_all_indicators,
            compute_signal_strength,
            OHLCV_COLS,
        )
        _df = prices_dict[_report_ticker].copy()
        _df.columns = [c.lower() for c in _df.columns]
        for _col in ["open", "high", "low"]:
            if _col not in _df.columns and "close" in _df.columns:
                _df[_col] = _df["close"]
        if "volume" not in _df.columns:
            _df["volume"] = 0.0
        if all(c in _df.columns for c in OHLCV_COLS):
            _ind = calculate_all_indicators(_df)
            _row = _ind.iloc[-1]
            _score, _result = compute_signal_strength(_row)
            print(f"\n--- Signal Strength Report ({_report_ticker}) ---", flush=True)
            print(f"  Master Score: {_score:.4f} (0=bearish, 0.5=neutral, 1=bullish)", flush=True)
            print(f"  As-of date:   {_row.name}", flush=True)
            _sub = _result.get("category_sub_scores", {})
            print("  Category sub-scores (Trend 40%, Momentum 30%, Volume 20%, Volatility 10%):", flush=True)
            for _cat, _val in _sub.items():
                print(f"    {_cat}: {_val:.4f}", flush=True)
            _breakdown = _result.get("breakdown", {})
            _top = sorted(_breakdown.items(), key=lambda x: -abs(x[1] - 0.5))[:8]
            print("  Top normalized indicators:", flush=True)
            for _k, _v in _top:
                print(f"    {_k}: {_v:.4f}", flush=True)
            print("---", flush=True)
    except Exception as e:
        print(f"  [WARNING] Signal Strength report skipped: {e}", flush=True)

# Determine actual date range from loaded data
if prices_dict:
    all_starts = [df.index.min() for df in prices_dict.values()]
    all_ends = [df.index.max() for df in prices_dict.values()]
    price_data_start = max(all_starts)  # Latest start (most restrictive)
    price_data_end = min(all_ends)      # Earliest end (most restrictive)
    print(f"  [DEBUG] Price data range: {price_data_start.date()} to {price_data_end.date()}", flush=True)
else:
    price_data_start = pd.to_datetime('2020-01-01')
    price_data_end = pd.to_datetime('2024-12-31')

# ============================================================================
# NEWS DATE RANGE DETECTION - 6+ MONTH CONTINUOUS PERIOD
# ============================================================================
# Target: 6-12 months with overlapping price AND news coverage for statistical
# significance (24+ weekly rebalances). Uses longest continuous overlap of
# price data and news (union of news ranges for universe tickers).
# ============================================================================
USE_BEST_COVERAGE = True  # Set to False to use fallback union approach
MIN_BACKTEST_MONTHS = 6   # Minimum period (24+ rebalances)
MAX_BACKTEST_MONTHS = 12  # Cap for investor presentation

print(f"\n  [DEBUG] Detecting news data date range...", flush=True)
news_dir = Path("data/news")

# Step 1: Track date ranges for ALL news files (not just tickers with price data)
# This ensures we find the month with best coverage across all available news
print(f"  [STEP 1] Scanning ALL news files to find best coverage period...", flush=True)
all_news_files = list(news_dir.glob("*_news.json"))
print(f"  [INFO] Found {len(all_news_files)} news files total", flush=True)

ticker_date_ranges = {}
tickers_scanned = 0

# Scan all news files to build date ranges
for news_file in all_news_files:
    ticker = news_file.stem.replace('_news', '')
    tickers_scanned += 1
    
    # Progress indicator for large datasets
    if tickers_scanned % 500 == 0:
        print(f"    Progress: {tickers_scanned}/{len(all_news_files)} files scanned...", flush=True)
    try:
        with open(news_file, 'r', encoding='utf-8') as f:
            articles = json.load(f)
        if isinstance(articles, list) and articles:
            dates = []
            for article in articles:
                published_at = article.get('publishedAt', '') or article.get('published_utc', '') or article.get('date', '')
                if published_at:
                    try:
                        # Handle space-separated ISO format
                        if 'T' in published_at or 'Z' in published_at or '+' in published_at or (published_at.count(' ') >= 2 and ':' in published_at):
                            date_str = published_at.replace('Z', '+00:00') if published_at.endswith('Z') else published_at
                            article_date = pd.to_datetime(date_str)
                        else:
                            article_date = pd.to_datetime(published_at)
                        if article_date.tzinfo:
                            article_date = article_date.tz_localize(None)
                        dates.append(article_date)
                    except Exception:
                        pass
            if dates:
                ticker_date_ranges[ticker] = {
                    'start': min(dates),
                    'end': max(dates),
                    'count': len(articles)
                }
    except Exception as e:
        pass

print(f"  [OK] Scanned {tickers_scanned} news files, found date ranges for {len(ticker_date_ranges)} tickers", flush=True)

news_data_start = None
news_data_end = None

if USE_BEST_COVERAGE and ticker_date_ranges and TICKERS:
    # Step 2: Find longest continuous period (6-12 months) with BOTH price AND news
    print(f"  [STEP 2] Finding 6+ month continuous period (price + news overlap)...", flush=True)
    
    # Union of news ranges for universe tickers only
    tickers_in_news = [t for t in TICKERS if t in ticker_date_ranges]
    if not tickers_in_news:
        print(f"  [WARNING] No universe tickers have news data; falling back to union approach", flush=True)
        USE_BEST_COVERAGE = False
    else:
        news_union_start = min(ticker_date_ranges[t]['start'] for t in tickers_in_news)
        news_union_end = max(ticker_date_ranges[t]['end'] for t in tickers_in_news)
        overlap_start = max(price_data_start, news_union_start)
        overlap_end = min(price_data_end, news_union_end)
        
        if overlap_start >= overlap_end:
            print(f"  [WARNING] No overlap between price and news; falling back to union approach", flush=True)
            USE_BEST_COVERAGE = False
        else:
            duration_days = (overlap_end - overlap_start).days
            duration_months = duration_days / 30.44
            print(f"  [INFO] Price/news overlap: {overlap_start.date()} to {overlap_end.date()} ({duration_months:.1f} months)", flush=True)
            
            # Use 6-12 months within overlap (start at overlap start, month-aligned)
            if duration_months >= MIN_BACKTEST_MONTHS:
                use_months = min(MAX_BACKTEST_MONTHS, int(duration_months))
                print(f"  [OK] Using {use_months} months (target 6-12 for statistical significance)", flush=True)
            else:
                use_months = max(1, int(round(duration_months)))
                print(f"  [WARNING] Overlap has only {duration_months:.1f} months; using all {use_months} month(s)", flush=True)
                print(f"  [TIP] For 6+ months ensure price and news both cover the same period (e.g. news from at least 6 months before price end)", flush=True)
            
            # Month-aligned period start (first day of month)
            period_start = overlap_start.replace(day=1)
            # End: start + use_months (last day of that month)
            period_end = period_start + pd.DateOffset(months=use_months) - pd.Timedelta(days=1)
            # Clamp to actual overlap
            period_end = min(period_end, overlap_end)
            if period_end <= period_start:
                period_end = overlap_end
            
            news_data_start = period_start
            news_data_end = period_end
            
            # Which calendar months are included
            months_in_period = pd.date_range(period_start.replace(day=1), period_end, freq='MS')
            months_list = [m.strftime('%Y-%m') for m in months_in_period]
            print(f"  [INFO] Months in period: {months_list}", flush=True)
            
            # Rebalance count (Mondays in period; need 30-day buffer for tech indicators)
            signal_start_calc = period_start + pd.Timedelta(days=30)
            signal_end_calc = period_end
            if signal_start_calc < signal_end_calc:
                mondays_in_period = pd.date_range(signal_start_calc, signal_end_calc, freq='W-MON')
                num_rebalances = len(mondays_in_period)
            else:
                num_rebalances = 0
            print(f"  [INFO] Expected rebalances (weeks): {num_rebalances}", flush=True)
            
            # Gemini estimate: 1x universe ranking at load + (weeks x tickers) news analyses (cached after first run)
            num_tickers_final = len(tickers_in_news)  # will filter again below
            gemini_ranking_calls = 1
            gemini_news_per_week = len(TICKERS) * num_rebalances if num_rebalances else 0
            print(f"  [INFO] Expected Gemini API usage: ~1 ranking run + up to {num_rebalances} weeks x {len(TICKERS)} tickers = {gemini_ranking_calls + gemini_news_per_week} analyses (cached after first run)", flush=True)
            
            # Filter to tickers with news in chosen period
            valid_tickers_with_news = [
                t for t, ranges in ticker_date_ranges.items()
                if ranges['start'] <= news_data_end and ranges['end'] >= news_data_start
            ]
            original_ticker_count = len(TICKERS)
            valid_tickers_for_backtest = [
                t for t in TICKERS
                if t in prices_dict.keys() and t in valid_tickers_with_news
            ]
            TICKERS = valid_tickers_for_backtest
            print(f"  [OK] Using period: {news_data_start.date()} to {news_data_end.date()}", flush=True)
            print(f"  [OK] {len(valid_tickers_with_news)} tickers have news in period; {len(TICKERS)} tickers for backtest (price + news)", flush=True)
            print(f"  [OK] Filtered TICKERS: {original_ticker_count} -> {len(TICKERS)}", flush=True)

# Only use fallback if best coverage didn't set the dates
if (not USE_BEST_COVERAGE or not ticker_date_ranges) and (news_data_start is None or news_data_end is None):
    # Fallback: Use union approach (original logic)
    print(f"  [FALLBACK] Using union approach (original logic)", flush=True)
    sample_tickers = list(prices_dict.keys())[:10]
    
    for ticker in sample_tickers:
        news_file = news_dir / f"{ticker}_news.json"
        if news_file.exists():
            try:
                with open(news_file, 'r', encoding='utf-8') as f:
                    articles = json.load(f)
                if isinstance(articles, list) and articles:
                    dates = []
                    for article in articles:
                        published_at = article.get('publishedAt', '') or article.get('published_utc', '') or article.get('date', '')
                        if published_at:
                            try:
                                if 'T' in published_at or 'Z' in published_at or '+' in published_at or (published_at.count(' ') >= 2 and ':' in published_at):
                                    date_str = published_at.replace('Z', '+00:00') if published_at.endswith('Z') else published_at
                                    article_date = pd.to_datetime(date_str)
                                else:
                                    article_date = pd.to_datetime(published_at)
                                if article_date.tzinfo:
                                    article_date = article_date.tz_localize(None)
                                dates.append(article_date)
                            except Exception:
                                pass
                    if dates:
                        ticker_news_start = min(dates)
                        ticker_news_end = max(dates)
                        if news_data_start is None or ticker_news_start < news_data_start:
                            news_data_start = ticker_news_start
                        if news_data_end is None or ticker_news_end > news_data_end:
                            news_data_end = ticker_news_end
            except Exception:
                pass

if news_data_start and news_data_end:
    print(f"  [DEBUG] Final news data range: {news_data_start.date()} to {news_data_end.date()}", flush=True)
    
    # Find overlap between price and news data
    overlap_start = max(price_data_start, news_data_start)
    overlap_end = min(price_data_end, news_data_end)
    
    if overlap_start < overlap_end:
        actual_data_start = overlap_start
        actual_data_end = overlap_end
        print(f"  [OK] Using overlapping date range: {actual_data_start.date()} to {actual_data_end.date()}", flush=True)
    else:
        actual_data_start = price_data_start
        actual_data_end = price_data_end
        print(f"  [WARNING] No overlap between price ({price_data_start.date()} to {price_data_end.date()}) and news ({news_data_start.date()} to {news_data_end.date()})!", flush=True)
        print(f"  [WARNING] Using price data range only - news analysis will find no articles", flush=True)
else:
    actual_data_start = price_data_start
    actual_data_end = price_data_end
    print(f"  [WARNING] Could not detect news date range, using price data range only", flush=True)

# ============================================================================
# STEP 3: Pre-calculate ALL technical signals ONCE (for all dates)
# ============================================================================
print(f"\n[3/5] Pre-calculating technical signals...", flush=True)

# DEBUG: Check volume availability across all loaded data
tickers_with_volume = []
tickers_without_volume = []
for ticker, df in list(prices_dict.items())[:10]:  # Check first 10
    if 'volume' in df.columns:
        tickers_with_volume.append(ticker)
    else:
        tickers_without_volume.append(ticker)

print(f"  [DEBUG] Volume data check (first 10 tickers):", flush=True)
print(f"    Tickers WITH volume: {tickers_with_volume}", flush=True)
print(f"    Tickers WITHOUT volume: {tickers_without_volume}", flush=True)
if tickers_without_volume:
    print(f"    [WARNING] {len(tickers_without_volume)} tickers missing volume data - volume signal will be 1.0 (neutral)", flush=True)

tech_start = time.time()

# Get all Mondays - use the aligned date range (overlap of price and news)
if prices_dict:
    # Use the aligned date range (already calculated above)
    # Need 30 days history for technical indicators, but don't exceed the end date
    signal_start = actual_data_start + pd.Timedelta(days=30)
    signal_end = actual_data_end
    # Ensure signal_start doesn't exceed signal_end
    if signal_start >= signal_end:
        # If adding 30 days pushes us past the end, use the start date
        signal_start = actual_data_start
    
    # Override date range in DEBUG_MODE
    if DEBUG_MODE:
        if DEBUG_START_DATE and DEBUG_END_DATE:
            # Override with specified dates
            signal_start = pd.to_datetime(DEBUG_START_DATE) + pd.Timedelta(days=30)
            signal_end = pd.to_datetime(DEBUG_END_DATE)
            print(f"  [DEBUG] Overriding date range to: {signal_start.date()} to {signal_end.date()}", flush=True)
        else:
            # Use auto-detected aligned date range
            # Need 30 days history for technical indicators, but don't exceed the end date
            signal_start = actual_data_start + pd.Timedelta(days=30)
            signal_end = actual_data_end
            # Ensure signal_start doesn't exceed signal_end
            if signal_start >= signal_end:
                # If adding 30 days pushes us past the end, use the start date
                signal_start = actual_data_start
                print(f"  [WARNING] Date range too short for 30-day history, using start date: {signal_start.date()}", flush=True)
            print(f"  [DEBUG] Using auto-detected aligned date range: {signal_start.date()} to {signal_end.date()}", flush=True)
    
    # Final validation: ensure signal_start < signal_end
    if signal_start >= signal_end:
        # If range is invalid, use actual_data_start (no 30-day buffer)
        signal_start = actual_data_start
        print(f"  [WARNING] Adjusted signal_start to {signal_start.date()} (range was too short for 30-day history)", flush=True)
    
    mondays = pd.date_range(signal_start, signal_end, freq='W-MON')
    
    # Limit iterations in DEBUG_MODE
    if DEBUG_MODE and len(mondays) > MAX_WEEKLY_ITERATIONS:
        mondays = mondays[:MAX_WEEKLY_ITERATIONS]
        print(f"  [DEBUG] Limited to {len(mondays)} weeks (max {MAX_WEEKLY_ITERATIONS})", flush=True)
    print(f"  Generating signals for {len(mondays)} Mondays ({signal_start.date()} to {signal_end.date()})...", flush=True)
else:
    mondays = pd.date_range('2023-02-01', '2023-12-31', freq='W-MON')
    print(f"  Generating signals for {len(mondays)} Mondays...", flush=True)

# Pre-calculate technical signals for all tickers and all dates
tech_signals_cache = {}  # {ticker: {date_str: {momentum_score, volume_score, rsi_score}}}

for i, ticker in enumerate(prices_dict.keys(), 1):
    ticker_df = prices_dict[ticker]
    tech_signals_cache[ticker] = {}
    
    for monday in mondays:
        date_str = monday.strftime("%Y-%m-%d")
        date_dt = pd.to_datetime(date_str)
        df_filtered = ticker_df[ticker_df.index <= date_dt]
        
        if df_filtered.empty or len(df_filtered) < 5:
            tech_signals_cache[ticker][date_str] = {
                'momentum_score': 0.0,
                'volume_score': 1.0,
                'rsi_score': 0.5
            }
        else:
            # Calculate momentum
            close = df_filtered['close']
            momentum_period = tech_config.get('momentum_period', 20)
            if len(close) >= momentum_period:
                close_short = close.iloc[-5] if len(close) >= 5 else close.iloc[-1]
                close_long = close.iloc[-momentum_period]
                momentum = (close_short - close_long) / (close_long + 1e-8)
            else:
                momentum = 0.0
            
            # Calculate volume ratio
            if 'volume' in df_filtered.columns:
                volume = df_filtered['volume']
                volume_period = tech_config.get('volume_period', 30)
                if len(volume) >= volume_period:
                    volume_mean = volume.rolling(volume_period, min_periods=1).mean().iloc[-1]
                    volume_latest = volume.iloc[-1]
                    volume_ratio = volume_latest / volume_mean if volume_mean > 0 else 1.0
                    # DEBUG: Print volume calculation for first ticker, first date
                    if i == 1 and monday == mondays[0]:
                        print(f"  [DEBUG] {ticker} volume calculation ({date_str}):", flush=True)
                        print(f"    Latest volume: {volume_latest:.0f}", flush=True)
                        print(f"    Mean volume ({volume_period}d): {volume_mean:.0f}", flush=True)
                        print(f"    Volume ratio: {volume_ratio:.6f}", flush=True)
                else:
                    volume_ratio = 1.0
                    if i == 1 and monday == mondays[0]:
                        print(f"  [WARNING] {ticker}: Insufficient data for volume (need {volume_period}, have {len(volume)})", flush=True)
            else:
                volume_ratio = 1.0
                if i == 1 and monday == mondays[0]:
                    print(f"  [WARNING] {ticker}: No 'volume' column in data, using default 1.0", flush=True)
            
            # Calculate RSI
            if 'close' in df_filtered.columns:
                close = df_filtered['close']
                delta = close.diff()
                gain = (delta.where(delta > 0, 0)).rolling(tech_config.get('rsi_period', 14), min_periods=1).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(tech_config.get('rsi_period', 14), min_periods=1).mean()
                if len(gain) > 0 and len(loss) > 0:
                    rs = gain.iloc[-1] / (loss.iloc[-1] + 1e-8)
                    rsi = 100 - (100 / (1 + rs))
                    rsi_score = ((rsi - 30) / 40).clip(0, 1)
                else:
                    rsi_score = 0.5
            else:
                rsi_score = 0.5
            
            tech_signals_cache[ticker][date_str] = {
                'momentum_score': float(momentum),
                'volume_score': float(volume_ratio),
                'rsi_score': float(rsi_score)
            }
    
    if i % 10 == 0 or i == len(prices_dict):
        print(f"  Progress: {i}/{len(prices_dict)} tickers processed...", flush=True)

tech_time = time.time() - tech_start
print(f"  [OK] Pre-calculated technical signals in {tech_time:.1f}s", flush=True)

# ============================================================================
# STEP 4: Pre-calculate ALL news signals ONCE (for all dates)
# ============================================================================
print(f"\n[4/5] Pre-calculating news signals...", flush=True)
news_start = time.time()

news_signals_cache = {}  # {ticker: {date_str: {supply_chain_score, sentiment_score, confidence}}}

# Initialize news analyzer
news_analyzer = None
if news_config.get('enabled', True):
    try:
        news_analyzer = NewsAnalyzer(
            news_dir="data/news",
            lookback_days=news_config.get('lookback_days', 7),
            min_articles=news_config.get('min_articles', 1),
            enable_propagation=True  # Enable sentiment propagation by default
        )
    except Exception as e:
        print(f"  [WARNING] News analyzer failed: {e} (continuing without news)", flush=True)
        news_analyzer = None

if news_analyzer:
    iteration_count = 0
    for i, ticker in enumerate(prices_dict.keys(), 1):
        news_signals_cache[ticker] = {}
        
        for monday in mondays:
            iteration_count += 1
            timestamp = datetime.now().strftime("%H:%M:%S")
            date_str = monday.strftime("%Y-%m-%d")
            lookback_start = (monday - timedelta(days=news_config.get('lookback_days', 7))).strftime("%Y-%m-%d")
            
            if DEBUG_MODE and iteration_count > MAX_WEEKLY_ITERATIONS:
                print(f"[{timestamp}] [FAST-FAIL] Reached {MAX_WEEKLY_ITERATIONS} iterations - STOPPING", flush=True)
                break
            
            print(f"\n[{timestamp}] [ITERATION {iteration_count}] Processing {ticker} on {date_str}", flush=True)
            
            try:
                print(f"[{timestamp}] Calling news analysis for {ticker}...", flush=True)
                news_signals = news_analyzer.analyze_news_for_ticker(ticker, lookback_start, date_str)
                
                # Fast-fail on first None result in DEBUG_MODE
                if news_signals is None:
                    news_signals_cache[ticker][date_str] = None
                    print(f"[{timestamp}] [FAST-FAIL] News returned None for {ticker} on {date_str}", flush=True)
                    if DEBUG_MODE:
                        print("[FAST-FAIL] Stopping to investigate - check logs above", flush=True)
                        raise SystemExit("Debug mode: Stopping on first None result")
                else:
                    news_signals_cache[ticker][date_str] = news_signals
                    print(f"[{timestamp}] [SUCCESS] {ticker} got news score: supply_chain={news_signals.get('supply_chain_score', 'N/A'):.3f}, sentiment={news_signals.get('sentiment_score', 'N/A'):.3f}", flush=True)
            except SystemExit:
                raise  # Re-raise SystemExit
            except Exception as e:
                # On error, store None (no fallback)
                news_signals_cache[ticker][date_str] = None
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] [FAST-FAIL ERROR] {ticker} on {date_str}: {e}", flush=True)
                if DEBUG_MODE:
                    import traceback
                    traceback.print_exc()
                    raise SystemExit(f"Debug mode: Stopping on error: {e}")
        
        if DEBUG_MODE and iteration_count >= MAX_WEEKLY_ITERATIONS:
            break
            
        if i % 10 == 0 or i == len(prices_dict):
            print(f"  Progress: {i}/{len(prices_dict)} tickers processed...", flush=True)
else:
    # No news analyzer, fill with None (no news available)
    for ticker in prices_dict.keys():
        news_signals_cache[ticker] = {}
        for monday in mondays:
            date_str = monday.strftime("%Y-%m-%d")
            news_signals_cache[ticker][date_str] = None

news_time = time.time() - news_start
print(f"  [OK] Pre-calculated news signals in {news_time:.1f}s", flush=True)

# STEP 4.5: Train ML model (optional - if enabled in config)
# Must happen AFTER both technical and news signals are calculated
use_ml_model = False
trained_model = None
try:
    config_path = Path('config/model_config.yaml')
    if config_path.exists():
        with open(config_path) as f:
            ml_config = yaml.safe_load(f)
        
        # Check if ML is enabled
        use_ml_model = ml_config.get('use_ml', False)  # Default to False for backward compatibility
        
        if use_ml_model:
            print(f"\n[4.5/5] Training ML model ({ml_config['active_model']})...", flush=True)
            from src.models.train_pipeline import ModelTrainingPipeline
            
            pipeline = ModelTrainingPipeline('config/model_config.yaml')
            # Pass the cached signals (they use date_str keys)
            trained_model = pipeline.train(prices_dict, tech_signals_cache, news_signals_cache)
            print(f"  [OK] Model trained and ready", flush=True)
        else:
            print(f"\n[4.5/5] ML model disabled (use_ml: false) - using weighted signals", flush=True)
except Exception as e:
    print(f"  [WARNING] Could not load ML config: {e}", flush=True)
    print(f"  [INFO] Falling back to weighted signal combination", flush=True)
    use_ml_model = False

total_prep_time = time.time() - start_time
print(f"\n[OK] Data preparation complete in {total_prep_time:.1f}s", flush=True)
print(f"  Breakdown: Loading={data_load_time:.1f}s, Technical={tech_time:.1f}s, News={news_time:.1f}s", flush=True)

# ============================================================================
# STEP 5: Run 3 backtests using pre-loaded data
# ============================================================================
print("\n" + "=" * 60)
print("Running 3 backtests with pre-loaded data...")
print("=" * 60)

def run_backtest_with_preloaded_data(prices_dict, tech_signals_cache, news_signals_cache,
                                     mondays, weights, tech_config, news_config,
                                     mode='combined', top_n=10, news_analyzer=None, weighting_method='proportional'):
    """
    Run backtest using pre-loaded data
    
    Args:
        mode: 'technical_only', 'news_only', or 'combined'
    """
    # Adjust weights based on mode
    if mode == 'technical_only':
        combiner_weights = {'supply_chain': 0.0, 'sentiment': 0.0, 'momentum': 0.5, 'volume': 0.3, 'rsi': 0.2}
        news_enabled = False
    elif mode == 'news_only':
        combiner_weights = {'supply_chain': 0.5, 'sentiment': 0.5, 'momentum': 0.0, 'volume': 0.0, 'rsi': 0.0}
        news_enabled = True
    else:  # combined
        combiner_weights = weights.copy()
        # Normalize
        total = sum(combiner_weights.values())
        if total > 0:
            combiner_weights = {k: v / total for k, v in combiner_weights.items()}
        news_enabled = news_config.get('enabled', True)
    
    signal_combiner = SignalCombiner()
    signals_df = pd.DataFrame(0.0, index=mondays, columns=list(prices_dict.keys()))
    
    print(f"  [DEBUG] Initial signals_df shape: {signals_df.shape}", flush=True)
    print(f"  [DEBUG] Tickers in prices_dict: {list(prices_dict.keys())[:5]}...", flush=True)
    
    total_scores_calculated = 0
    for idx, monday in enumerate(mondays, 1):
        date_str = monday.strftime("%Y-%m-%d")
        scores = {}
        
        for ticker in prices_dict.keys():
            try:
                # Get pre-calculated technical signals
                tech_signals = tech_signals_cache.get(ticker, {}).get(date_str, {
                    'momentum_score': 0.0,
                    'volume_score': 1.0,
                    'rsi_score': 0.5
                })
                
                # Get pre-calculated news signals
                if news_enabled and news_analyzer:
                    news_signals = news_signals_cache.get(ticker, {}).get(date_str, {
                        'supply_chain_score': 0.0,
                        'sentiment_score': 0.0,
                        'confidence': 0.0
                    })
                else:
                    news_signals = {'supply_chain_score': 0.0, 'sentiment_score': 0.0, 'confidence': 0.0}
                
                # Prepare signals for combiner
                tech_for_combiner = {
                    'momentum_score': tech_signals.get('momentum_score', 0.0),
                    'volume_score': tech_signals.get('volume_score', 1.0),
                    'rsi_score': tech_signals.get('rsi_score', 0.5)
                }
                
                # Handle RSI combination for technical-only mode
                if mode == 'technical_only':
                    momentum = tech_for_combiner['momentum_score']
                    rsi = tech_for_combiner['rsi_score']
                    momentum_weight = combiner_weights.get('momentum', 0.5)
                    rsi_weight = combiner_weights.get('rsi', 0.2)
                    volume_weight = combiner_weights.get('volume', 0.3)
                    total_tech = momentum_weight + rsi_weight + volume_weight
                    
                    if total_tech > 0:
                        momentum_weight_norm = momentum_weight / total_tech
                        rsi_weight_norm = rsi_weight / total_tech
                        volume_weight_norm = volume_weight / total_tech
                        combined_momentum = (momentum * momentum_weight_norm + rsi * rsi_weight_norm) / (momentum_weight_norm + rsi_weight_norm) if (momentum_weight_norm + rsi_weight_norm) > 0 else momentum
                        tech_for_combiner['momentum_score'] = combined_momentum
                        combiner_weights = {
                            'supply_chain': 0.0,
                            'sentiment': 0.0,
                            'momentum': momentum_weight_norm + rsi_weight_norm,
                            'volume': volume_weight_norm
                        }
                
                # Generate prediction/score
                if use_ml_model and trained_model is not None:
                    # Use ML model to predict return
                    try:
                        # Extract features in same order as training
                        features = np.array([[
                            tech_for_combiner['momentum_score'],
                            tech_for_combiner['volume_score'],
                            tech_for_combiner['rsi_score'],
                            news_signals.get('supply_chain_score', 0.0),
                            news_signals.get('sentiment_score', 0.0)
                        ]])
                        
                        # Predict forward return
                        predicted_return = trained_model.predict(features)[0]
                        
                        # Use predicted return as score (higher = better)
                        scores[ticker] = predicted_return
                    except Exception as e:
                        if idx == 1 and len(scores) < 3:
                            print(f"    [WARNING] ML prediction failed for {ticker}: {e}", flush=True)
                        # Fallback to weighted signals
                        if mode == 'news_only':
                            news_total = abs(news_signals.get('supply_chain_score', 0.0)) + abs(news_signals.get('sentiment_score', 0.0))
                            if news_total < 0.001:
                                continue
                            else:
                                scores[ticker] = signal_combiner.combine_signals_direct(
                                    tech_for_combiner, news_signals, combiner_weights
                                )
                        else:
                            scores[ticker] = signal_combiner.combine_signals_direct(
                                tech_for_combiner, news_signals, combiner_weights
                            )
                else:
                    # Use weighted signal combination (original method)
                    # Handle news-only mode: if no news data (all zeros), skip this ticker (don't use fallback)
                    if mode == 'news_only':
                        news_total = abs(news_signals.get('supply_chain_score', 0.0)) + abs(news_signals.get('sentiment_score', 0.0))
                        if news_total < 0.001:  # All news signals are essentially 0 (no news found)
                            # Skip this ticker - no news data available (no fallback to technical)
                            continue
                        else:
                            combined_score = signal_combiner.combine_signals_direct(
                                tech_for_combiner, news_signals, combiner_weights
                            )
                    else:
                        combined_score = signal_combiner.combine_signals_direct(
                            tech_for_combiner, news_signals, combiner_weights
                        )
                    
                    scores[ticker] = combined_score
                total_scores_calculated += 1
            except Exception as e:
                if idx == 1 and len(scores) < 3:  # Only print for first week, first few errors
                    print(f"    [WARNING] Error calculating score for {ticker}: {e}", flush=True)
                continue
        
        if scores:
            print(f"  [DEBUG] Week {idx} ({date_str}): {len(scores)} tickers with scores", flush=True)
            # Ensure we select at least min(len(scores), top_n) stocks
            actual_top_n = min(len(scores), top_n)
            top_tickers = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:actual_top_n]
            print(f"  [DEBUG] Week {idx}: Selected top {len(top_tickers)} tickers (top_n={top_n}, available={len(scores)}, actual_top_n={actual_top_n})", flush=True)
            if len(top_tickers) == 0:
                print(f"  [ERROR] Week {idx}: No tickers selected despite {len(scores)} scores available!", flush=True)
            
            # Calculate weights based on weighting_method
            if top_tickers:
                if weighting_method == 'proportional':
                    # Proportional weighting: weight = score / sum(all scores)
                    # Higher score = larger position weight
                    ticker_scores = {t: s for t, s in top_tickers}
                    total_score = sum(ticker_scores.values())
                    
                    if total_score > 0:
                        weights_dict = {t: s / total_score for t, s in ticker_scores.items()}
                    else:
                        # Fallback to equal weights if all scores are 0
                        equal_weight = 1.0 / len(top_tickers)
                        weights_dict = {t: equal_weight for t, _ in top_tickers}
                else:
                    # Equal weighting: 1/N for all selected stocks
                    equal_weight = 1.0 / len(top_tickers)
                    weights_dict = {t: equal_weight for t, _ in top_tickers}
            else:
                weights_dict = {}
            
            if idx == 1:  # Debug first week
                print(f"  [DEBUG] Week 1 ({date_str}): Top {len(top_tickers)} tickers selected (weighting: {weighting_method}):", flush=True)
                for rank, (t, s) in enumerate(top_tickers[:5], 1):
                    weight = weights_dict.get(t, 0.0)
                    print(f"    {rank}. {t}: score={s:.6f}, weight={weight:.4f}", flush=True)
            
            # Assign weights
            print(f"  [DEBUG] Week {idx}: Assigning weights to {len(weights_dict)} tickers", flush=True)
            for ticker, weight in weights_dict.items():
                signals_df.loc[monday, ticker] = weight
                if idx == 1:  # Debug first week
                    print(f"    {ticker}: weight={weight:.6f}", flush=True)
        else:
            print(f"  [WARNING] Week {idx} ({date_str}): No scores calculated! (scores dict is empty)", flush=True)
            print(f"  [DEBUG] Week {idx}: Available tickers in prices_dict: {list(prices_dict.keys())}", flush=True)
    
    print(f"  [DEBUG] Total scores calculated: {total_scores_calculated}", flush=True)
    print(f"  [DEBUG] Expected scores: {len(mondays) * len(prices_dict)}", flush=True)
    
    # DEBUG: Check signals before backtest
    print(f"  [DEBUG] Signals DataFrame shape: {signals_df.shape}", flush=True)
    print(f"  [DEBUG] Total signals generated: {(signals_df > 0).sum().sum()}", flush=True)
    print(f"  [DEBUG] Non-zero signals per week: {(signals_df > 0).sum(axis=1).head(5).tolist()}", flush=True)
    if not signals_df.empty:
        print(f"  [DEBUG] Sample signals (first 5 weeks, first 5 tickers):", flush=True)
        print(f"    {signals_df.iloc[:5, :5].to_string()}", flush=True)
    
    # Run backtest
    all_dates = sorted(set().union(*[df.index for df in prices_dict.values()]))
    prices_df = pd.DataFrame({t: prices_dict[t]['close'] for t in prices_dict.keys()}, index=all_dates)
    positions_df = pd.DataFrame(0.0, index=prices_df.index, columns=prices_df.columns)
    
    # CRITICAL: Validate date overlap
    signal_start = signals_df.index.min() if not signals_df.empty else None
    signal_end = signals_df.index.max() if not signals_df.empty else None
    price_start = prices_df.index.min()
    price_end = prices_df.index.max()
    
    if signal_start and signal_end:
        overlap_start = max(signal_start, price_start)
        overlap_end = min(signal_end, price_end)
        
        print(f"  [DEBUG] Signals date range: {signal_start.date()} to {signal_end.date()}", flush=True)
        print(f"  [DEBUG] Prices date range: {price_start.date()} to {price_end.date()}", flush=True)
        print(f"  [DEBUG] Overlap period: {overlap_start.date()} to {overlap_end.date()}", flush=True)
        
        if overlap_start >= overlap_end:
            print(f"  [ERROR] No date overlap! Signals: {signal_start.date()} to {signal_end.date()}, Prices: {price_start.date()} to {price_end.date()}", flush=True)
            print(f"  [ERROR] Cannot execute backtest without date overlap!", flush=True)
            return {
                'sharpe': 0.0,
                'total_return': 0.0,
                'max_drawdown': 0.0,
                'signals_df': signals_df,
                'error': 'No date overlap between signals and prices'
            }
        
        # Filter signals and prices to overlap period only
        signals_df_filtered = signals_df[(signals_df.index >= overlap_start) & (signals_df.index <= overlap_end)]
        prices_df_filtered = prices_df[(prices_df.index >= overlap_start) & (prices_df.index <= overlap_end)]
        
        print(f"  [DEBUG] Using overlap period: {overlap_start.date()} to {overlap_end.date()}", flush=True)
        print(f"  [DEBUG] Filtered signals: {len(signals_df_filtered)} weeks", flush=True)
        print(f"  [DEBUG] Filtered prices: {len(prices_df_filtered)} days", flush=True)
        
        # Update mondays to only include overlap period
        mondays_filtered = mondays[(mondays >= overlap_start) & (mondays <= overlap_end)]
        signals_df = signals_df_filtered
        prices_df = prices_df_filtered
        positions_df = pd.DataFrame(0.0, index=prices_df.index, columns=prices_df.columns)
        mondays = mondays_filtered
    else:
        print(f"  [WARNING] No signals generated, using all price data", flush=True)
    
    print(f"  [DEBUG] Prices DataFrame shape: {prices_df.shape}", flush=True)
    print(f"  [DEBUG] Positions DataFrame shape: {positions_df.shape}", flush=True)
    print(f"  [DEBUG] Date range: {prices_df.index.min()} to {prices_df.index.max()}", flush=True)
    print(f"  [DEBUG] Mondays to process: {len(mondays)}", flush=True)
    
    positions_filled = 0
    print(f"  [DEBUG] Portfolio construction: Processing {len(mondays)} Mondays", flush=True)
    print(f"  [DEBUG] Available tickers in signals_df: {list(signals_df.columns)}", flush=True)
    print(f"  [DEBUG] Available tickers in positions_df: {list(positions_df.columns)}", flush=True)
    
    for monday in mondays:
        if monday not in signals_df.index:
            print(f"  [DEBUG] Monday {monday.date()} not in signals_df.index, skipping", flush=True)
            continue
        next_days = prices_df.index[prices_df.index >= monday]
        if len(next_days) == 0:
            print(f"  [DEBUG] No price data after {monday.date()}, skipping", flush=True)
            continue
        start_idx = prices_df.index.get_loc(next_days[0])
        next_monday = mondays[mondays > monday]
        end_idx = len(prices_df) if len(next_monday) == 0 else prices_df.index.get_loc(prices_df.index[prices_df.index < next_monday[0]][-1]) + 1
        
        monday_signals = signals_df.loc[monday]
        non_zero_signals = monday_signals[monday_signals > 0]
        print(f"  [DEBUG] Monday {monday.date()}: {len(non_zero_signals)} tickers with non-zero signals", flush=True)
        
        for ticker in positions_df.columns:
            if ticker in signals_df.columns:
                signal_value = signals_df.loc[monday, ticker]
                if signal_value > 0:
                    positions_df.iloc[start_idx:end_idx, positions_df.columns.get_loc(ticker)] = signal_value
                    positions_filled += 1
                    if monday == mondays[0]:  # Debug first Monday
                        print(f"    [DEBUG] Set position for {ticker}: weight={signal_value:.6f}, dates={prices_df.index[start_idx].date()} to {prices_df.index[end_idx-1].date()}", flush=True)
    
    print(f"  [DEBUG] Positions filled: {positions_filled} entries", flush=True)
    print(f"  [DEBUG] Non-zero positions: {(positions_df > 0).sum().sum()}", flush=True)
    if positions_filled > 0:
        print(f"  [DEBUG] Sample positions (first 5 dates, first 5 tickers):", flush=True)
        print(f"    {positions_df.iloc[:5, :5].to_string()}", flush=True)
    
    # Calculate metrics
    returns = prices_df.pct_change()
    print(f"  [DEBUG] Returns DataFrame shape: {returns.shape}", flush=True)
    print(f"  [DEBUG] Returns stats:", flush=True)
    print(f"    Mean: {returns.mean().mean():.6f}", flush=True)
    print(f"    Std: {returns.std().mean():.6f}", flush=True)
    print(f"    Non-zero returns: {(returns != 0).sum().sum()}/{returns.size}", flush=True)
    print(f"    NaN returns: {returns.isna().sum().sum()}", flush=True)
    if not returns.empty:
        print(f"    Sample returns (first 5 rows, first 3 cols):", flush=True)
        print(f"      {returns.iloc[:5, :3].to_string()}", flush=True)
    
    portfolio_returns = (positions_df.shift(1) * returns).sum(axis=1).fillna(0)
    print(f"  [DEBUG] Portfolio returns stats:", flush=True)
    print(f"    Length: {len(portfolio_returns)}", flush=True)
    print(f"    Mean: {portfolio_returns.mean():.6f}", flush=True)
    print(f"    Std: {portfolio_returns.std():.6f}", flush=True)
    print(f"    Non-zero: {(portfolio_returns != 0).sum()}/{len(portfolio_returns)}", flush=True)
    print(f"    Sample portfolio returns (first 10): {portfolio_returns.head(10).tolist()}", flush=True)
    
    rebalance_dates = positions_df.diff().abs().sum(axis=1) > 0.01
    print(f"  [DEBUG] Rebalance dates: {rebalance_dates.sum()} days", flush=True)
    portfolio_returns[rebalance_dates] -= 0.001
    
    cumulative = (1 + portfolio_returns).cumprod()
    total_return = cumulative.iloc[-1] - 1
    sharpe = (portfolio_returns.mean() * 252) / (portfolio_returns.std() * np.sqrt(252)) if portfolio_returns.std() > 0 else 0.0
    max_dd = ((cumulative - cumulative.expanding().max()) / cumulative.expanding().max()).min()
    
    print(f"  [DEBUG] Final metrics:", flush=True)
    print(f"    Total return: {total_return:.6f}", flush=True)
    print(f"    Sharpe: {sharpe:.6f}", flush=True)
    print(f"    Max drawdown: {max_dd:.6f}", flush=True)
    
    return {
        'sharpe': sharpe,
        'total_return': total_return,
        'max_drawdown': max_dd,
        'signals_df': signals_df
    }

# Run 3 backtests
results = {}

# 1. Technical-only
print("\n[1/3] Running technical-only backtest...", flush=True)
bt_start = time.time()
results['technical_only'] = run_backtest_with_preloaded_data(
    prices_dict, tech_signals_cache, news_signals_cache,
    mondays, weights, tech_config, news_config,
    mode='technical_only', top_n=args.top_n, news_analyzer=news_analyzer, weighting_method=weighting_method
)
bt_time = time.time() - bt_start
print(f"  [OK] Technical-only Sharpe: {results['technical_only']['sharpe']:.2f} (took {bt_time:.1f}s)", flush=True)

# 2. News-only
print("\n[2/3] Running news-only backtest...", flush=True)
bt_start = time.time()
results['news_only'] = run_backtest_with_preloaded_data(
    prices_dict, tech_signals_cache, news_signals_cache,
    mondays, weights, tech_config, news_config,
    mode='news_only', top_n=args.top_n, news_analyzer=news_analyzer, weighting_method=weighting_method
)
bt_time = time.time() - bt_start
print(f"  [OK] News-only Sharpe: {results['news_only']['sharpe']:.2f} (took {bt_time:.1f}s)", flush=True)

# 3. Combined
print("\n[3/3] Running combined backtest...", flush=True)
bt_start = time.time()
results['combined'] = run_backtest_with_preloaded_data(
    prices_dict, tech_signals_cache, news_signals_cache,
    mondays, weights, tech_config, news_config,
    mode='combined', top_n=args.top_n, news_analyzer=news_analyzer, weighting_method=weighting_method
)
bt_time = time.time() - bt_start
print(f"  [OK] Combined Sharpe: {results['combined']['sharpe']:.2f} (took {bt_time:.1f}s)", flush=True)

# Summary
total_time = time.time() - start_time
print("\n" + "=" * 60)
print("RESULTS SUMMARY (6+ month expanded backtest)")
print("=" * 60)
print(f"  Period: {len(mondays)} weekly rebalances ({mondays[0].date() if len(mondays) else 'N/A'} to {mondays[-1].date() if len(mondays) else 'N/A'})")
for approach, result in results.items():
    print(f"{approach:20s}: Sharpe={result['sharpe']:6.2f}, Return={result['total_return']:7.2%}, Drawdown={result['max_drawdown']:7.2%}")

print(f"\nTotal runtime: {total_time:.1f}s")
print(f"  Data loading: {data_load_time:.1f}s")
print(f"  Signal calculation: {tech_time + news_time:.1f}s")
print(f"  Backtests: {total_time - total_prep_time:.1f}s")

if all('sharpe' in r for r in results.values()):
    best = max(results.items(), key=lambda x: x[1]['sharpe'] if x[1]['sharpe'] is not None else -999)
    print(f"\n[BEST] Best approach: {best[0]} (Sharpe: {best[1]['sharpe']:.2f})")
    tech_sharpe = results.get('technical_only', {}).get('sharpe')
    news_sharpe = results.get('news_only', {}).get('sharpe')
    if tech_sharpe is not None and news_sharpe is not None:
        if news_sharpe < tech_sharpe:
            print(f"  News vs technical: news underperforms (Sharpe {news_sharpe:.2f} < technical {tech_sharpe:.2f})")
        else:
            print(f"  News vs technical: news matches or beats technical (Sharpe {news_sharpe:.2f} vs {tech_sharpe:.2f})")
    print("\nRecommendations:")
    if best[0] == 'technical_only':
        print("  -> Use technical-only signals (news adds noise)")
        print("  -> Set news weights to 0 in config/signal_weights.yaml")
    elif best[0] == 'news_only':
        print("  -> Use news-only signals (technical adds noise)")
        print("  -> Set technical weights to 0 in config/signal_weights.yaml")
    else:
        print("  -> Use combined signals (both add value)")
        print("  -> Tune weights in config/signal_weights.yaml for optimization")

print("=" * 60)

# Restore original stdout before closing log file
sys.stdout = original_stdout
log_file.close()
print(f"\nFull log saved to: {log_filename}")
