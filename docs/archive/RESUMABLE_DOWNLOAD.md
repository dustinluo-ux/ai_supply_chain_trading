# Resumable Download Feature

## Overview

The download script is now **fully resumable**. If interrupted, you can re-run it and it will automatically skip already downloaded tickers and continue from where it left off.

## Features

### 1. **Automatic Resume**
- Checks `data/prices/` for existing `.parquet` files at startup
- Skips tickers that already have valid data
- Only downloads remaining tickers

### 2. **Retry Logic**
- **3 retries** per ticker if download fails
- **5-second pause** between retries
- Handles temporary network issues and Yahoo Finance rate limits

### 3. **Rate Limiting**
- **1 second delay** between each ticker download
- Prevents Yahoo Finance from blocking requests
- More reliable than 0.2s delay

### 4. **Progress Saving**
- Saves progress **every 10 tickers**
- If interrupted, you only lose progress on the current ticker (max 1 ticker)
- Files are saved immediately after download

### 5. **Progress Display**
```
Found 11 tickers already downloaded
  Examples: ON, SWKS, QRVO, MRVL, MCHP, MPWR, WOLF, ALGM, DIOD, SLAB...
Downloading 54 remaining tickers...
[1/54] Fetching CRUS...
Progress: 10/54 tickers downloaded (21 total, 11 cached, 0 failed)
```

## Usage

### First Run
```bash
python download_full_dataset.py
```

### Resume After Interruption
```bash
# Just run it again - it will automatically resume!
python download_full_dataset.py
```

The script will:
1. Check existing downloads
2. Show: "Skipping X tickers (already downloaded), downloading Y remaining"
3. Continue from where it stopped

## Example Output

```
[Step 2/2] Checking existing downloads and resuming...
Found 11 tickers already downloaded
  Examples: ON, SWKS, QRVO, MRVL, MCHP, MPWR, WOLF, ALGM, DIOD, SLAB...
Downloading 54 remaining tickers...
Date range: 2023-01-01 to 2024-12-31
This may take 20-40 minutes...
Progress will be shown as: [X/Total] Fetched ticker...
Progress saved every 10 tickers (resumable if interrupted)
Rate limiting: 1 second between tickers (to avoid Yahoo blocking)

[1/54] Fetching CRUS...
[2/54] Fetching OLED...
...
Progress: 10/54 tickers downloaded (21 total, 11 cached, 0 failed)
...
```

## How It Works

1. **Startup Check**: Scans `data/prices/*.parquet` files
2. **Validation**: Checks if existing files cover the required date range
3. **Filter**: Removes already-downloaded tickers from the list
4. **Download**: Only downloads remaining tickers
5. **Save**: Saves each file immediately after download
6. **Progress**: Saves checkpoint every 10 tickers

## Benefits

✅ **Resumable**: Can stop and resume anytime
✅ **Efficient**: Doesn't re-download existing data
✅ **Reliable**: Retry logic handles temporary failures
✅ **Safe**: Rate limiting prevents blocking
✅ **Transparent**: Shows exactly what's being skipped/downloaded

## Troubleshooting

**Q: Script says "All tickers already downloaded" but I want to re-download?**
A: Delete the specific `.parquet` files you want to re-download, or delete the entire `data/prices/` folder.

**Q: Some tickers keep failing?**
A: Check the ticker symbols are correct. Some may be delisted or have no data available.

**Q: Download is very slow?**
A: Normal - 1 second delay per ticker prevents Yahoo from blocking. For 65 tickers, expect ~65 seconds minimum + download time.

**Q: Can I reduce the delay?**
A: Not recommended - Yahoo Finance may block requests if too fast. 1 second is a safe rate.

## Next Steps

After successful download:
```bash
python run_technical_backtest.py
```

The system is ready for backtesting once you have 50+ tickers with price data!
