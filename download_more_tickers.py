"""
Download price data for additional semiconductor stocks to expand the backtest universe
This allows the backtest to actually select different stocks for different approaches
"""
import yfinance as yf
import pandas as pd
from pathlib import Path
import time
from datetime import datetime

# Additional semiconductor stocks to add
ADDITIONAL_TICKERS = [
    'INTC',  # Intel
    'TSM',   # Taiwan Semiconductor
    'AVGO',  # Broadcom
    'QCOM',  # Qualcomm
    'MU',    # Micron
    'MRVL',  # Marvell
    'KLAC',  # KLA Corporation
    'LRCX',  # Lam Research
    'AMAT',  # Applied Materials
    'ASML',  # ASML Holding
    'TXN',   # Texas Instruments
    'ADI',   # Analog Devices
    'MCHP',  # Microchip Technology
    'NXPI',  # NXP Semiconductors
    'ON',    # ON Semiconductor
    'STM',   # STMicroelectronics
    'SWKS',  # Skyworks Solutions
    'QRVO',  # Qorvo
    'WOLF',  # Wolfspeed
    'CRUS',  # Cirrus Logic
]

DATA_DIR = Path("data/prices")
DATA_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("DOWNLOADING ADDITIONAL SEMICONDUCTOR STOCKS")
print("=" * 60)
print(f"Target: {len(ADDITIONAL_TICKERS)} additional tickers")
print(f"Period: 2023-01-01 to 2024-12-31")
print()

successful = 0
failed = 0

for i, ticker in enumerate(ADDITIONAL_TICKERS, 1):
    file_path = DATA_DIR / f"{ticker}.csv"
    
    # Skip if already exists
    if file_path.exists():
        print(f"[{i}/{len(ADDITIONAL_TICKERS)}] {ticker}: Already exists, skipping")
        successful += 1
        continue
    
    try:
        print(f"[{i}/{len(ADDITIONAL_TICKERS)}] Downloading {ticker}...", end=" ", flush=True)
        
        # Download data
        stock = yf.Ticker(ticker)
        df = stock.history(start='2023-01-01', end='2025-01-01')
        
        if df.empty:
            print("FAILED (no data)")
            failed += 1
            continue
        
        # Filter to 2023-2024
        df = df.loc['2023-01-01':'2024-12-31']
        
        if df.empty:
            print("FAILED (no data in range)")
            failed += 1
            continue
        
        # Reset index to make Date a column
        df.reset_index(inplace=True)
        df.rename(columns={'Date': 'Date'}, inplace=True)
        
        # Save as CSV
        df.to_csv(file_path, index=False)
        
        print(f"OK ({len(df)} rows)")
        successful += 1
        
        # Rate limiting
        time.sleep(1)
        
    except Exception as e:
        print(f"FAILED: {e}")
        failed += 1
        time.sleep(2)  # Longer delay on error

print()
print("=" * 60)
print("DOWNLOAD SUMMARY")
print("=" * 60)
print(f"Successful: {successful}/{len(ADDITIONAL_TICKERS)}")
print(f"Failed: {failed}/{len(ADDITIONAL_TICKERS)}")
print(f"Total tickers now: {len(list(DATA_DIR.glob('*.csv')))}")
print()
print("Next steps:")
print("1. Run simple_backtest_v2.py again - it will automatically detect new tickers")
print("2. Change TOP_N back to 10 in simple_backtest_v2.py for proper selection")
print("=" * 60)
