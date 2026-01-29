# Supply Chain Scoring Issue - Complete Analysis

**Date:** 2026-01-25  
**Critical Issue:** Non-AI companies (AAL, AEM, ADM) ranking higher than actual AI companies

---

## 1. Exact Scoring Code

**File:** `src/signals/supply_chain_scanner.py` lines 149-194

```python
def calculate_supply_chain_score(self, aggregated: Dict) -> float:
    if aggregated['total_articles'] == 0:
        return 0.0
    
    # 1. AI score (40% weight) - PROBLEM: False positives from keyword matching
    ai_score = min(aggregated['ai_related_count'] / 10.0, 1.0)
    
    # 2. Mention score (30% weight) - PROBLEM: Always 0 with FinBERT!
    mention_score = (
        aggregated['supplier_mentions'] * 0.4 +  # Always 0 (FinBERT returns None)
        aggregated['customer_mentions'] * 0.3 +  # Always 0
        aggregated['product_mentions'] * 0.3     # Always 0
    ) / max(aggregated['total_articles'], 1)
    
    # 3. Relevance weight (20% weight) - Also keyword-based
    relevance_weight = aggregated['avg_relevance_score']
    
    # 4. Sentiment ratio (10% weight)
    total_sentiment = (
        aggregated['positive_sentiment_count'] +
        aggregated['negative_sentiment_count'] +
        aggregated['neutral_sentiment_count']
    )
    sentiment_ratio = aggregated['positive_sentiment_count'] / total_sentiment if total_sentiment > 0 else 0.5
    
    # Final score
    score = (
        ai_score * 0.4 +
        mention_score * 0.3 +  # THIS IS ALWAYS 0!
        relevance_weight * 0.2 +
        sentiment_ratio * 0.1
    )
    
    return min(score, 1.0)
```

---

## 2. Keyword Matching Logic

**File:** `src/signals/llm_analyzer.py` lines 152-158

```python
# For FinBERT, we can only get sentiment, not supply chain extraction
# So we do basic keyword matching for supply chain relevance
text_lower = text.lower()
ai_keywords = ['ai', 'artificial intelligence', 'gpu', 'semiconductor', 'datacenter', 'supply chain']
ai_related = any(keyword in text_lower for keyword in ai_keywords)

# Simple relevance scoring
keyword_count = sum(1 for keyword in ai_keywords if keyword in text_lower)
relevance_score = min(keyword_count / 3.0, 1.0) if ai_related else 0.0
```

**CRITICAL PROBLEMS:**
1. ❌ Keyword `'ai'` matches "AAL" (ticker symbol) → False positive!
2. ❌ Keyword `'supply chain'` matches generic logistics (airlines, mining, agriculture)
3. ❌ No context checking (doesn't verify if it's actually AI-related)
4. ❌ Single keyword match is enough (`any()` function)

---

## 3. Actual Scores for Problem Stocks

| Ticker | Score | AI-Related | Total Articles | Supplier | Customer | Problem |
|--------|-------|------------|----------------|----------|----------|---------|
| ACLS | 0.498 | 21/37 (56.8%) | 37 | 0 | 0 | False positives from "ai" keyword |
| AAL | 0.497 | 162/166 (97.6%) | 166 | 0 | 0 | **"AAL" contains "ai" → 97% false positive!** |
| AEM | 0.494 | 24/34 (70.6%) | 34 | 0 | 0 | False positives |
| A | 0.493 | 43/70 (61.4%) | 70 | 0 | 0 | False positives |
| ADM | 0.484 | 89/167 (53.3%) | 167 | 0 | 0 | False positives |

**Key Finding:** AAL has 97.6% "AI-related" articles because the ticker symbol "AAL" contains "ai"!

---

## 4. Sample News Headlines

### AAL (American Airlines)
- "American Airlines (AAL) Dips More Than Broader Markets"
  - **Matches:** "AAL" contains "ai" → False positive!
- "Anglo American evaluates shipment plans"
  - **Matches:** "Anglo American" → False positive!

### AEM (Agnico Eagle Mines - Gold Mining)
- "4 Gold Stocks to Watch in a Promising Industry"
  - **Matches:** Generic "supply chain" mentions in mining context

