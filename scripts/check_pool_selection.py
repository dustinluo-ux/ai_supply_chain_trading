"""Check which stocks have news data and verify pool selection logic"""
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data.universe_loader import UniverseLoader

# Check news data for key AI stocks
news_dir = Path("data/news")
known_ai_stocks = ['NVDA', 'AMD', 'TSM', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 
                   'INTC', 'QCOM', 'AVGO', 'MU', 'LRCX', 'KLAC', 'AMAT', 'SNPS', 'CDNS']

print("Checking news data availability for known AI stocks:")
print("=" * 60)
has_news = []
no_news = []

for ticker in known_ai_stocks:
    files = list(news_dir.glob(f"{ticker}_*.json"))
    if files:
        has_news.append(ticker)
        print(f"  {ticker}: {len(files)} files [HAS NEWS]")
    else:
        no_news.append(ticker)
        print(f"  {ticker}: No news files [MISSING]")

print("\n" + "=" * 60)
print(f"Stocks WITH news: {len(has_news)} - {has_news}")
print(f"Stocks WITHOUT news: {len(no_news)} - {no_news}")

# Test universe loader to see what it would select
print("\n" + "=" * 60)
print("Testing UniverseLoader pool selection:")
print("=" * 60)

loader = UniverseLoader()
ticker_metadata = loader.load_universe(
    max_tickers=15,
    rank_by_supply_chain=True,
    supply_chain_pool_size=45
)

selected_tickers = [t['ticker'] for t in ticker_metadata]
print(f"\nSelected {len(selected_tickers)} tickers:")
print(f"  {selected_tickers}")

print("\nKnown AI stocks in selection:")
for ticker in known_ai_stocks:
    if ticker in selected_tickers:
        print(f"  {ticker}: [SELECTED] (ranked #{selected_tickers.index(ticker) + 1})")
    else:
        print(f"  {ticker}: [NOT SELECTED]")
