# Download From List Guide

## Overview

`download_from_list.py` downloads price data for a pre-identified list of 65 tickers, **skipping market cap filtering entirely**. This is faster and avoids the 10-20 minute market cap checking step.

## What It Does

1. **Uses Pre-Identified Ticker List** (65 tickers from previous successful filter)
2. **Skips Market Cap Filtering** - goes straight to downloading
3. **Checks Existing Downloads** - resumes from where it left off
4. **Downloads Price Data** (2023-2024) for remaining tickers
5. **Saves Progress** every 10 tickers (resumable)

## Usage

```bash
python download_from_list.py
```

## Ticker List

The script uses these 65 pre-identified tickers:
- QLYS, SLAB, SYNA, CTMX, ALRM, AB, CVAC, ACAD, TENB, ALG
- ASO, AIV, AMBA, COMM, BLMN, ACHC, AWR, VSH, CRMD, AEO
- ACMR, AEIS, ALKS, ALLO, ALNY, ALXO, ARWR, ASND, ATRA, AUPH
- AVEO, BLUE, BMRN, BPMC, BTAI, CABA, CARA, CBLI, CCXI, CDMO
- CDNA, CERS, CGEN, CHRS, CLLS, CLVS, CRIS, CRNX, CUR, CYRX
- DAWN, DBVT, DCPH, DIOD, FLEX, JBL, SANM, TTMI, AOS, ATI
- AXE, ON, SWKS, QRVO, MRVL

## Features

✅ **No Market Cap Filtering** - Saves 10-20 minutes
✅ **Resumable** - Automatically skips already downloaded tickers
✅ **Rate Limited** - 1 second between tickers (prevents Yahoo blocking)
✅ **Progress Saving** - Saves every 10 tickers
✅ **Retry Logic** - 3 retries per ticker with 5-second pauses

## Estimated Time

- **65 tickers** × **~10 seconds each** = **~11 minutes**
- Plus download time per ticker (~1-2 seconds)
- **Total: ~15-20 minutes**

## Output

- **Price Data**: `data/prices/{ticker}.parquet` (one file per ticker)
- **Summary**: `data/prices/download_from_list_summary.txt`
- **Logs**: `logs/ai_supply_chain_YYYYMMDD.log`

## Example Output

```
DOWNLOAD FROM PRE-IDENTIFIED TICKER LIST
============================================================
Skipping market cap filtering - using known ticker list
============================================================

Loaded 65 pre-identified tickers
Tickers: QLYS, SLAB, SYNA, CTMX, ALRM, AB, CVAC, ACAD, TENB, ALG...

[Step 1/2] Checking existing downloads...
Checking data/prices/ directory...
Found 11 existing .parquet files
Found 11 valid existing tickers with complete data
Found 11 tickers already downloaded
  Examples: ON, SWKS, QRVO, MRVL, DIOD, FLEX, JBL, SANM, TTMI, AOS...
Tickers to process: 65 total, 11 already downloaded, 54 remaining

[Step 2/2] Downloading price data for 54 tickers...
Date range: 2023-01-01 to 2024-12-31
Rate limiting: 1 second between tickers (to avoid Yahoo blocking)
Progress saved every 10 tickers (resumable if interrupted)

[1/54] Fetching QLYS...
[2/54] Fetching SLAB...
...
Progress: 10/54 tickers downloaded (21 total, 11 cached, 0 failed)
...

============================================================
DOWNLOAD COMPLETE
============================================================
Total tickers: 65
✅ Successful: 65
❌ Failed: 0
⏱️  Time elapsed: 12.5 minutes

Data saved to: data/prices/
```

## Advantages Over Full Download Script

| Feature | `download_full_dataset.py` | `download_from_list.py` |
|---------|----------------------------|------------------------|
| Market Cap Filtering | ✅ Yes (10-20 min) | ❌ No (skipped) |
| Ticker Source | Extended list → Filter | Pre-identified list |
| Time to Start Download | ~15-25 minutes | ~30 seconds |
| Total Time | 30-60 minutes | 15-20 minutes |
| Use Case | First time setup | Quick download of known tickers |

## Resuming

If interrupted, just run again:
```bash
python download_from_list.py
```

It will automatically:
- Detect already downloaded tickers
- Skip them
- Continue from where it stopped

## After Download

Once complete:
```bash
python run_technical_backtest.py
```

The system is ready for backtesting with 65 tickers!
