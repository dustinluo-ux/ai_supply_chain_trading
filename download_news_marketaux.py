"""
Download 2023-2024 news for all tickers using Marketaux API
Strategy: Fetch by month to minimize requests, stay within 100 requests/day limit
"""
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from src.data.news_sources.marketaux_source import MarketauxSource

# Load environment variables
load_dotenv()

DATA_DIR = Path("data")
PRICES_DIR = DATA_DIR / "prices"
NEWS_DIR = DATA_DIR / "news"
NEWS_DIR.mkdir(parents=True, exist_ok=True)

# Daily request limits
MAX_REQUESTS_PER_DAY = 90  # Leave buffer below 100 limit
START_DATE = "2023-01-01"
END_DATE = "2024-12-31"

print("=" * 60)
print("MARKETAUX NEWS DOWNLOADER - 2023-2024")
print("=" * 60)

# Check API key
api_key = os.getenv("MARKETAUX_API_KEY")
if not api_key:
    print("❌ ERROR: MARKETAUX_API_KEY not found in .env file")
    exit(1)

# Get list of tickers from CSV files in data/prices/
print("\n[1/3] Discovering tickers...", flush=True)
csv_files = list(PRICES_DIR.glob("*.csv"))
tickers = sorted([f.stem for f in csv_files if f.suffix == '.csv'])
print(f"✓ Found {len(tickers)} tickers: {', '.join(tickers[:5])}..." + 
      (f" and {len(tickers)-5} more" if len(tickers) > 5 else ""))
print()

# Generate month-by-month date ranges
print("[2/3] Generating month-by-month download plan...", flush=True)
month_ranges = []
start_dt = datetime.strptime(START_DATE, "%Y-%m-%d")
end_dt = datetime.strptime(END_DATE, "%Y-%m-%d")

current = start_dt
while current <= end_dt:
    # First day of month
    month_start = current.replace(day=1)
    # Last day of month
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)
    
    # Don't go past end_date
    if month_end > end_dt:
        month_end = end_dt
    
    month_ranges.append({
        'year': month_start.year,
        'month': month_start.month,
        'start': month_start.strftime("%Y-%m-%d"),
        'end': month_end.strftime("%Y-%m-%d")
    })
    
    # Move to next month
    if month_start.month == 12:
        current = month_start.replace(year=month_start.year + 1, month=1, day=1)
    else:
        current = month_start.replace(month=month_start.month + 1, day=1)

print(f"✓ Generated {len(month_ranges)} month ranges ({START_DATE} to {END_DATE})")
print()

# Create download tasks: (ticker, year, month, start_date, end_date)
download_tasks = []
for ticker in tickers:
    for month_info in month_ranges:
        download_tasks.append({
            'ticker': ticker,
            'year': month_info['year'],
            'month': month_info['month'],
            'start_date': month_info['start'],
            'end_date': month_info['end']
        })

total_tasks = len(download_tasks)
print(f"Total download tasks: {len(tickers)} tickers × {len(month_ranges)} months = {total_tasks} requests")
print(f"Estimated days needed: {total_tasks // MAX_REQUESTS_PER_DAY + (1 if total_tasks % MAX_REQUESTS_PER_DAY > 0 else 0)} days")
print()

# Check for existing files (resume capability)
print("[3/3] Checking for existing downloads (resume capability)...", flush=True)
existing_files = set()
for task in download_tasks:
    filename = f"{task['ticker']}_{task['year']}_{task['month']:02d}.json"
    filepath = NEWS_DIR / filename
    if filepath.exists():
        existing_files.add((task['ticker'], task['year'], task['month']))

pending_tasks = [t for t in download_tasks 
                 if (t['ticker'], t['year'], t['month']) not in existing_files]

print(f"✓ Found {len(existing_files)} already downloaded")
print(f"✓ {len(pending_tasks)} tasks remaining")
print()

if len(pending_tasks) == 0:
    print("✅ All news data already downloaded!")
    exit(0)

