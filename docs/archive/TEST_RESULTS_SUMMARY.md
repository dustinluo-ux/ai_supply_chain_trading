# Gemini Ranking Test Results - Summary

**Date:** 2026-01-25  
**Test Duration:** ~8 minutes (timed out on NVDA, but completed all 3 stocks)  
**Status:** ⚠️ **PARTIAL SUCCESS**

---

## FINAL SCORES

| Stock | Score | Expected | Pass/Fail | Supplier | Customer |
|-------|-------|----------|-----------|----------|----------|
| **NVDA** | **0.8347** | >0.8 | ✅ **PASS** | **422** | **371** |
| **AAL** | **0.4972** | <0.3 | ❌ **FAIL** | 0 | 0 |
| **AEM** | **0.4941** | <0.3 | ❌ **FAIL** | 0 | 0 |

---

## KEY FINDINGS

### ✅ What's Working

1. **Gemini Relationship Extraction:**
   - NVDA: Successfully extracted 422 supplier mentions and 371 customer mentions
   - Sample: "Nvidia" → "datacenter" → "GPUs"
   - This proves Gemini is working correctly for actual AI companies!

2. **Gemini Context Understanding:**
   - AAL/AEM: Correctly identified NO supplier/customer relationships (0 mentions)
   - This proves Gemini understands these are NOT AI supply chain companies

### ❌ What's Broken

1. **False Positive "AI-Related" Detection:**
   - AAL: 97.6% articles marked "ai_related" (ticker "AAL" contains "ai")
   - AEM: 70.6% articles marked "ai_related" (generic keyword matches)
   - **Root Cause:** Gemini itself is marking these as "ai_related" even without relationships

2. **Scoring Formula Issue:**
   - Even with 0 relationships (30% weight = 0), false positive AI matches (40% weight) + relevance (20%) + sentiment (10%) = 0.497
   - **Solution Needed:** Require relationships for high scores, or reduce AI keyword weight

---

## VALIDATION RESULTS

**Total Validations:** 3
- ✅ **1 PASS:** NVDA score >0.8 with relationships
- ❌ **2 FAILS:** AAL and AEM scores >0.3 without relationships

**Flags Raised:**
1. AAL (Airlines) scores 0.497 > 0.3: Airlines should not have high AI exposure
2. AEM (Mining) scores 0.494 > 0.3: Mining should not have high AI exposure
3. AAL: No supplier/customer mentions extracted (expected, but flagged)
4. AEM: No supplier/customer mentions extracted (expected, but flagged)

---

## RECOMMENDATION

### ⚠️ **NO-GO** (Need Fix Before Full Backtest)

**Reasons:**
1. ✅ Gemini relationship extraction works perfectly (NVDA: 422/371)
2. ❌ False positive "ai_related" still causing high scores for non-AI companies
3. ❌ Scoring formula doesn't penalize lack of relationships enough

**Required Fixes:**

1. **Post-Process Gemini Results:**
   - If `supplier=null AND customer=null`, set `ai_related=false`
   - This ensures only articles with actual relationships are marked AI-related

2. **Adjust Scoring Formula:**
   - Option A: Require `supplier_mentions > 0 OR customer_mentions > 0` to score > 0.3
   - Option B: Reduce AI keyword weight from 40% to 20%, increase relationship weight to 50%

3. **Improve Gemini Prompt:**
   - Make prompt more strict: "Only mark ai_related=true if article discusses actual AI supply chain relationships"
   - Add example: "Airlines discussing logistics = NOT AI-related"

---

## NEXT STEPS

1. ⏭️ **Fix post-processing** - Set `ai_related=false` if no relationships
2. ⏭️ **Adjust scoring** - Require relationships for high scores
3. ⏭️ **Re-test** - Run test again after fixes
4. ⏭️ **Verify** - AAL and AEM should score <0.3

---

## DETAILED RESULTS

See `docs/TEST_RESULTS_ANALYSIS.md` for complete analysis.

**Output File:** `outputs/gemini_ranking_test_3stocks.json`

---

**Status:** ⚠️ **PARTIAL SUCCESS** - Gemini works, but needs post-processing fix
