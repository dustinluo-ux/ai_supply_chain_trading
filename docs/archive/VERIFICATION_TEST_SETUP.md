# Fast Verification Test Setup

## Configuration

**Ultra-Minimal Settings:**
```python
DEBUG_MODE = True
DEBUG_STOCKS = ['AAPL']  # Just 1 stock
DEBUG_START_DATE = None  # Use auto-detected aligned date range
DEBUG_END_DATE = None    # Use auto-detected aligned date range
MAX_WEEKLY_ITERATIONS = 1  # Just 1 week
```

## Expected Behavior

1. **Loads 1 stock**: AAPL
2. **Detects price data**: 2023-2024
3. **Scans all news files**: Finds best aligned month (likely 2023-04)
4. **Uses aligned period**: April 2023 (2023-04-01 to 2023-04-30)
5. **Processes 1 week**: First Monday in April 2023
6. **Gets news score**: Should return actual LLM analysis (not None)

## Success Criteria

✅ **Alignment works:**
- Detects 2023-04 as best aligned month
- Uses April 2023 date range

✅ **News analysis works:**
- Successfully loads AAPL news for April 2023
- Calls Gemini API
- Returns non-None score with supply chain analysis

✅ **Output shows:**
```
[OK] Using overlapping date range: 2023-04-01 to 2023-04-30
[ITERATION 1] Processing AAPL on 2023-04-03
[SUCCESS] AAPL got news score: supply_chain=0.X, sentiment=0.X
```

## Next Steps After Verification

### If Successful:
1. **Scale to 5 stocks:**
   ```python
   DEBUG_STOCKS = ['AAPL', 'NVDA', 'AMD', 'MSFT', 'TSLA']
   MAX_WEEKLY_ITERATIONS = 4  # 1 month
   ```

2. **Then full production:**
   ```python
   DEBUG_MODE = False  # Full 26+ tickers, full month
   ```

### If Fails:
- Check alignment output
- Verify AAPL has news in April 2023
- Check Gemini API connectivity
- Review error messages

## Files Modified

- `test_signals.py` lines 24-28: Updated DEBUG_MODE settings
- `test_signals.py` lines 546-555: Updated date range override logic
