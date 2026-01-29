"""Test if the data in Downloads/stock/stock_market_data is compatible with test_signals.py"""
from src.data.universe_loader import UniverseLoader
import sys

print("Testing data compatibility...")
print("=" * 60)

# Load universe
loader = UniverseLoader()
print(f"Data directory: {loader.data_dir}")
print(f"Date range: {loader.config['universe_selection']['date_range']}")
print()

# Try to load a small sample
print("Loading sample tickers (max 5)...")
tickers = loader.load_universe(max_tickers=5)

if tickers:
    print(f"\n✓ Successfully loaded {len(tickers)} tickers")
    print("\nSample ticker metadata:")
    for ticker in tickers[:3]:
        print(f"  {ticker['ticker']}: {ticker['data_points']} data points, "
              f"date range: {ticker['date_range'][0].date()} to {ticker['date_range'][1].date()}")
    
    # Get summary
    summary = loader.get_universe_summary(tickers)
    print(f"\nSummary:")
    print(f"  Count: {summary['count']}")
    print(f"  Date range: {summary['date_range'][0].date()} to {summary['date_range'][1].date()}")
    print(f"  Avg data points: {summary['avg_data_points']:.0f}")
    print(f"  News coverage: {summary['with_news']}/{summary['count']} ({summary['news_coverage']:.1%})")
    
    print("\n" + "=" * 60)
    print("✓ DATA IS COMPATIBLE - test_signals.py should work!")
    print("=" * 60)
    sys.exit(0)
else:
    print("\n✗ No valid tickers found!")
    print("\nPossible issues:")
    print("  1. Date range mismatch - check data_config.yaml date_range")
    print("  2. CSV format issues - check if Date column is readable")
    print("  3. Missing required columns (Close, Adjusted Close)")
    print("  4. Insufficient data points")
    print("\n" + "=" * 60)
    print("✗ DATA MAY NOT BE COMPATIBLE - check issues above")
    print("=" * 60)
    sys.exit(1)
