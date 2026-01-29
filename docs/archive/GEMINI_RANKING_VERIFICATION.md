# Gemini-Based Supply Chain Ranking - Verification Report

**Date:** 2026-01-25  
**Purpose:** Verify Gemini implementation is correct before clearing cache and re-running backtest

---

## PART 1: Implementation Verification ✅

### 1.1 Code Changes in `src/data/universe_loader.py`

**Location:** Lines 462-500

**Key Code:**
```python
def _rank_by_supply_chain(self, tickers: List[str]) -> List[str]:
    """Rank tickers by supply chain relevance (AI exposure)."""
    try:
        from src.signals.supply_chain_scanner import SupplyChainScanner
        
        print(f"    [INFO] Analyzing {len(tickers)} stocks for supply chain relevance...", flush=True)
        # Use Gemini instead of FinBERT - it can actually extract relationships
        # FinBERT only does sentiment and has false positives (e.g., "AAL" matches "ai")
        scanner = SupplyChainScanner(llm_provider="gemini", llm_model="gemini-2.5-flash-lite")
        df = scanner.scan_all_tickers(tickers, use_cache=True)
        
        # Rank by supply_chain_score (descending)
        df_sorted = df.sort_values('supply_chain_score', ascending=False)
        ranked = df_sorted['ticker'].tolist()
        
        return ranked
```

**✅ VERIFIED:**
- Line 478: Uses `llm_provider="gemini"` (not FinBERT)
- Line 478: Uses `llm_model="gemini-2.5-flash-lite"`
- Line 479: Calls `scan_all_tickers()` which will use Gemini
- Line 486: Ranks by `supply_chain_score` (highest first)

---

### 1.2 Analyzer Initialization in `src/signals/supply_chain_scanner.py`

**Location:** Lines 24-30

**Key Code:**
```python
def __init__(self, llm_provider: str = "finbert", llm_model: str = "ProsusAI/finbert",
             data_dir: str = "data/news", output_dir: str = "data"):
    self.llm_analyzer = LLMAnalyzer(provider=llm_provider, model=llm_model)
    self.data_dir = data_dir
    self.output_dir = output_dir
    os.makedirs(self.output_dir, exist_ok=True)
    logger.info(f"SupplyChainScanner initialized with {llm_provider}")
```

**✅ VERIFIED:**
- Line 26: Passes `llm_provider` to `LLMAnalyzer`
- When `llm_provider="gemini"`, `LLMAnalyzer` will use Gemini (see 1.3)

---

### 1.3 Gemini Extraction in `src/signals/llm_analyzer.py`

**Location:** Lines 201-220

**Key Code:**
```python
def _extract_with_gemini(self, article: Dict) -> Dict:
    """Extract supply chain info using Gemini API"""
    try:
        result = self.gemini_analyzer.analyze_article(article)
        
        # Map Gemini output to our standard format
        return {
            "supplier": result.get("supplier"),  # ✅ Will extract actual suppliers
            "customer": result.get("customer_type"),  # ✅ Will extract customers
            "product": result.get("product"),  # ✅ Will extract products
            "ai_related": result.get("ai_related", False),
            "sentiment": result.get("sentiment", "neutral"),
            "relevance_score": result.get("relevance_score", 0.0),
            "key_mentions": []
        }
    except Exception as e:
        logger.error(f"Error with Gemini analysis: {e}")
        return self._default_extraction()
```

**✅ VERIFIED:**
- Line 204: Calls `gemini_analyzer.analyze_article()` which uses Gemini API
- Lines 210-212: Maps `supplier`, `customer`, `product` (these will be non-None with Gemini)
- **CRITICAL:** Unlike FinBERT, Gemini actually extracts relationships!

---

### 1.4 Scoring Formula in `src/signals/supply_chain_scanner.py`

**Location:** Lines 149-194

**Formula:**
```python
def calculate_supply_chain_score(self, aggregated: Dict) -> float:
    # 1. AI score (40% weight)
    ai_score = min(aggregated['ai_related_count'] / 10.0, 1.0)
    
    # 2. Mention score (30% weight) - NOW WORKS WITH GEMINI!
    mention_score = (
        aggregated['supplier_mentions'] * 0.4 +  # ✅ Will be >0 with Gemini
        aggregated['customer_mentions'] * 0.3 +  # ✅ Will be >0 with Gemini
        aggregated['product_mentions'] * 0.3     # ✅ Will be >0 with Gemini
    ) / max(aggregated['total_articles'], 1)
    
    # 3. Relevance weight (20% weight)
    relevance_weight = aggregated['avg_relevance_score']
    
    # 4. Sentiment ratio (10% weight)
    sentiment_ratio = aggregated['positive_sentiment_count'] / total_sentiment
    
    # Final score
    score = (
        ai_score * 0.4 +
        mention_score * 0.3 +  # ✅ NOW NON-ZERO with Gemini!
        relevance_weight * 0.2 +
        sentiment_ratio * 0.1
    )
    
    return min(score, 1.0)
```

**✅ VERIFIED:**
- Formula unchanged (still 40% AI, 30% mentions, 20% relevance, 10% sentiment)
- **KEY DIFFERENCE:** `mention_score` will now be >0 because Gemini extracts relationships
- This restores the 30% weight that was lost with FinBERT

---

## PART 2: Cache Files to Clear

### 2.1 Supply Chain Scores CSV

**File:** `data/supply_chain_mentions.csv`
- **Last Modified:** Today (from previous FinBERT run)
- **Content:** Contains old FinBERT-based scores with false positives
- **Action:** ✅ **MUST DELETE** - Contains old scores (AAL=0.497, AEM=0.494, etc.)

