# News Date Range Detection Diagnosis

## Problem Identified

The date range detection logic takes the **UNION** (minimum start, maximum end) across ALL sample tickers, which creates a misleading overall range.

### Example:
- **A**: 2022-10-04 to 2022-12-30 (70 articles)
- **AAN**: 2023-04-19 to 2023-11-22 (4 articles)  
- **AAXN**: 2023-02-01 to 2023-10-30 (11 articles)

**Detected Range**: 2022-10-01 to 2023-11-22 (union of all)

This is **misleading** because:
- Most tickers only have 2022 data (Oct-Dec)
- A few tickers have 2023 data
- The union makes it look like there's coverage from Oct 2022 to Nov 2023
- But for any specific ticker, the actual range is much smaller

## Actual File Contents

### A_news.json Verification:
- **File**: `C:\Users\dusro\OneDrive\Programming\ai_supply_chain_trading\data\news\A_news.json`
- **Size**: 420,644 bytes
- **Total articles**: 70
- **Actual date range**: 2022-10-04 to 2022-12-30
- **November 2022 articles**: 36 articles (2022-11-01 to 2022-11-29) ✓

**The file DOES contain November 1-29 articles!**

## Detection Logic Location

**File**: `test_signals.py` lines 282-327

**Current Logic**:
```python
# Samples first 10 tickers
sample_tickers = list(prices_dict.keys())[:10]

for ticker in sample_tickers:
    # Loads news file
    # Finds min/max dates for that ticker
    # Takes UNION: min(all starts), max(all ends)
    if news_data_start is None or ticker_news_start < news_data_start:
        news_data_start = ticker_news_start
    if news_data_end is None or ticker_news_end > news_data_end:
        news_data_end = ticker_news_end
```

## File Deletion Information

**Location of deleted files**:
- Directory: `C:\Users\dusro\OneDrive\Programming\ai_supply_chain_trading\data\news`
- Files deleted: All `*_news.json` files (3,701 files)
- Command used: `Remove-Item data\news\*_news.json -Force`
- When: During re-processing on 2026-01-24

**Recovery options**:
1. **Recycle Bin**: Check Windows Recycle Bin
2. **OneDrive Version History**: 
   - Right-click `data/news` folder in OneDrive
   - Select "Version history"
   - Restore previous version
3. **Git History**: If files were committed, use `git log` and `git checkout`

## Fix Applied

1. **Added verification** after detection to show actual ranges for sample tickers
2. **Added note** that detected range is a UNION (may be misleading)
3. **Added verification** in detection loop to confirm file contents match detected range

## Recommendations

1. **Use intersection instead of union** for more conservative date range
2. **Or** show per-ticker ranges instead of overall range
3. **Or** filter sample tickers to only those with overlapping date ranges
