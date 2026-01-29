# Best Coverage Date Range Detection - Implementation Notes

## Overview

The date range detection now uses a **"best coverage period"** approach instead of the union approach. This finds the month with the most tickers having news data and uses that period for backtesting.

## Why This Compromise?

**Problem with Union Approach:**
- Takes min(start) and max(end) across ALL tickers
- Creates huge date ranges (e.g., Oct 2022 to Nov 2023)
- Most tickers have no news on most dates in that range
- Results in many "No articles in range" errors

**Solution - Best Coverage:**
- Finds month with most tickers having news
- Uses only that month for backtesting
- Filters tickers to only those with news in that period
- Ensures high coverage rate (40+ tickers with actual news)

## Implementation Details

### Location
`test_signals.py` lines ~282-430

### Key Variable
```python
USE_BEST_COVERAGE = True  # Set to False to use union/intersection approach
```

### Steps:
1. **Scan all tickers**: Load date ranges for all tickers with news files
2. **Count coverage per month**: Count how many tickers have news in each month
3. **Select best month**: Choose month with highest ticker count
4. **Filter tickers**: Only use tickers with news in that period
5. **Set date range**: Use the best month's start/end dates

## How to Pivot Later

### Option 1: Use Intersection (Common Period)
```python
USE_BEST_COVERAGE = False
# Then implement intersection logic:
# news_data_start = max(all starts)
# news_data_end = min(all ends)
```

### Option 2: Per-Ticker Date Ranges
```python
# Don't filter TICKERS list
# In backtest loop, check each ticker's date range individually
# Skip tickers without news for that specific date
```

### Option 3: Multi-Period Backtesting
```python
# Run separate backtests for each month
# Aggregate results across periods
```

## Current Behavior

- **Finds best month**: e.g., "2022-11" with 40+ tickers
- **Sets range**: 2022-11-01 to 2022-11-30
- **Filters TICKERS**: Only tickers with news in Nov 2022
- **Verifies**: Shows sample ticker coverage counts

## Expected Outcome

- Clean date range (single month)
- 40+ tickers with actual news coverage
- No more "No articles in range" errors
- All selected tickers have news for the backtest period

## Trade-offs

**Pros:**
- High coverage rate
- No gaps in news data
- Fast iteration
- Reliable results

**Cons:**
- Limited to one month period
- Excludes tickers without news in that month
- May miss longer-term trends

**Future Enhancement:**
- Support multi-month periods
- Weighted coverage (more articles = higher weight)
- Per-ticker date range support
