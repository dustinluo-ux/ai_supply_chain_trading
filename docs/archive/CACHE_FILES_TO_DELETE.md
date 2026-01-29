# Cache Files to Delete - Complete List

**Date:** 2026-01-25  
**Purpose:** List all cache files containing old FinBERT-based supply chain scores

---

## Summary

**Total Files:** 46 files
- 1 CSV file (main scores)
- 45 JSON files (extraction cache)

**All files contain:** Old FinBERT extractions with:
- `supplier: null` (FinBERT can't extract)
- `customer: null` (FinBERT can't extract)
- `product: null` (FinBERT can't extract)
- False positive `ai_related: true` (e.g., "AAL" contains "ai")

**Action:** ✅ **DELETE ALL** before re-running with Gemini

---

## File 1: Main Scores CSV

**Path:** `data/supply_chain_mentions.csv`

**Last Modified:** 2026-01-25 (today)

**Sample Content:**
```csv
ticker,supply_chain_score,ai_related_count,total_articles,supplier_mentions,customer_mentions,...
AAL,0.497189,162,166,0,0,...
AEM,0.494118,24,34,0,0,...
```

**Problem:** All scores based on FinBERT (no relationship extraction)

**Action:** ✅ **DELETE**

---

## Files 2-46: Extraction Cache JSON

**Pattern:** `data/{TICKER}_extractions.json`

**Last Modified:** 2026-01-25, 1:39 PM - 2:25 PM

**Complete List:**
1. `data/A_extractions.json` - 1:39 PM
2. `data/AAL_extractions.json` - 1:42 PM
3. `data/AAOI_extractions.json` - 1:42 PM
4. `data/AAON_extractions.json` - 1:42 PM
5. `data/AAP_extractions.json` - 1:43 PM
6. `data/AAPL_extractions.json` - 2:04 PM
7. `data/AAT_extractions.json` - 2:04 PM
8. `data/AB_extractions.json` - 2:04 PM
9. `data/ABBV_extractions.json` - 2:07 PM
10. `data/ABC_extractions.json` - 2:07 PM
11. `data/ABCB_extractions.json` - 2:07 PM
12. `data/ABG_extractions.json` - 2:08 PM
13. `data/ABM_extractions.json` - 2:08 PM
14. `data/ABR_extractions.json` - 2:08 PM
15. `data/ABT_extractions.json` - 2:10 PM
16. `data/ACAD_extractions.json` - 2:11 PM
17. `data/ACGL_extractions.json` - 2:11 PM
18. `data/ACHC_extractions.json` - 2:11 PM
19. `data/ACIW_extractions.json` - 2:12 PM
20. `data/ACLS_extractions.json` - 2:12 PM
21. `data/ACNB_extractions.json` - 2:13 PM
22. `data/ACN_extractions.json` - 2:13 PM
23. `data/ACRE_extractions.json` - 2:14 PM
24. `data/ACRX_extractions.json` - 2:14 PM
25. `data/ACTG_extractions.json` - 2:14 PM
26. `data/ADBE_extractions.json` - 2:16 PM
27. `data/ADC_extractions.json` - 2:17 PM
28. `data/ADI_extractions.json` - 2:18 PM
29. `data/ADMA_extractions.json` - 2:20 PM
30. `data/ADM_extractions.json` - 2:20 PM
31. `data/ADP_extractions.json` - 2:20 PM
32. `data/ADPT_extractions.json` - 2:20 PM
33. `data/ADSK_extractions.json` - 2:21 PM
34. `data/ADTN_extractions.json` - 2:21 PM
35. `data/ADUS_extractions.json` - 2:21 PM
36. `data/ADXS_extractions.json` - 2:21 PM
37. `data/AEE_extractions.json` - 2:22 PM
38. `data/AEHR_extractions.json` - 2:22 PM
39. `data/AEIS_extractions.json` - 2:22 PM
40. `data/AEL_extractions.json` - 2:23 PM
41. `data/AEM_extractions.json` - 2:24 PM
42. `data/AEO_extractions.json` - 2:24 PM
43. `data/AEP_extractions.json` - 2:25 PM
44. `data/AER_extractions.json` - 2:25 PM
45. `data/AEY_extractions.json` - 2:25 PM

**Sample Content (AAL_extractions.json):**
```json
{
  "supplier": null,
  "customer": null,
  "product": null,
  "ai_related": true,  // FALSE POSITIVE - "AAL" contains "ai"
  "sentiment": "negative",
  "relevance_score": 0.333
}
```

**Problem:** All have `supplier=null, customer=null` (FinBERT can't extract)

**Action:** ✅ **DELETE ALL 45 FILES**

---

## Files to KEEP

**DO NOT DELETE:**
- `data/cache/gemini_*.json` - These are for news analysis (different system)
- `data/news/*_news.json` - Source news articles (keep these!)

---

## Delete Command

**Windows PowerShell:**
```powershell
# Delete main scores file
Remove-Item data\supply_chain_mentions.csv -Force

# Delete all extraction files
Remove-Item data\*_extractions.json -Force

# Verify deletion
Get-ChildItem data\*_extractions.json -ErrorAction SilentlyContinue | Measure-Object
# Should return: Count = 0
```

**Linux/Mac:**
```bash
rm data/supply_chain_mentions.csv
rm data/*_extractions.json
```

---

## Verification After Deletion

**Check:**
1. ✅ `data/supply_chain_mentions.csv` does not exist
2. ✅ `data/*_extractions.json` files do not exist (all 45 deleted)
3. ✅ `data/cache/gemini_*.json` still exist (news analysis cache - keep these)

---

**Status:** ✅ **READY TO DELETE** - All 46 files identified
