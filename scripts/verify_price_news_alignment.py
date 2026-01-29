"""Verify price data and news data date range alignment"""
import pandas as pd
from pathlib import Path
import json
from collections import Counter

print("=" * 60)
print("PRICE AND NEWS DATA ALIGNMENT CHECK")
print("=" * 60)

# Check price data
price_dir = Path("data/prices")
print(f"\n1. Checking price data directory: {price_dir}")
print(f"   Exists: {price_dir.exists()}")

if price_dir.exists():
    price_files = list(price_dir.glob("*.csv"))
    print(f"   Total price files: {len(price_files)}")
    print(f"   Sample files: {[f.name for f in price_files[:5]]}")
    
    # Check date ranges for sample tickers
    print(f"\n2. Checking price data date ranges (first 10 files)...")
    price_date_ranges = {}
    price_years = Counter()
    
    for price_file in price_files[:10]:
        ticker = price_file.stem
        try:
            df = pd.read_csv(price_file, index_col=0, parse_dates=True)
            if not df.empty and 'close' in df.columns:
                dates = df.index
                price_date_ranges[ticker] = {
                    'start': dates.min(),
                    'end': dates.max(),
                    'rows': len(df)
                }
                # Count years
                for date in dates:
                    year = date.year
                    price_years[year] += 1
        except Exception as e:
            print(f"   Error reading {ticker}: {e}")
    
    if price_date_ranges:
        print(f"   Sample ticker date ranges:")
        for ticker, ranges in list(price_date_ranges.items())[:5]:
            print(f"     {ticker}: {ranges['start'].date()} to {ranges['end'].date()} ({ranges['rows']} rows)")
        
        all_starts = [r['start'] for r in price_date_ranges.values()]
        all_ends = [r['end'] for r in price_date_ranges.values()]
        price_data_start = max(all_starts)  # Latest start
        price_data_end = min(all_ends)      # Earliest end
        
        print(f"\n   Price data range (intersection): {price_data_start.date()} to {price_data_end.date()}")
        print(f"   Price data years: {sorted(set([d.year for d in all_starts + all_ends]))}")
        
        print(f"\n   Year distribution in price data:")
        for year, count in sorted(price_years.items()):
            print(f"     {year}: {count} rows")
    else:
        print("   No price data found!")
else:
    print("   Price directory does not exist!")

# Check news data
news_dir = Path("data/news")
print(f"\n3. Checking news data for best coverage month...")
print(f"   Directory: {news_dir}")
print(f"   Exists: {news_dir.exists()}")

if news_dir.exists():
    all_news_files = list(news_dir.glob("*_news.json"))
    print(f"   Total news files: {len(all_news_files)}")
    
    # Quick check of first 100 files for month coverage
    print(f"\n4. Analyzing news date distribution (first 100 files)...")
    month_coverage = Counter()
    news_years = Counter()
    ticker_date_ranges = {}
    
    for news_file in all_news_files[:100]:
        ticker = news_file.stem.replace('_news', '')
        try:
            with open(news_file, 'r', encoding='utf-8') as f:
                articles = json.load(f)
            
            if isinstance(articles, list) and articles:
                dates = []
                for article in articles[:10]:  # First 10 articles
                    published_at = article.get('publishedAt', '')
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
                            year = article_date.year
                            news_years[year] += 1
                        except:
                            pass
                
                if dates:
                    start_month = min(dates).replace(day=1)
                    end_month = max(dates).replace(day=1)
                    months = pd.date_range(start_month, end_month, freq='MS')
                    for month in months:
                        month_key = month.strftime('%Y-%m')
                        month_coverage[month_key] += 1
        except Exception:
            pass
    
    if month_coverage:
        print(f"   Top 10 months by ticker count:")
        for month, count in month_coverage.most_common(10):
            print(f"     {month}: {count} tickers")
        
        best_month_str, best_count = month_coverage.most_common(1)[0]
        best_month = pd.to_datetime(best_month_str)
        best_year = best_month.year
        
        print(f"\n   BEST NEWS COVERAGE: {best_month_str} with {best_count} tickers")
        print(f"   Best news year: {best_year}")
        
        print(f"\n   News year distribution:")
        for year, count in sorted(news_years.items()):
            print(f"     {year}: {count} articles")
    else:
        print("   No news data found!")
else:
    print("   News directory does not exist!")

# Alignment check
print(f"\n" + "=" * 60)
print("ALIGNMENT ANALYSIS")
print("=" * 60)

if price_date_ranges and month_coverage:
    price_years_set = set([d.year for d in all_starts + all_ends])
    best_news_year = best_year
    
    print(f"\nPrice data years: {sorted(price_years_set)}")
    print(f"Best news year: {best_year}")
    
    if best_news_year in price_years_set:
        print(f"\n[OK] ALIGNMENT: Price data and best news coverage are from the same year ({best_news_year})")
        print(f"    The backtest can proceed with {best_month_str} period")
    else:
        print(f"\n[WARNING] MISALIGNMENT: Price data is from {sorted(price_years_set)}, but best news is from {best_news_year}")
        print(f"\nOptions:")
        if best_news_year > max(price_years_set):
            print(f"  1. Get {best_news_year} price data (recommended if available)")
            print(f"  2. Use {max(price_years_set)} news data instead (may have less coverage)")
        else:
            print(f"  1. Use {best_news_year} news data (already available)")
            print(f"  2. Get {best_news_year} price data if needed")
        
        # Check if there's good news coverage in price data year
        price_year = max(price_years_set)  # Use latest year
        news_in_price_year = [m for m, c in month_coverage.items() if m.startswith(str(price_year))]
        if news_in_price_year:
            best_news_in_price_year = max(news_in_price_year, key=lambda m: month_coverage[m])
            print(f"\n   Alternative: Use {best_news_in_price_year} (news coverage: {month_coverage[best_news_in_price_year]} tickers)")
else:
    print("\n[ERROR] Cannot check alignment - missing price or news data")
