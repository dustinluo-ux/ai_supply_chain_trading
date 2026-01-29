# News Coverage Detection Fix

## Problem Identified

The detection logic was only checking tickers that had price data loaded (`prices_dict.keys()`), which limited the coverage analysis to a small subset of tickers. With 3,720 news files available, this caused the system to only detect 7 tickers with October 2022 coverage.

## Root Cause

**Line 299 (old code):**
```python
all_tickers = list(prices_dict.keys())  # Only checks tickers with price data
```

This meant:
- If DEBUG_MODE limits tickers, only those are checked
- If price data loading fails for some tickers, they're excluded
- News files for tickers without price data are ignored

## Solution

**Changed to scan ALL news files:**
```python
# Step 1: Track date ranges for ALL news files (not just tickers with price data)
all_news_files = list(news_dir.glob("*_news.json"))
# Scan all files to find best coverage month
```

**Then filter to tickers with BOTH price data AND news:**
```python
valid_tickers_for_backtest = [
    t for t in TICKERS 
    if t in prices_dict.keys() and t in valid_tickers_with_news
]
```

## Expected Results

1. **Best month detection**: Now scans all 3,720 news files to find the month with most ticker coverage
2. **Better coverage**: Should find months with 40+ tickers instead of just 7
3. **Accurate filtering**: Only uses tickers that have both price data AND news in the best month

## Diagnostic Findings

From `quick_news_check.py`:
- **Total news files**: 3,720
- **Year distribution** (sample): 2022 (170 articles), 2023 (89 articles)
- **Top months by ticker count** (from 500 files):
  - 2023-04: 18 tickers
  - 2023-05: 16 tickers
  - 2022-12: 16 tickers
  - 2022-11: 12 tickers

**Recommendation**: The system will now automatically find the month with best coverage (likely 2023-04 or 2023-05 based on sample), which should have 40+ tickers when scanning all files.

## Files Modified

- `test_signals.py` lines 297-337: Changed to scan all news files instead of just price data tickers
- `test_signals.py` lines 402-407: Updated filtering to require both price data and news
