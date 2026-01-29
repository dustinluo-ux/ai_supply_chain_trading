# Full Dataset Download Guide

## Overview

The `download_full_dataset.py` script downloads price data for 100-200 small-cap stocks ($500M-$5B market cap) for backtesting.

## What It Does

1. **Gets Ticker List** (100-200 tickers)
   - Tries Russell 2000 CSV file first (if exists)
   - Falls back to extended small-cap list (150+ tickers)
   
2. **Filters by Market Cap** ($500M-$5B)
   - Checks each ticker's market cap
   - Keeps only those in range
   - Takes 10-20 minutes for 150+ tickers

3. **Downloads Price Data** (2023-2024)
   - Fetches 2 years of daily OHLCV data
   - Saves as parquet files in `data/prices/`
   - Skips already downloaded tickers (uses cache)
   - Takes 20-40 minutes for 100+ tickers

## Usage

```bash
python download_full_dataset.py
```

The script will:
- Show progress: `[50/150] Fetching ticker...`
- Display summary at the end
- Save detailed report to `data/prices/download_summary.txt`

## Estimated Time

- **Market Cap Filtering**: 10-20 minutes (150 tickers × ~5 seconds each)
- **Price Data Download**: 20-40 minutes (100 tickers × ~15 seconds each)
- **Total**: 30-60 minutes

## Progress Tracking

You'll see:
```
[1/150] Fetching ON...
[2/150] Fetching SWKS...
...
Progress: 50/150 tickers processed (45 successful, 3 cached, 2 failed)
```

## Output

- **Price Data**: `data/prices/{ticker}.parquet` (one file per ticker)
- **Summary**: `data/prices/download_summary.txt`
- **Logs**: `logs/ai_supply_chain_YYYYMMDD.log`

## Adding More Tickers

### Option 1: Add Russell 2000 CSV

Create `data/russell2000_tickers.csv`:
```csv
ticker
AAPL
MSFT
...
```

The script will automatically use this file if it exists.

### Option 2: Extend the List

Edit `src/utils/ticker_utils.py` → `get_extended_small_cap_list()` and add more tickers.

## After Download

Once complete, you can:
1. Run technical backtest: `python run_technical_backtest.py`
2. Check downloaded tickers: `ls data/prices/*.parquet`
3. View summary: `cat data/prices/download_summary.txt`

## Troubleshooting

**Only a few tickers downloaded:**
- Check market cap filter range in `config.yaml`
- Some tickers may be delisted or have no data
- Verify ticker symbols are correct

**Slow download:**
- Normal for 100+ tickers (yfinance rate limiting)
- Script includes 0.2s delay between requests
- Can resume later (uses cache)

**Failed tickers:**
- Check `download_summary.txt` for list
- Common reasons: delisted, symbol changed, no data available

## Next Steps

After successful download:
1. Verify: Check `data/prices/` has 50+ parquet files
2. Run backtest: `python run_technical_backtest.py`
3. Review results: Check `backtests/results/`

The system is ready for backtesting once you have 50+ tickers with price data!
