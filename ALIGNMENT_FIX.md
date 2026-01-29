# Price and News Data Alignment Fix

## Problem Identified

**MISALIGNMENT DETECTED:**
- **Price data**: 2023-2024 (2023-01-03 to 2024-12-30)
- **Best news coverage**: 2022-12 (32 tickers from sample)
- **Issue**: Best news month is from 2022, but price data is from 2023-2024

## Diagnostic Results

From `verify_price_news_alignment.py`:

### Price Data
- **Years**: 2023, 2024
- **Range**: 2023-01-03 to 2024-12-30
- **Sample tickers**: AMD, NVDA, QLYS, SLAB, SYNA (all have same range)

### News Data (from 100 file sample)
- **Best month**: 2022-12 (32 tickers)
- **2023 months with good coverage**:
  - 2023-04: 26 tickers
  - 2023-05: 24 tickers
  - 2023-07: 22 tickers
  - 2023-03: 20 tickers
- **Year distribution**: 2022 (331 articles), 2023 (157 articles)

## Solution Implemented

**Updated detection logic to prefer months aligned with price data years:**

1. **Extract price data years** from `prices_dict`
2. **Filter months** to only those in price data years
3. **Select best aligned month** (e.g., 2023-04 instead of 2022-12)
4. **Fallback**: If no alignment, use best available month with warning

## Expected Outcome

When running the backtest:
1. System detects price data is from 2023-2024
2. Filters news months to 2023-2024 only
3. Selects best month: **2023-04** (26 tickers from sample, likely 40+ from all files)
4. Uses aligned period: 2023-04-01 to 2023-04-30
5. Only processes tickers with both price data AND news in April 2023

## Files Modified

- `test_signals.py` lines 342-375: Added price data year alignment logic
- `scripts/verify_price_news_alignment.py`: Diagnostic script created

## Next Steps

1. Run backtest - it should now use 2023-04 (or best 2023 month)
2. Verify alignment in backtest output
3. If needed, can manually specify month or get additional price data
