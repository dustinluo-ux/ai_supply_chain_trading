# Gemini Ranking Test Results - Analysis

**Date:** 2026-01-25  
**Test File:** `outputs/gemini_ranking_test_3stocks.json`

---

## EXECUTIVE SUMMARY

✅ **NVDA:** PASSED - Score 0.8347 > 0.8, with supplier/customer relationships extracted  
❌ **AAL:** FAILED - Score 0.497 > 0.3, but NO relationships extracted (correctly)  
❌ **AEM:** FAILED - Score 0.494 > 0.3, but NO relationships extracted (correctly)

**Key Finding:** Gemini is working correctly for NVDA (extracted relationships), but AAL and AEM still score high due to false positive "ai_related" keyword matches.

---

## DETAILED RESULTS

### 1. NVDA (NVIDIA) - ✅ PASSED

**Score:** 0.8347 (Expected: >0.8) ✅

**Metrics:**
- Total articles: 464
- AI-related: 392/464 (84.5%)
- **Supplier mentions: 422** ✅ (Gemini extracted!
- **Customer mentions: 371** ✅ (Gemini extracted!)
- Product mentions: 421
- Avg relevance: 0.679
- Supply chain score: 0.8347

**Sample Extractions:**
- Supplier: "Nvidia", Customer: "datacenter", Product: "GPUs"
- Supplier: "Nvidia", Customer: "hyperscaler/AI lab/datacenter", Product: "GPUs, AI software"
- Supplier: "Nvidia Corp", Customer: "hyperscaler/AI lab/datacenter", Product: "GPUs"

**Status:** ✅ **PASS** - Gemini correctly extracted relationships and scored high

---

### 2. AAL (American Airlines) - ❌ FAILED

**Score:** 0.4972 (Expected: <0.3) ❌

**Metrics:**
- Total articles: 166
- AI-related: 162/166 (97.6%) ⚠️ **FALSE POSITIVE**
- **Supplier mentions: 0** (Correct - no AI supply chain)
- **Customer mentions: 0** (Correct - no AI supply chain)
- Product mentions: 0
- Avg relevance: 0.329
- Supply chain score: 0.4972

**Sample Extractions:**
- All have: `supplier: null, customer: null, product: null`
- All marked: `ai_related: true` ⚠️ (False positive from "AAL" containing "ai")

**Problem:** 
- Gemini correctly did NOT extract relationships (good!)
- But 97.6% articles still marked "ai_related" (false positive)
- Score breakdown: 40% AI (false positive) + 20% relevance + 10% sentiment = 0.497

**Status:** ❌ **FAIL** - Score too high due to false positive keyword matching

---

### 3. AEM (Agnico Eagle Mines) - ❌ FAILED

**Score:** 0.4941 (Expected: <0.3) ❌

**Metrics:**
- Total articles: 34
- AI-related: 24/34 (70.6%) ⚠️ **FALSE POSITIVE**
- **Supplier mentions: 0** (Correct - no AI supply chain)
- **Customer mentions: 0** (Correct - no AI supply chain)
- Product mentions: 0
- Avg relevance: 0.235
- Supply chain score: 0.4941

**Sample Extractions:**
- All have: `supplier: null, customer: null, product: null`
- All marked: `ai_related: true` ⚠️ (False positive from generic keywords)

**Problem:**
- Gemini correctly did NOT extract relationships (good!)
- But 70.6% articles still marked "ai_related" (false positive)
- Score breakdown: 40% AI (false positive) + 20% relevance + 10% sentiment = 0.494

**Status:** ❌ **FAIL** - Score too high due to false positive keyword matching

---

## VALIDATION FLAGS

**Total Flags:** 4
- ✅ 1 Pass (NVDA)
- ❌ 2 Fails (AAL, AEM)
- ⚠️ 2 Warnings (No relationships for AAL/AEM - expected, but flagged)

**Issues:**
1. AAL scores 0.497 > 0.3 (should be <0.3)
2. AEM scores 0.494 > 0.3 (should be <0.3)

---

## GROUND TRUTH TABLE

| Company | Ticker | Industry | Expected | Actual | Pass/Fail | Supplier | Customer |
|---------|--------|----------|----------|--------|-----------|----------|----------|
| NVIDIA | NVDA | AI Chips | >0.8 | **0.8347** | ✅ **PASS** | **422** | **371** |
| American Airlines | AAL | Airlines | <0.3 | **0.4972** | ❌ **FAIL** | 0 | 0 |
| Agnico Eagle Mines | AEM | Mining | <0.3 | **0.4941** | ❌ **FAIL** | 0 | 0 |

---

## ROOT CAUSE ANALYSIS

### What's Working ✅

1. **Gemini Relationship Extraction:** 
   - NVDA: 422 supplier mentions, 371 customer mentions ✅
   - AAL/AEM: 0 mentions (correctly - no relationships exist) ✅

2. **Gemini Context Understanding:**
   - NVDA correctly identified as AI supply chain company
   - AAL/AEM correctly identified as having NO relationships

### What's Broken ❌

1. **False Positive "AI-Related" Flagging:**
   - AAL: 97.6% false positive (ticker "AAL" contains "ai")
   - AEM: 70.6% false positive (generic "supply chain" keyword)

2. **Scoring Formula Issue:**
   - Even with 0 supplier/customer mentions (30% weight = 0)
   - 40% AI score (false positive) + 20% relevance + 10% sentiment = 0.497
   - Should require relationships to score high!

---

## RECOMMENDATION

### ⚠️ **NO-GO** (Need Fix)

**Reasons:**
1. ✅ Gemini relationship extraction works (NVDA has 422/371 mentions)
2. ❌ False positive keyword matching still causing high scores for non-AI companies
3. ❌ Scoring formula doesn't penalize lack of relationships enough

**Required Fixes:**

1. **Improve "ai_related" Detection:**
   - Remove ticker symbol contamination (e.g., "AAL" contains "ai")
   - Require word boundaries for "ai" keyword
   - Require AI-specific context (not just generic "supply chain")

2. **Adjust Scoring Formula:**
   - Require minimum supplier OR customer mentions > 0 to score > 0.3
   - Or: Reduce AI keyword weight from 40% to 20%, increase relationship weight to 50%

3. **Use Gemini's "ai_related" Field:**
   - Gemini already returns `ai_related` field - use that instead of keyword matching
   - Check if Gemini's `ai_related` is more accurate than keyword matching

---

## NEXT STEPS

1. ⏭️ **Fix keyword matching** - Remove ticker contamination, require word boundaries
2. ⏭️ **Adjust scoring** - Require relationships for high scores
3. ⏭️ **Re-test** - Run test again after fixes
4. ⏭️ **Verify** - AAL and AEM should score <0.3

---

**Status:** ⚠️ **PARTIAL SUCCESS** - Gemini works, but keyword matching needs fix
