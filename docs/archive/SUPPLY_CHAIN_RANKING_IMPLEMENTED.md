# Supply Chain Ranking Implementation

**Date:** 2026-01-25  
**Status:** ✅ Implemented

---

## Problem Solved

**Before:** System selected stocks alphabetically (A, AAL, AAOI, etc.) without analyzing supply chain relevance.

**After:** System now:
1. Analyzes a larger pool of stocks (e.g., 45 stocks) for supply chain relevance
2. Ranks them by AI supply chain exposure score
3. Selects top 15 with highest supply chain scores

---

## Implementation Details

### Files Modified

1. **`src/data/universe_loader.py`**
   - Added `rank_by_supply_chain` parameter to `load_universe()`
   - Added `supply_chain_pool_size` parameter (default: 3x max_tickers)
   - Added `_rank_by_supply_chain()` method that:
     - Uses `SupplyChainScanner` to analyze stocks
     - Ranks by `supply_chain_score` (highest first)
     - Falls back to alphabetical if analysis fails

2. **`test_signals.py`**
   - Enabled supply chain ranking: `rank_by_supply_chain=True`
   - Set pool size: `supply_chain_pool_size=args.universe_size * 3`

### How It Works

```python
# In test_signals.py
ticker_metadata = universe_loader.load_universe(
    max_tickers=15,  # Final selection: top 15
    rank_by_supply_chain=True,  # Enable ranking
    supply_chain_pool_size=45  # Analyze 45 stocks, select top 15
)
```

**Process:**
1. Load all valid tickers (with basic filters: price, data points, news)
2. Take larger pool (45 stocks with news coverage)
3. Analyze all 45 using `SupplyChainScanner.scan_all_tickers()`
4. Calculate `supply_chain_score` for each stock
5. Rank by score (highest AI exposure first)
6. Select top 15

---

## Supply Chain Scoring

The `SupplyChainScanner` calculates scores based on:
- **AI-related mentions** (40% weight)
- **Supply chain mentions** (30% weight)
- **Relevance weight** (20% weight)
- **Sentiment ratio** (10% weight)

**Score Range:** 0.0 to 1.0 (higher = more AI supply chain exposure)

---

## Performance

### First Run
- **Time:** 5-15 minutes (depends on number of stocks analyzed)
- **API Calls:** LLM calls for each stock's news articles
- **Output:** Cached results in `data/cache/` and `data/supply_chain_mentions.csv`

### Subsequent Runs
- **Time:** < 1 minute (uses cache)
- **No API Calls:** Uses cached analysis results

### Fallback
- If analysis fails or no scores generated, falls back to alphabetical order
- Logs warning but continues execution

---

## Configuration

### Enable/Disable Ranking

```python
# Enable (default in test_signals.py)
ticker_metadata = universe_loader.load_universe(
    max_tickers=15,
    rank_by_supply_chain=True
)

# Disable (old behavior)
ticker_metadata = universe_loader.load_universe(
    max_tickers=15,
    rank_by_supply_chain=False  # Alphabetical selection
)
```

### Adjust Pool Size

```python
# Analyze 50 stocks, select top 15
ticker_metadata = universe_loader.load_universe(
    max_tickers=15,
    rank_by_supply_chain=True,
    supply_chain_pool_size=50
)
```

---

## Example Output

**Before (Alphabetical):**
```
Selected: ['A', 'AAL', 'AAOI', 'AAON', 'AAP', 'AAPL', 'AAT', 'AB', 'ABBV', 'ABC', 'ABCB', 'ABG', 'ABM', 'ABR', 'ABT']
```

**After (Ranked by Supply Chain):**
```
[INFO] Analyzing 45 stocks for supply chain relevance...
[INFO] Top 5 by supply chain score: ['NVDA', 'AMD', 'TSM', 'AAPL', 'MSFT']
Selected: ['NVDA', 'AMD', 'TSM', 'AAPL', 'MSFT', ...] (top 15 by score)
```

---

## Dependencies

- `SupplyChainScanner` from `src/signals/supply_chain_scanner.py`
- `LLMAnalyzer` (defaults to FinBERT, can use Gemini)
- News data files in `data/news/{ticker}_news.json`

---

## Testing

To test the implementation:

```bash
python test_signals.py --universe-size 15 --top-n 10
```

**Expected Behavior:**
1. Loads larger pool (45 stocks)
2. Analyzes supply chain relevance
3. Ranks and selects top 15
4. Logs: `[INFO] Selected top 15 stocks by supply chain relevance`

**Check Logs For:**
- `[INFO] Ranking stocks by supply chain relevance (analyzing X stocks)...`
- `[INFO] Top 5 by supply chain score: [...]`
- `[INFO] Selected top 15 stocks by supply chain relevance`

---

## Troubleshooting

### Issue: Analysis takes too long
**Solution:** Reduce `supply_chain_pool_size` or disable ranking for faster runs

### Issue: No scores generated
**Solution:** Check that news files exist in `data/news/` for analyzed stocks

### Issue: Falls back to alphabetical
**Solution:** Check logs for error messages from `SupplyChainScanner`

---

## Next Steps

1. ✅ Implementation complete
2. ⏭️ Test with actual run
3. ⏭️ Verify top stocks are actually high AI supply chain exposure
4. ⏭️ Adjust scoring weights if needed
5. ⏭️ Add configuration option to `data_config.yaml`

---

**Status:** ✅ **READY FOR TESTING**
