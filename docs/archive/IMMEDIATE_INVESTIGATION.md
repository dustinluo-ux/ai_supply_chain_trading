# Immediate Investigation: Supply Chain = Sentiment Bug

**Date:** 2026-01-24  
**Status:** CRITICAL BUG CONFIRMED

---

## The Bug

### Location
`src/signals/gemini_news_analyzer.py` line 510

### Current Code (BUGGY)
```python
# Map to our format (backward compatible with existing signal combiner)
scores = {
    'supply_chain_score': float(result.get('supply_chain_health_score', 0.0)),
    'sentiment_score': float(result.get('supply_chain_health_score', 0.0)),  # BUG: Uses same field!
    'confidence': 1.0,
    'relationship': result.get('relationship', 'Neutral'),
    'reasoning': result.get('reasoning', '')
}
```

**Problem:** Both `supply_chain_score` and `sentiment_score` are assigned from `supply_chain_health_score`.

---

## Root Cause

### The LLM Prompt Doesn't Request Sentiment

**Location:** `src/signals/gemini_news_analyzer.py` lines 294-315

**Current Prompt:**
```python
prompt = f"""You are a Supply Chain Quant. For {ticker} on {date}, analyze these articles:

{combined_text}

Extract:
1. Relationship: Supplier/Buyer/Neutral (role of {ticker} in supply chain)
2. Supply Chain Health Score: -1.0 to 1.0 (negative = supply chain disruption, positive = healthy/growing)
3. Reasoning: max 15 words explaining the score

IMPORTANT: Supply Chain Sentiment is Asymmetric:
- For Suppliers (e.g., TSMC): Positive news about raising prices = Neutral for buyers (e.g., Apple)
- For Buyers: Positive news about supplier partnerships = Positive
- Consider the role of {ticker} when scoring

Return ONLY valid JSON with these 3 fields:
{{
  "relationship": "Supplier" | "Buyer" | "Neutral",
  "supply_chain_health_score": -1.0 to 1.0,
  "reasoning": "max 15 words"
}}

Return ONLY the JSON object, nothing else."""
```

**Missing:** The prompt never asks for a separate `sentiment_score` field.

---

## Evidence from Log

From `outputs/backtest_log_20260124_231528.txt`:

```
Week 1: supply_chain=-0.216, sentiment=-0.216  ✅ IDENTICAL
Week 2: supply_chain=0.010, sentiment=0.010   ✅ IDENTICAL
Week 3: supply_chain=0.190, sentiment=0.190   ✅ IDENTICAL
Week 4: supply_chain=-0.401, sentiment=-0.401 ✅ IDENTICAL
```

**All 4 weeks:** Supply chain and sentiment are perfectly identical.

---

## Impact

### Signal Weight Redundancy

**Current Weights (Combined Mode):**
- Supply Chain: 40%
- Sentiment: 30% ← **REDUNDANT** (same as supply chain)
- Momentum: 20%
- Volume: 10%

**Effective Weights:**
- Supply Chain: 70% (40% + 30% redundant)
- Momentum: 20%
- Volume: 10%

**Result:** Sentiment signal provides zero additional information.

---

## Fix Required

### Step 1: Update LLM Prompt

**File:** `src/signals/gemini_news_analyzer.py`  
**Function:** `_create_supply_chain_prompt()`  
**Lines:** 294-315

**Change:**
```python
Extract:
1. Relationship: Supplier/Buyer/Neutral (role of {ticker} in supply chain)
2. Supply Chain Health Score: -1.0 to 1.0 (negative = supply chain disruption, positive = healthy/growing)
3. Sentiment Score: -1.0 to 1.0 (negative = bad news, positive = good news, 0 = neutral)
4. Reasoning: max 15 words explaining the scores

Return ONLY valid JSON with these 4 fields:
{{
  "relationship": "Supplier" | "Buyer" | "Neutral",
  "supply_chain_health_score": -1.0 to 1.0,
  "sentiment_score": -1.0 to 1.0,  # ADD THIS
  "reasoning": "max 15 words"
}}
```

### Step 2: Fix Score Assignment

**File:** `src/signals/gemini_news_analyzer.py`  
**Function:** `analyze_news_for_ticker()`  
**Line:** 510

**Change:**
```python
# Current (BUGGY):
'sentiment_score': float(result.get('supply_chain_health_score', 0.0)),  # Use health score as sentiment

# Fixed:
'sentiment_score': float(result.get('sentiment_score', 0.0)),  # Parse actual sentiment from LLM
```

### Step 3: Handle List Responses

**File:** `src/signals/gemini_news_analyzer.py`  
**Function:** `analyze_news_for_ticker()`  
**Lines:** 447-475 (list response handling)

**Update:** Ensure list response handling also extracts `sentiment_score` separately:

```python
if isinstance(result, list):
    # ... existing code ...
    sentiment_scores = [r.get('sentiment_score', 0) for r in result if isinstance(r, dict)]
    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0
    
    # ... combine into single result ...
    result = {
        'relationship': most_common_relationship,
        'supply_chain_health_score': avg_score,
        'sentiment_score': avg_sentiment,  # ADD THIS
        'reasoning': combined_reasoning
    }
```

---

## Verification

After fix, verify:

1. **Log Check:** Run backtest and check log for:
   ```
   supply_chain=-0.216, sentiment=0.150  ← Should be DIFFERENT
   ```

2. **Code Check:** Verify `sentiment_score` is parsed from `result.get('sentiment_score')` not `supply_chain_health_score`

3. **Distribution Check:** Run `scripts/validate_data.py` and verify:
   - Supply chain and sentiment scores are NOT identical
   - Both have good variance
   - Correlation < 1.0

---

## Related Issues

This bug also affects:
- **List response handling:** Lines 447-475 need to extract sentiment separately
- **Batch aggregation:** Lines 490-504 need to average sentiment separately
- **Caching:** Cached results will have the bug until cache is cleared

**Recommendation:** Clear cache after fix:
```bash
rm -rf data/cache/*.json
```

---

**Status:** Ready to fix  
**Priority:** CRITICAL  
**Estimated Fix Time:** 15 minutes