**Sample Content:**
```
ticker,supply_chain_score,ai_related_count,total_articles,supplier_mentions,customer_mentions,...
AAL,0.497189,162,166,0,0,...
AEM,0.494118,24,34,0,0,...
```

**Problem:** All `supplier_mentions=0, customer_mentions=0` (FinBERT couldn't extract)

---

### 2.2 Extraction Cache Files

**Files:** `data/*_extractions.json` (45 files found)

**Last Modified:** Today (2026-01-25, 1:39 PM - 2:25 PM)

**Key Files for Test Stocks:**
- `data/AAL_extractions.json` - Last modified: 1:42 PM
- `data/AEM_extractions.json` - Last modified: 2:24 PM
- `data/NVDA_extractions.json` - (Not found in list, may not exist yet)

**Action:** ✅ **MUST DELETE** - Contains old FinBERT extractions with:
- `supplier: None`
- `customer: None`
- `product: None`
- False positive `ai_related: True` (e.g., "AAL" contains "ai")

**Sample Old Format (FinBERT):**
```json
{
  "supplier": null,
  "customer": null,
  "product": null,
  "ai_related": true,  // False positive from "AAL" containing "ai"
  "sentiment": "positive",
  "relevance_score": 0.33
}
```

**Expected New Format (Gemini):**
```json
{
  "supplier": "TSMC",
  "customer_type": "hyperscaler",
  "product": "GPUs",
  "ai_related": true,
  "sentiment": "positive",
  "relevance_score": 0.85
}
```

---

### 2.3 Complete Cache File List

**All files to delete:**

1. ✅ `data/supply_chain_mentions.csv` - Main scores file
2. ✅ `data/AAL_extractions.json` - American Airlines
3. ✅ `data/AEM_extractions.json` - Agnico Eagle Mines
4. ✅ `data/ADM_extractions.json` - Archer Daniels Midland
5. ✅ `data/A_extractions.json` - Agilent Technologies
6. ✅ `data/ACLS_extractions.json` - Axcelis Technologies
7. ✅ `data/*_extractions.json` - All 45 extraction files (from FinBERT run)

**Note:** Files in `data/cache/gemini_*.json` are for news analysis (different system), NOT for supply chain ranking, so they can stay.

---

## PART 3: Test Script Created ✅

**File:** `scripts/test_gemini_ranking_3stocks.py`

**Test Cases:**
1. **AAL** (American Airlines) - Expected: <0.3
2. **NVDA** (NVIDIA) - Expected: >0.8
3. **AEM** (Agnico Eagle Mines) - Expected: <0.3

**Output:** `outputs/gemini_ranking_test_3stocks.json`

**Features:**
- Shows sample headlines analyzed
- Counts AI-related articles (should be accurate with Gemini)
- Shows supplier/customer relationships extracted
- Calculates final `supply_chain_score`
- Validation flags for suspicious scores
- Ground truth comparison table

---

## PART 4: Validation Checks ✅

**Implemented in test script:**

1. ✅ Industry-based checks:
   - AAL >0.3 → FLAG "Airlines shouldn't be high AI exposure"
   - AEM >0.3 → FLAG "Mining shouldn't be high AI exposure"
   - NVDA <0.7 → FLAG "NVIDIA should be high AI exposure"

2. ✅ Keyword contamination check:
   - Detects if ticker symbol matches keywords (e.g., "AAL" contains "ai")

3. ✅ Relationship extraction check:
   - Warns if `supplier_mentions=0` AND `customer_mentions=0` (should be >0 with Gemini)

---

## PART 5: Ground Truth Table

**Template (to be filled after test run):**

| Company | Ticker | Industry | Expected Score | Actual Score | Pass/Fail | Supplier | Customer |
|---------|--------|----------|----------------|--------------|-----------|----------|----------|
| NVIDIA | NVDA | AI Chips | >0.8 | ??? | ??? | ??? | ??? |
| AMD | AMD | AI Chips | >0.7 | ??? | ??? | ??? | ??? |
| American Airlines | AAL | Airlines | <0.3 | ??? | ??? | ??? | ??? |
| Agnico Eagle Mines | AEM | Mining | <0.3 | ??? | ??? | ??? | ??? |

**Will be generated by test script.**

---

## NEXT STEPS

### Step 1: Run Test Script
```bash
python scripts/test_gemini_ranking_3stocks.py
```

**Expected Output:**
- Detailed analysis of 3 stocks
- Validation flags (should be minimal with Gemini)
- Ground truth table with actual scores
- GO/NO-GO recommendation

### Step 2: Review Test Results

**Check:**
- ✅ AAL score <0.3 (not 0.497)
- ✅ NVDA score >0.8 (high AI exposure)
- ✅ AEM score <0.3 (not 0.494)
- ✅ Supplier/customer mentions >0 (Gemini extracted relationships)
- ✅ No keyword contamination flags

### Step 3: Clear Cache (if tests pass)

**Delete:**
```bash
# Delete main scores file
rm data/supply_chain_mentions.csv

# Delete all extraction files (old FinBERT results)
rm data/*_extractions.json
```

### Step 4: Re-run Full Backtest

```bash
python test_signals.py --universe-size 15 --top-n 10
```

**Expected:**
- System analyzes 45 stocks with Gemini
- Ranks by actual AI supply chain exposure
- Selects top 15 (should be NVDA, AMD, TSM, etc., not AAL, AEM, ADM)

---

## IMPLEMENTATION STATUS

✅ **PART 1:** Implementation verified - Gemini is correctly configured
✅ **PART 2:** Cache files identified - ready to delete after test
✅ **PART 3:** Test script created - ready to run
✅ **PART 4:** Validation checks implemented
✅ **PART 5:** Ground truth table template ready

**READY FOR TESTING** - Run test script to verify before clearing cache.
