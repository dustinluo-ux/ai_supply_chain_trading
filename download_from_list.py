"""
Download Price Data from Pre-Identified Ticker List
Skips market cap filtering - downloads directly for known tickers
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

logger = setup_logger()


def load_config():
    """Load configuration"""
    config_path = project_root / "config" / "config.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def get_pre_identified_tickers() -> list:
    """
    Get the list of 65 tickers from previous successful market cap filter
    These are the tickers that passed the $500M-$5B market cap filter
    """
    return [
        'QLYS', 'SLAB', 'SYNA', 'CTMX', 'ALRM', 'AB', 'CVAC', 'ACAD', 'TENB', 'ALG',
        'ASO', 'AIV', 'AMBA', 'COMM', 'BLMN', 'ACHC', 'AWR', 'VSH', 'CRMD', 'AEO',
        'ACMR', 'AEIS', 'ALKS', 'ALLO', 'ALNY', 'ALXO', 'ARWR', 'ASND', 'ATRA', 'AUPH',
        'AVEO', 'BLUE', 'BMRN', 'BPMC', 'BTAI', 'CABA', 'CARA', 'CBLI', 'CCXI', 'CDMO',
        'CDNA', 'CERS', 'CGEN', 'CHRS', 'CLLS', 'CLVS', 'CRIS', 'CRNX', 'CUR', 'CYRX',
        'DAWN', 'DBVT', 'DCPH', 'DIOD', 'FLEX', 'JBL', 'SANM', 'TTMI', 'AOS', 'ATI',
        'AXE', 'ON', 'SWKS', 'QRVO', 'MRVL'
    ]


def download_from_list(config):
    """Download price data for pre-identified ticker list"""
    logger.info("=" * 60)
    logger.info("DOWNLOAD FROM PRE-IDENTIFIED TICKER LIST")
    logger.info("=" * 60)
    logger.info("Skipping market cap filtering - using known ticker list")
    logger.info("=" * 60)
    
    # Get ticker list
    tickers = get_pre_identified_tickers()
    logger.info(f"\nLoaded {len(tickers)} pre-identified tickers")
    logger.info(f"Tickers: {', '.join(tickers[:20])}{'...' if len(tickers) > 20 else ''}")
    
    # Initialize price fetcher (market cap params don't matter since we're skipping filter)
    price_fetcher = PriceFetcher(
        data_dir="data/prices",
        min_market_cap=500_000_000,  # Not used, but required for init
        max_market_cap=5_000_000_000  # Not used, but required for init
    )
    
    # Check for existing downloads
    logger.info(f"\n[Step 1/2] Checking existing downloads...")
    
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
    
    remaining_tickers = [t for t in tickers if t not in existing_tickers]
    logger.info(f"Tickers to process: {len(tickers)} total, {len(existing_tickers)} already downloaded, {len(remaining_tickers)} remaining")
    
    if len(remaining_tickers) == 0:
        logger.info("✅ All tickers already downloaded! Nothing to do.")
        # Load all existing data
        results = {}
        for ticker in tickers:
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
        # Download price data
        logger.info(f"\n[Step 2/2] Downloading price data for {len(remaining_tickers)} tickers...")
        logger.info(f"Date range: {config['data']['date_range']['start']} to {config['data']['date_range']['end']}")
        logger.info("Rate limiting: 1 second between tickers (to avoid Yahoo blocking)")
        logger.info("Progress saved every 10 tickers (resumable if interrupted)")
        
        start_time = time.time()
        results = price_fetcher.fetch_all_tickers(
            tickers,  # Pass all tickers, method will filter internally
            start_date=config['data']['date_range']['start'],
            end_date=config['data']['date_range']['end'],
            use_cache=True,  # Skip already downloaded tickers
            save_progress_every=10  # Save progress every 10 tickers
        )
        elapsed_time = time.time() - start_time
    
    # Summary
    successful = len([t for t, df in results.items() if df is not None and not df.empty])
    failed_tickers = [t for t in tickers if t not in results or results.get(t) is None or results.get(t).empty]
    failed = len(failed_tickers)
    
    logger.info("\n" + "=" * 60)
    logger.info("DOWNLOAD COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total tickers: {len(tickers)}")
    logger.info(f"✅ Successful: {successful}")
    logger.info(f"❌ Failed: {failed}")
    if 'elapsed_time' in locals() and elapsed_time > 0:
        logger.info(f"⏱️  Time elapsed: {elapsed_time/60:.1f} minutes")
    logger.info(f"\nData saved to: data/prices/")
    
    # Save summary
    summary_path = project_root / "data" / "prices" / "download_from_list_summary.txt"
    with open(summary_path, 'w') as f:
        f.write("Download From List Summary\n")
        f.write("=" * 60 + "\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Date Range: {config['data']['date_range']['start']} to {config['data']['date_range']['end']}\n")
        f.write(f"Total Tickers: {len(tickers)}\n")
        f.write(f"Successful Downloads: {successful}\n")
        f.write(f"Failed Downloads: {failed}\n")
        if 'elapsed_time' in locals() and elapsed_time > 0:
            f.write(f"Time Elapsed: {elapsed_time/60:.1f} minutes\n")
        f.write("\n")
        f.write("Successful Tickers:\n")
        successful_list = sorted([t for t, df in results.items() if df is not None and not df.empty])
        for ticker in successful_list:
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
        logger.warning("  1. Checking ticker symbols are correct")
        logger.warning("  2. Verifying internet connection")
        logger.warning("  3. Checking Yahoo Finance availability")


if __name__ == "__main__":
    config = load_config()
    
    print("\n" + "=" * 60)
    print("DOWNLOAD FROM PRE-IDENTIFIED TICKER LIST")
    print("=" * 60)
    print("This script will:")
    print("  1. Use 65 pre-identified tickers (from previous market cap filter)")
    print("  2. Skip market cap filtering")
    print("  3. Download 2 years of price data (2023-2024)")
    print("  4. Save to data/prices/")
    print("\nEstimated time: 10-20 minutes (65 tickers × ~10 seconds each)")
    print("=" * 60)
    
    response = input("\nContinue? (y/n): ")
    if response.lower() != 'y':
        print("Download cancelled")
        sys.exit(0)
    
    try:
        download_from_list(config)
    except KeyboardInterrupt:
        logger.info("\n\nDownload interrupted by user")
        logger.info("Progress saved - you can resume by running the script again")
    except Exception as e:
        logger.error(f"\nError during download: {e}")
        import traceback
        logger.debug(traceback.format_exc())
