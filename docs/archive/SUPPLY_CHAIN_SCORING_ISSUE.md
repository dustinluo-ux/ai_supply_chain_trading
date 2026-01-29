# Supply Chain Scoring Issue - Analysis

**Date:** 2026-01-25  
**Issue:** Non-AI companies (AAL, AEM, ADM) ranking higher than actual AI companies

---

## Problem Identified

The `SupplyChainScanner` is using **FinBERT** by default, which:
1. ❌ Only does sentiment analysis (not supply chain extraction)
2. ❌ Uses basic keyword matching for AI detection
3. ❌ Returns `supplier=None, customer=None, product=None` (no relationship extraction)
4. ❌ Keyword "supply chain" is too generic (matches logistics, not AI supply chain)

---

## Scoring Formula Analysis

**Location:** `src/signals/supply_chain_scanner.py` lines 149-194

```python
def calculate_supply_chain_score(self, aggregated: Dict) -> float:
    # 1. AI score (40% weight)
    ai_score = min(aggregated['ai_related_count'] / 10.0, 1.0)
    
    # 2. Mention score (30% weight) - PROBLEM: Always 0 with FinBERT!
    mention_score = (
        aggregated['supplier_mentions'] * 0.4 +  # Always 0 (FinBERT returns None)
        aggregated['customer_mentions'] * 0.3 +  # Always 0
        aggregated['product_mentions'] * 0.3    # Always 0
    ) / max(aggregated['total_articles'], 1)
    
    # 3. Relevance weight (20% weight)
    relevance_weight = aggregated['avg_relevance_score']
    
    # 4. Sentiment ratio (10% weight)
    sentiment_ratio = positive_count / total_sentiment
    
    # Final score
    score = (
        ai_score * 0.4 +
        mention_score * 0.3 +  # This is always 0!
        relevance_weight * 0.2 +
        sentiment_ratio * 0.1
    )
```

**Problem:** Since `mention_score = 0` (FinBERT doesn't extract relationships), the score is:
- 40% AI keyword matches
- 20% Relevance (also keyword-based)
- 10% Positive sentiment
- 30% Lost (mention_score = 0)

---

## Keyword Matching Logic

**Location:** `src/signals/llm_analyzer.py` lines 152-154

```python
ai_keywords = ['ai', 'artificial intelligence', 'gpu', 'semiconductor', 'datacenter', 'supply chain']
ai_related = any(keyword in text_lower for keyword in ai_keywords)
```

**CRITICAL ISSUE:** The keyword **"supply chain"** is too generic!
- Airlines have "supply chain" news (logistics, fuel supply chain)
- Gold mining has "supply chain" news (mining supply chain)
- Agriculture has "supply chain" news (food supply chain)

These are NOT AI supply chain, but they match the keyword!

---

## Why Non-AI Companies Score High

1. **High article volume** → More chances to match keywords
2. **"Supply chain" keyword matches** → Generic logistics news triggers `ai_related=True`
3. **Positive sentiment** → Gets 10% boost
4. **No relationship extraction** → Can't filter out non-AI supply chain news

---

## Solution Options

### Option 1: Use Gemini Instead of FinBERT (RECOMMENDED)
- Gemini can actually extract supply chain relationships
- Can distinguish AI supply chain from generic supply chain
- Better at understanding context

### Option 2: Improve Keyword Matching
- Remove generic "supply chain" keyword
- Require AI-specific context: "AI supply chain", "datacenter supply chain"
- Require multiple keywords (not just one)

### Option 3: Add Industry Filter
- Exclude non-tech industries (airlines, mining, agriculture)
- Use industry classification to filter candidates

### Option 4: Require Supplier/Customer Mentions
- Only score if `supplier_mentions > 0` OR `customer_mentions > 0`
- This would require Gemini (FinBERT can't extract this)

---

## Recommended Fix

**Switch SupplyChainScanner to use Gemini:**

```python
# In src/data/universe_loader.py _rank_by_supply_chain()
scanner = SupplyChainScanner(
    llm_provider="gemini",  # Use Gemini instead of FinBERT
    llm_model="gemini-2.5-flash-lite"
)
```

**Benefits:**
- ✅ Actually extracts supplier/customer relationships
- ✅ Can distinguish AI supply chain from generic supply chain
- ✅ Better relevance scoring
- ✅ `mention_score` will be non-zero

**Trade-offs:**
- ⚠️ Requires API calls (costs tokens)
- ⚠️ Slower than FinBERT (but can cache)

---

## Next Steps

1. ✅ Document the issue (this file)
2. ⏭️ Switch SupplyChainScanner to Gemini
3. ⏭️ Test with same stocks (ACLS, AAL, AEM, A, ADM)
4. ⏭️ Verify AI companies now rank higher
5. ⏭️ Update documentation
