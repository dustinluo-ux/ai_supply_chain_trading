"""
Simple Price Data Downloader
Downloads 2023-2024 OHLCV data for 65 tickers - no checking, no resume, just download
"""
import yfinance as yf
import pandas as pd
import time
import os

# Hardcoded ticker list
TICKERS = [
    'QLYS', 'SLAB', 'SYNA', 'CTMX', 'ALRM', 'AB', 'CVAC', 'ACAD', 'TENB', 'ALG',
    'ASO', 'AIV', 'AMBA', 'COMM', 'BLMN', 'ACHC', 'AWR', 'VSH', 'CRMD', 'AEO',
    'BLKB', 'KTOS', 'VG', 'RPD', 'ACMR', 'FRSH', 'AIR', 'ABR', 'PLAB', 'CALX',
    'IDCC', 'ENPH', 'CRUS', 'ALGM', 'MCHP', 'ADTN', 'AEIS', 'FORM', 'ON', 'DIOD',
    'MPWR', 'WOLF', 'QRVO', 'CLB', 'SWKS', 'MRVL', 'NTGR', 'APLE', 'AUPH', 'BRC',
    'S', 'SEDG', 'PLUG', 'VIAV', 'COHR', 'CIEN', 'LITE', 'AAOI', 'INFN', 'FSLR',
    'BLDP', 'NVDA', 'AMD', 'AVGO', 'QCOM'
]

# Create output directory
os.makedirs('data/prices', exist_ok=True)

print(f"Downloading price data for {len(TICKERS)} tickers (2023-2024)...")
print("=" * 60)

for idx, ticker in enumerate(TICKERS, 1):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(start='2023-01-01', end='2024-12-31', interval='1d')
        
        if not df.empty:
            # Standardize column names
            df.columns = [col.lower() for col in df.columns]
            df['ticker'] = ticker
            
            # Save to parquet
            output_path = f'data/prices/{ticker}.parquet'
            df.to_parquet(output_path)
            print(f"[{idx}/{len(TICKERS)}] Downloaded {ticker} ({len(df)} rows)")
        else:
            print(f"[{idx}/{len(TICKERS)}] No data for {ticker}")
    
    except Exception as e:
        print(f"[{idx}/{len(TICKERS)}] Error downloading {ticker}: {e}")
    
    # Wait 2 seconds between tickers
    if idx < len(TICKERS):
        time.sleep(2)

print("=" * 60)
print("Download complete!")
