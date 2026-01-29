# Debug Prompt: Why are all signal approaches producing identical results?

## Problem
When running `test_signals.py --universe-size 10`, all three approaches (technical-only, news-only, combined) produce identical Sharpe ratios, indicating the signal combination logic isn't working.

## Investigation Checklist

### 1. Verify Signal Generation Differences
Run with debug output and check:
```python
# In test_signals.py, verify:
- Are technical signals actually different for different tickers?
- Are news signals actually different for different tickers?
- Are combined scores different when weights change?
```

**Check points:**
- Print first 10 rows of `signals_df` for each approach
- Verify `signals_df` has different values across rows (not all identical)
- Check if signal generation is using the correct weights

### 2. Verify Weight Application
```python
# In run_backtest_with_preloaded_data(), check:
- Are weights being modified correctly for each approach?
- Print the actual weights dict being used
- Verify SignalCombiner is receiving different weights
```

**Check points:**
- Technical-only: momentum=0.33, volume=0.33, rsi=0.33, supply_chain=0, sentiment=0
- News-only: momentum=0, volume=0, rsi=0, supply_chain=0.5, sentiment=0.5
- Combined: momentum=0.2, volume=0.1, rsi=0.1, supply_chain=0.4, sentiment=0.3

### 3. Verify Date Overlap
```python
# Check date ranges:
- Signals date range: ?
- Prices date range: ?
- Overlap period: ?
- Are positions being filled in the overlap period?
```

**Check points:**
- If no overlap, backtest should return error (not 0.00 Sharpe)
- If overlap exists, verify positions are filled for overlapping dates
- Check if `mondays` list is filtered to overlap period

### 4. Verify Position Filling
```python
# In run_backtest_with_preloaded_data(), check:
- How many positions are filled?
- Are positions filled on the correct dates?
- Are position values different for each approach?
```

**Check points:**
- `positions_filled` count should be > 0
- Positions should align with signal dates
- Position values should reflect signal weights

### 5. Verify Returns Calculation
```python
# Check returns calculation:
- Are returns non-zero?
- Are returns different for each approach?
- Is portfolio_returns calculated correctly?
```

**Check points:**
- `returns_df` should have non-zero values
- `portfolio_returns` should vary by approach
- Sharpe ratio calculation should use portfolio_returns

### 6. Check for Data Caching Issues
```python
# Verify data isn't being reused incorrectly:
- Are technical_signals_dict and news_signals_dict being reused?
- Are signals being recalculated or just reused?
- Is the same signals_df being used for all approaches?
```

**Check points:**
- Each approach should generate its own `signals_df`
- Signals should be recalculated with different weights
- No shared state between approaches

## Expected Debug Output

For each approach, you should see:
```
[DEBUG] Weights: {'momentum': 0.33, 'volume': 0.33, 'rsi': 0.33, 'supply_chain': 0.0, 'sentiment': 0.0}
[DEBUG] Sample combined scores: [0.45, 0.52, 0.38, 0.61, 0.43]  # Should vary
[DEBUG] Signals DataFrame shape: (48, 10)
[DEBUG] Non-zero signals: 480
[DEBUG] Positions filled: 480
[DEBUG] Portfolio returns mean: 0.0012, std: 0.0045
[DEBUG] Sharpe ratio: 0.267
```

## Quick Test
Add this to `run_backtest_with_preloaded_data()`:
```python
# After generating signals_df, add:
print(f"  [DEBUG] Approach: {approach_name}")
print(f"  [DEBUG] Weights: {weights}")
print(f"  [DEBUG] Signals sample (first 5 rows, first 5 cols):")
print(signals_df.iloc[:5, :5])
print(f"  [DEBUG] Signals unique values count: {signals_df.nunique().sum()}")
print(f"  [DEBUG] Signals mean: {signals_df.mean().mean():.6f}, std: {signals_df.std().mean():.6f}")
```

If all approaches show identical signals_df values, the issue is in signal generation.
If signals_df values differ but Sharpe ratios are identical, the issue is in position filling or returns calculation.
