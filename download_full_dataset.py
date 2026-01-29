"""
Download Full Dataset
Downloads price data for 100-200 small-cap stocks ($500M-$5B market cap)
One-time download that takes 30-60 minutes
"""
import sys
import os
import yaml
from pathlib import Path
from datetime import datetime
import time

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logger
from src.data.price_fetcher import PriceFetcher
from src.utils.ticker_utils import get_extended_small_cap_list, get_russell2000_tickers

logger = setup_logger()


def load_config():
    """Load configuration"""
    config_path = project_root / "config" / "config.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def get_large_ticker_list(config) -> list:
    """
    Get a large list of tickers (100-200) for downloading
    
    Priority:
    1. Russell 2000 CSV file (if exists)
    2. Extended small-cap list (curated)
    3. Fallback to smaller list
    """
    logger.info("Getting ticker list...")
    
    # Try Russell 2000 file first
    russell_file = project_root / "data" / "russell2000_tickers.csv"
    if russell_file.exists():
        logger.info(f"Found Russell 2000 file: {russell_file}")
        tickers = get_russell2000_tickers(use_file=True, file_path=str(russell_file))
        if len(tickers) >= 100:
            logger.info(f"Using Russell 2000 list: {len(tickers)} tickers")
            return tickers
    
    # Use extended small-cap list
    tickers = get_extended_small_cap_list()
    logger.info(f"Using extended small-cap list: {len(tickers)} tickers")
    
    # Remove duplicates
    tickers = list(set(tickers))
    logger.info(f"After deduplication: {len(tickers)} unique tickers")
    
    return tickers


