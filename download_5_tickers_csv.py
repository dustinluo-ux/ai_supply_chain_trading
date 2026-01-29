"""Download fresh price data for 5 test tickers and save as CSV"""
import yfinance as yf
import pandas as pd
from pathlib import Path
import time

TICKERS = ['QLYS', 'NVDA', 'AMD', 'SLAB', 'SYNA']
DATA_DIR = Path("data/prices")
DATA_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("DOWNLOADING 5 TICKERS - CSV FORMAT")
print("=" * 60)
print(f"Tickers: {', '.join(TICKERS)}")
print(f"Period: 2023-01-01 to 2024-12-31")
print(f"Output: {DATA_DIR}/{{ticker}}.csv\n")

for idx, ticker in enumerate(TICKERS, 1):
    print(f"[{idx}/{len(TICKERS)}] Downloading {ticker}...", flush=True)
    try:
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(start='2023-01-01', end='2024-12-31')
        
        if df.empty:
            print(f"  ⚠ {ticker}: No data returned", flush=True)
            continue
        
        # Ensure we have close and volume columns
        if 'Close' not in df.columns:
            print(f"  ✗ {ticker}: No 'Close' column found", flush=True)
            continue
        
        # Rename columns to lowercase
        df.columns = [col.lower() for col in df.columns]
        
        # Save as CSV (Date will be saved as index)
        output_path = DATA_DIR / f"{ticker}.csv"
        df.to_csv(output_path)
        
        print(f"  ✓ {ticker}: {len(df)} rows saved to {output_path}", flush=True)
        
        # 3-second delay between tickers (except for the last one)
        if idx < len(TICKERS):
            time.sleep(3)
            
    except Exception as e:
        print(f"  ✗ {ticker}: Error - {e}", flush=True)
        if idx < len(TICKERS):
            time.sleep(3)

print("\n" + "=" * 60)
print("✅ Download complete!")
print("=" * 60)
