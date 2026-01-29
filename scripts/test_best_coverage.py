"""Test the best coverage date range detection logic"""
from collections import Counter
import pandas as pd
import json
from pathlib import Path

print("=" * 60)
print("TESTING BEST COVERAGE DATE RANGE DETECTION")
print("=" * 60)

news_dir = Path("data/news")

# Get all tickers (simulate what backtest does)
all_tickers = ['A', 'AA', 'AAL', 'AAN', 'AAON', 'AAPL', 'AAP', 'AAT', 'AAWH', 'AAXN', 'NVDA']

print(f"\nStep 1: Scanning news files for {len(all_tickers)} tickers...")

ticker_date_ranges = {}

for ticker in all_tickers:
    news_file = news_dir / f"{ticker}_news.json"
    if news_file.exists():
        try:
            with open(news_file, 'r', encoding='utf-8') as f:
                articles = json.load(f)
            if isinstance(articles, list) and articles:
                dates = []
                for article in articles:
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

print(f"Found news data for {len(ticker_date_ranges)} tickers")

if ticker_date_ranges:
    print(f"\nStep 2: Finding month with best ticker coverage...")
    
    # Count tickers per month
    month_coverage = Counter()
    for ticker, ranges in ticker_date_ranges.items():
        start_month = ranges['start'].replace(day=1)
        end_month = ranges['end'].replace(day=1)
        months = pd.date_range(start_month, end_month, freq='MS')
        for month in months:
            month_key = month.strftime('%Y-%m')
            month_coverage[month_key] += 1
    
    if month_coverage:
        # Find best month
        best_month_str, ticker_count = month_coverage.most_common(1)[0]
        best_month = pd.to_datetime(best_month_str)
        
        print(f"\nBest coverage: {best_month_str} with {ticker_count} tickers")
        print(f"\nTop 5 months:")
        for month_str, count in month_coverage.most_common(5):
            print(f"  {month_str}: {count} tickers")
        
        # Set date range
        news_data_start = best_month
        if best_month.month == 12:
            news_data_end = best_month.replace(year=best_month.year + 1, month=1) - pd.Timedelta(days=1)
        else:
            news_data_end = best_month.replace(month=best_month.month + 1) - pd.Timedelta(days=1)
        
        print(f"\nDate range: {news_data_start.date()} to {news_data_end.date()}")
        
        # Filter tickers
        valid_tickers = [
            ticker for ticker, ranges in ticker_date_ranges.items()
            if ranges['start'] <= news_data_end and ranges['end'] >= news_data_start
        ]
        
        print(f"\nValid tickers with news in this period: {len(valid_tickers)}")
        print(f"Tickers: {valid_tickers[:10]}...")
        
        # Verify
        print(f"\nVerification - Sample ticker coverage:")
        for ticker in valid_tickers[:5]:
            news_file = news_dir / f"{ticker}_news.json"
            try:
                with open(news_file, 'r', encoding='utf-8') as f:
                    articles = json.load(f)
                period_articles = [
                    a for a in articles 
                    if a.get('publishedAt', '') and best_month_str in a['publishedAt']
                ]
                print(f"  {ticker}: {len(period_articles)} articles in {best_month_str}")
            except Exception:
                pass