# Initialize Marketaux source
print("Initializing MarketauxSource...", flush=True)
try:
    source = MarketauxSource(data_dir=str(NEWS_DIR), keywords=None)
    print("✓ MarketauxSource initialized")
except Exception as e:
    print(f"❌ Error initializing MarketauxSource: {e}")
    exit(1)

print()
print("=" * 60)
print("STARTING DOWNLOAD")
print("=" * 60)
print(f"Daily limit: {MAX_REQUESTS_PER_DAY} requests/day")
print(f"Remaining tasks: {len(pending_tasks)}")
print()

# Track progress
requests_today = 0
day_number = 1
completed_tasks = 0
failed_tasks = []

for task_idx, task in enumerate(pending_tasks, 1):
    # Check daily limit
    if requests_today >= MAX_REQUESTS_PER_DAY:
        remaining_tasks = len(pending_tasks) - completed_tasks
        print()
        print("=" * 60)
        print(f"📊 DAILY LIMIT REACHED (Day {day_number})")
        print("=" * 60)
        print(f"Progress: {completed_tasks}/{total_tasks} requests completed")
        print(f"Remaining: {remaining_tasks} requests")
        print(f"Estimated days remaining: {remaining_tasks // MAX_REQUESTS_PER_DAY + 1}")
        print()
        print("💡 Resume tomorrow by running this script again.")
        print("   It will automatically skip already downloaded months.")
        print("=" * 60)
        break
    
    ticker = task['ticker']
    year = task['year']
    month = task['month']
    start_date = task['start_date']
    end_date = task['end_date']
    
    filename = f"{ticker}_{year}_{month:02d}.json"
    filepath = NEWS_DIR / filename
    
    # Skip if already exists (double-check)
    if filepath.exists():
        print(f"[{task_idx}/{len(pending_tasks)}] ⏭️  {ticker} {year}-{month:02d} (already exists)", flush=True)
        continue
    
    # Fetch articles
    print(f"[{task_idx}/{len(pending_tasks)}] 📥 {ticker} {year}-{month:02d}...", flush=True)
    try:
        articles = source.fetch_articles_for_ticker(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            use_cache=False  # Don't use cache, we're saving by month
        )
        
        # Save to month-specific file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'ticker': ticker,
                'year': year,
                'month': month,
                'start_date': start_date,
                'end_date': end_date,
                'article_count': len(articles),
                'articles': articles,
                'downloaded_at': datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        requests_today += 1
        completed_tasks += 1
        
        print(f"     ✓ {len(articles)} articles saved to {filename}", flush=True)
        
    except Exception as e:
        print(f"     ✗ Error: {e}", flush=True)
        failed_tasks.append({
            'task': task,
            'error': str(e)
        })
        requests_today += 1  # Count failed requests too
        completed_tasks += 1
    
    # Show progress every 10 requests
    if completed_tasks % 10 == 0:
        remaining = len(pending_tasks) - completed_tasks
        print(f"   Progress: {completed_tasks}/{len(pending_tasks)} ({requests_today}/{MAX_REQUESTS_PER_DAY} today)", flush=True)

# Final summary
print()
print("=" * 60)
print("DOWNLOAD SESSION COMPLETE")
print("=" * 60)
print(f"Completed: {completed_tasks}/{len(pending_tasks)} tasks")
print(f"Requests used today: {requests_today}/{MAX_REQUESTS_PER_DAY}")
print(f"Failed: {len(failed_tasks)}")

if failed_tasks:
    print("\nFailed tasks:")
    for failed in failed_tasks[:5]:  # Show first 5
        task = failed['task']
        print(f"  - {task['ticker']} {task['year']}-{task['month']:02d}: {failed['error']}")

remaining = len(pending_tasks) - completed_tasks
if remaining > 0:
    print(f"\nRemaining tasks: {remaining}")
    print(f"Run this script again tomorrow to continue.")
else:
    print("\n✅ All tasks completed!")

print("=" * 60)