### ADM (Archer Daniels Midland - Agriculture)
- "Are Investors Undervaluing Archer Daniels Midland (ADM) Right Now?"
  - **Matches:** Generic "supply chain" mentions in agriculture context

**None of these are actually AI supply chain news!**

---

## 5. Why Non-AI Companies Score High

1. **Ticker Symbol False Positives:**
   - "AAL" contains "ai" → 97% of articles marked AI-related
   - Simple substring matching without word boundaries

2. **Generic "Supply Chain" Keyword:**
   - Airlines have "supply chain" news (logistics, fuel supply)
   - Mining has "supply chain" news (mining supply chain)
   - Agriculture has "supply chain" news (food supply chain)
   - These are NOT AI supply chain!

3. **No Relationship Extraction:**
   - FinBERT returns `supplier=None, customer=None, product=None`
   - Can't filter out non-AI supply chain news
   - `mention_score` is always 0 (30% of weight lost)

4. **High Article Volume:**
   - More articles = more chances for false positive matches
   - AAL has 166 articles → 162 false positives

---

## 6. Root Cause Summary

**The scoring system is fundamentally broken because:**

1. ❌ **FinBERT can't extract relationships** → `mention_score = 0` (30% weight lost)
2. ❌ **Keyword matching is too simple** → "ai" matches "AAL", "Anglo American", etc.
3. ❌ **No context checking** → "supply chain" matches logistics, not AI supply chain
4. ❌ **Single keyword match** → `any()` means one false positive = entire article marked AI-related

---

## 7. Recommended Fix

### Option 1: Switch to Gemini (RECOMMENDED) ✅

**Why:**
- ✅ Actually extracts supplier/customer relationships
- ✅ Can distinguish AI supply chain from generic supply chain
- ✅ `mention_score` will be non-zero (30% weight restored)
- ✅ Better context understanding

**Implementation:**
```python
# In src/data/universe_loader.py _rank_by_supply_chain()
scanner = SupplyChainScanner(
    llm_provider="gemini",  # Use Gemini instead of FinBERT
    llm_model="gemini-2.5-flash-lite"
)
```

**Trade-offs:**
- ⚠️ Requires API calls (costs tokens, but can cache)
- ⚠️ Slower than FinBERT (but acceptable for ranking)

### Option 2: Improve Keyword Matching

**Changes needed:**
```python
# Remove generic keywords
ai_keywords = [
    'artificial intelligence',  # Full phrase, not just "ai"
    'gpu', 'semiconductor', 
    'datacenter', 'data center',
    # REMOVE: 'supply chain' (too generic)
    # ADD: Require AI context
    'ai supply chain',
    'ai datacenter',
    'ai chip',
    'ai hardware'
]

# Require word boundaries for "ai"
import re
ai_pattern = r'\bai\b'  # Word boundary, not substring
ai_related = bool(re.search(ai_pattern, text_lower, re.IGNORECASE))

# Require multiple keywords (not just one)
if ai_related:
    keyword_count = sum(1 for kw in ai_keywords if kw in text_lower)
    ai_related = keyword_count >= 2  # Require at least 2 matches
```

**Trade-offs:**
- ✅ No API calls needed
- ⚠️ Still can't extract relationships (mention_score still 0)
- ⚠️ Less accurate than Gemini

### Option 3: Add Minimum Threshold

**Require actual relationships:**
```python
# Only score if has supplier/customer mentions
if aggregated['supplier_mentions'] == 0 and aggregated['customer_mentions'] == 0:
    return 0.0  # No relationships = not AI supply chain
```

**Problem:** This requires Gemini (FinBERT can't extract relationships)

---

## 8. Immediate Action Required

**RECOMMENDED:** Switch `SupplyChainScanner` to use Gemini for universe ranking.

**Why this is critical:**
- Current system is selecting wrong stocks (airlines, mining, agriculture)
- These stocks have NO actual AI supply chain exposure
- The ranking is meaningless with current scoring

**Next Steps:**
1. Modify `_rank_by_supply_chain()` to use Gemini
2. Re-run ranking
3. Verify AI companies (NVDA, AMD, TSM, etc.) now rank higher
4. Update documentation

---

**Status:** 🔴 **CRITICAL - SCORING SYSTEM IS BROKEN**