def download_full_dataset(config):
    """Download price data for large ticker set"""
    logger.info("=" * 60)
    logger.info("FULL DATASET DOWNLOAD")
    logger.info("=" * 60)
    logger.info("This will download price data for 100-200 small-cap stocks")
    logger.info("Estimated time: 30-60 minutes")
    logger.info("=" * 60)
    
    # Get ticker list
    all_tickers = get_large_ticker_list(config)
    
    if len(all_tickers) < 50:
        logger.warning(f"Only {len(all_tickers)} tickers found. Consider adding more tickers to the list.")
        response = input(f"Continue with {len(all_tickers)} tickers? (y/n): ")
        if response.lower() != 'y':
            logger.info("Download cancelled")
            return
    
    logger.info(f"\nStarting download for {len(all_tickers)} tickers...")
    
    # Initialize price fetcher
    price_fetcher = PriceFetcher(
        data_dir="data/prices",
        min_market_cap=config['market_cap']['min'],
        max_market_cap=config['market_cap']['max']
    )
    
    # Step 1: Filter by market cap
    logger.info("\n[Step 1/2] Filtering tickers by market cap ($500M-$5B)...")
    logger.info("This may take 10-20 minutes...")
    
    filtered_tickers = price_fetcher.filter_by_market_cap(all_tickers)
    
    logger.info(f"\n✅ Filtered to {len(filtered_tickers)} tickers in market cap range")
    logger.info(f"Tickers: {', '.join(filtered_tickers[:20])}{'...' if len(filtered_tickers) > 20 else ''}")
    
    if len(filtered_tickers) < 10:
        logger.error(f"Only {len(filtered_tickers)} tickers passed market cap filter. Check your market cap range.")
        return
    
    # Step 2: Check existing downloads and resume
    logger.info(f"\n[Step 2/2] Checking existing downloads and resuming...")
    
    # Ensure data/prices directory exists
    prices_dir = project_root / "data" / "prices"
    if not prices_dir.exists():
        logger.info(f"Creating data/prices directory...")
        prices_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {prices_dir}")
    
    # Check for existing parquet files
    try:
        existing_tickers = price_fetcher.get_existing_tickers(
            start_date=config['data']['date_range']['start'],
            end_date=config['data']['date_range']['end']
        )
    except Exception as e:
        logger.error(f"Error checking existing downloads: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        logger.warning("Continuing with full download...")
        existing_tickers = set()
    
    if existing_tickers:
        logger.info(f"Found {len(existing_tickers)} tickers already downloaded")
        logger.info(f"  Examples: {', '.join(sorted(list(existing_tickers))[:10])}{'...' if len(existing_tickers) > 10 else ''}")
    else:
        logger.info("No existing tickers found - will download all tickers")
    
    remaining_tickers = [t for t in filtered_tickers if t not in existing_tickers]
    logger.info(f"Tickers to process: {len(filtered_tickers)} total, {len(existing_tickers)} already downloaded, {len(remaining_tickers)} remaining")
    
    if len(remaining_tickers) == 0:
        logger.info("✅ All tickers already downloaded! Nothing to do.")
        # Load all existing data
        results = {}
        for ticker in filtered_tickers:
            cache_path = project_root / "data" / "prices" / f"{ticker}.parquet"
            if cache_path.exists():
                try:
                    import pandas as pd
                    df = pd.read_parquet(cache_path)
                    if not df.empty:
                        results[ticker] = df
                except Exception as e:
                    logger.warning(f"Error loading {ticker}: {e}")
        elapsed_time = 0
    else:
        logger.info(f"Downloading {len(remaining_tickers)} remaining tickers...")
        logger.info(f"Date range: {config['data']['date_range']['start']} to {config['data']['date_range']['end']}")
        logger.info("This may take 20-40 minutes...")
        logger.info("Progress will be shown as: [X/Total] Fetched ticker...")
        logger.info("Progress saved every 10 tickers (resumable if interrupted)")
        logger.info("Rate limiting: 1 second between tickers (to avoid Yahoo blocking)")
        
        start_time = time.time()
        results = price_fetcher.fetch_all_tickers(
            filtered_tickers,  # Pass all tickers, method will filter internally
            start_date=config['data']['date_range']['start'],
            end_date=config['data']['date_range']['end'],
            use_cache=True,  # Skip already downloaded tickers
            save_progress_every=10  # Save progress every 10 tickers
        )
        elapsed_time = time.time() - start_time
    
    # Summary
    successful = len([t for t, df in results.items() if df is not None and not df.empty])
    failed_tickers = [t for t in filtered_tickers if t not in results or results.get(t) is None or results.get(t).empty]
    failed = len(failed_tickers)
    
    logger.info("\n" + "=" * 60)
    logger.info("DOWNLOAD COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total tickers: {len(filtered_tickers)}")
    logger.info(f"✅ Successful: {successful}")
    logger.info(f"❌ Failed: {failed}")
    if 'elapsed_time' in locals() and elapsed_time > 0:
        logger.info(f"⏱️  Time elapsed: {elapsed_time/60:.1f} minutes")
    logger.info(f"\nData saved to: data/prices/")
    
    # Save summary
    summary_path = project_root / "data" / "prices" / "download_summary.txt"
    with open(summary_path, 'w') as f:
        f.write("Full Dataset Download Summary\n")
        f.write("=" * 60 + "\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Date Range: {config['data']['date_range']['start']} to {config['data']['date_range']['end']}\n")
        f.write(f"Market Cap Filter: ${config['market_cap']['min']:,} - ${config['market_cap']['max']:,}\n")
        f.write(f"Total Tickers Attempted: {len(filtered_tickers)}\n")
        f.write(f"Successful Downloads: {successful}\n")
        f.write(f"Failed Downloads: {failed}\n")
        f.write(f"Time Elapsed: {elapsed_time/60:.1f} minutes\n\n")
        f.write("Successful Tickers:\n")
        for ticker in sorted([t for t, df in results.items() if df is not None and not df.empty]):
            f.write(f"  {ticker}: {len(results[ticker])} rows\n")
        f.write(f"\nFailed Tickers ({len(failed_tickers)}):\n")
        for ticker in sorted(failed_tickers):
            f.write(f"  {ticker}\n")
    
    logger.info(f"Summary saved to: {summary_path}")
    
    if successful >= 50:
        logger.info(f"\n✅ Successfully downloaded data for {successful} tickers!")
        logger.info("You can now run the technical backtest:")
        logger.info("  python run_technical_backtest.py")
    else:
        logger.warning(f"\n⚠️  Only {successful} tickers downloaded. Consider:")
        logger.warning("  1. Adding more tickers to the list")
        logger.warning("  2. Checking market cap filter range")
        logger.warning("  3. Verifying ticker symbols are correct")


if __name__ == "__main__":
    config = load_config()
    
    print("\n" + "=" * 60)
    print("FULL DATASET DOWNLOAD")
    print("=" * 60)
    print("This script will:")
    print("  1. Get 100-200 small-cap tickers")
    print("  2. Filter by market cap ($500M-$5B)")
    print("  3. Download 2 years of price data (2023-2024)")
    print("  4. Save to data/prices/")
    print("\nEstimated time: 30-60 minutes")
    print("=" * 60)
    
    response = input("\nContinue? (y/n): ")
    if response.lower() != 'y':
        print("Download cancelled")
        sys.exit(0)
    
    try:
        download_full_dataset(config)
    except KeyboardInterrupt:
        logger.info("\n\nDownload interrupted by user")
    except Exception as e:
        logger.error(f"\nError during download: {e}")
        import traceback
        logger.debug(traceback.format_exc())
