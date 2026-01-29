# Universe Selection Issue - Analysis

**Date:** 2026-01-25  
**Issue:** System selects stocks alphabetically instead of by supply chain relevance

---

## Problem

The system is currently:
1. ✅ Loading stocks from data directories
2. ✅ Filtering by basic criteria (price, data points, news coverage)
3. ❌ **Selecting first 15 alphabetically** (A, AAL, AAOI, etc.)
4. ❌ **NOT analyzing supply chain relevance**
5. ❌ **NOT ranking by AI supply chain exposure**
6. ❌ **NOT selecting top 15 by supply chain scores**

---

## Current Flow

### 1. Universe Loader (`src/data/universe_loader.py`)
- **Location:** `load_universe()` method (line 321)
- **Selection Logic:** Lines 400-405
  ```python
  if len(with_news) >= max_tickers:
      valid_tickers = with_news[:max_tickers]  # Just takes first N!
  ```
- **Problem:** No ranking, just takes first N alphabetically

### 2. Supply Chain Manager (`test_signals.py`)
- **Location:** Lines 113-133
- **Current:** `auto_research=False` - only checks coverage, doesn't auto-research
- **Problem:** Doesn't analyze stocks for supply chain relevance

### 3. Supply Chain Scanner (`src/signals/supply_chain_scanner.py`)
- **Exists:** `scan_all_tickers()` method can analyze stocks
- **Problem:** **NOT CALLED** during universe selection
- **Capability:** Can calculate `supply_chain_score` for ranking

---

## Desired Flow

1. Load larger pool (e.g., 50 stocks with news coverage)
2. **Analyze all 50 for supply chain relevance** (AI exposure, supplier/customer relationships)
3. **Rank by supply chain scores** (highest AI exposure first)
4. **Select top 15** with highest supply chain scores
5. Use those 15 for backtest

---

## Root Causes

### Issue 1: No Supply Chain Analysis in Selection
- **File:** `src/data/universe_loader.py`
- **Problem:** Universe loader doesn't call supply chain scanner
- **Fix Needed:** Add supply chain analysis step before limiting to top N

### Issue 2: auto_research Disabled
- **File:** `test_signals.py` line 120
- **Problem:** `auto_research=False` prevents automatic research
- **Note:** This is for supply chain **database** (relationships), not for **scoring** stocks

### Issue 3: No Ranking Logic
- **File:** `src/data/universe_loader.py` line 400
- **Problem:** Just takes `[:max_tickers]` without sorting
- **Fix Needed:** Sort by supply chain score before limiting

---

## Solution Approach

### Option 1: Add Supply Chain Ranking to Universe Loader
1. Load larger pool (50 stocks)
2. Call `SupplyChainScanner.scan_all_tickers()` to get scores
3. Rank by `supply_chain_score`
4. Select top 15

### Option 2: Pre-filter with Supply Chain Analysis
1. Create new function: `select_top_supply_chain_stocks(pool_size=50, top_n=15)`
2. Analyze pool_size stocks
3. Return top_n ranked by supply chain scores
4. Call this before universe loading

### Option 3: Two-Stage Selection
1. Stage 1: Load 50 stocks (basic filters)
2. Stage 2: Analyze supply chain relevance
3. Stage 3: Rank and select top 15

---

## Implementation Plan

### Step 1: Create Supply Chain Ranking Function
**File:** `src/data/universe_loader.py` or new `src/data/supply_chain_ranker.py`

```python
def rank_stocks_by_supply_chain(tickers: List[str], top_n: int = 15) -> List[str]:
    """
    Analyze stocks for supply chain relevance and return top N.
    
    Args:
        tickers: List of candidate tickers
        top_n: Number of top stocks to return
        
    Returns:
        List of top N tickers ranked by supply chain score
    """
    from src.signals.supply_chain_scanner import SupplyChainScanner
    
    scanner = SupplyChainScanner()
    df = scanner.scan_all_tickers(tickers, use_cache=True)
    
    # Rank by supply_chain_score
    df_sorted = df.sort_values('supply_chain_score', ascending=False)
    
    return df_sorted['ticker'].head(top_n).tolist()
```

### Step 2: Integrate into Universe Selection
**File:** `src/data/universe_loader.py`

Modify `load_universe()` to:
1. Load larger pool (e.g., 50 stocks)
2. Call ranking function
3. Return top N

### Step 3: Update test_signals.py
- Remove or update the supply chain database check (it's for relationships, not scoring)
- Ensure supply chain scanner is available

---

## Questions to Resolve

1. **Pool Size:** How many stocks should we analyze? (50? 100?)
2. **Caching:** Should we cache supply chain scores to avoid re-analysis?
3. **Performance:** How long does analyzing 50 stocks take? (LLM calls)
4. **Fallback:** What if supply chain analysis fails? Use alphabetical?

---

## Next Steps

1. ✅ Document the issue (this file)
2. ✅ Implement supply chain ranking function
3. ✅ Integrate into universe loader
4. ⏭️ Test with 50 stocks → top 15
5. ✅ Update documentation

---

## Implementation Complete ✅

### Changes Made

1. **Modified `src/data/universe_loader.py`:**
   - Added `rank_by_supply_chain` parameter to `load_universe()`
   - Added `supply_chain_pool_size` parameter (default: 3x max_tickers)
   - Added `_rank_by_supply_chain()` method that:
     - Calls `SupplyChainScanner.scan_all_tickers()` to analyze stocks
     - Ranks by `supply_chain_score` (highest first)
     - Falls back to alphabetical if analysis fails

2. **Modified `test_signals.py`:**
   - Enabled supply chain ranking: `rank_by_supply_chain=True`
   - Set pool size to 3x final size (analyze 45 stocks, select top 15)

### How It Works Now

1. Load all valid tickers (with basic filters)
2. **If `rank_by_supply_chain=True`:**
   - Take larger pool (e.g., 45 stocks with news)
   - Analyze all 45 for supply chain relevance using `SupplyChainScanner`
   - Rank by `supply_chain_score` (highest AI exposure first)
   - Select top 15
3. **If `rank_by_supply_chain=False`:**
   - Use old behavior (alphabetical, first N)

### Performance Notes

- **First Run:** Will analyze 45 stocks (LLM calls) - may take 5-15 minutes
- **Subsequent Runs:** Uses cache from `data/cache/` - much faster
- **Fallback:** If analysis fails, falls back to alphabetical order

### Configuration

Can be controlled via:
- `rank_by_supply_chain` parameter in `load_universe()` call
- `supply_chain_pool_size` parameter (default: 3x max_tickers)
