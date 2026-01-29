# Supply Chain Relationship Verification Checklist

**Purpose:** Manual verification guide for automatically extracted relationships

---

## Confidence Levels

### High-Confidence (No verification needed)
- ✅ From Apple's official supplier list
- ✅ Explicitly named in 10-K (not "Customer A")
- ✅ Confirmed in 2+ independent sources
- ✅ Known industry relationships (e.g., NVDA vs AMD competitors)

**Action:** Accept as-is, mark `needs_verification: false`

---

### Medium-Confidence (Quick verification)
- ⚠️ Deduced from concentration % → Google "[Supplier] largest customer"
- ⚠️ From single news source → Find one more source
- ⚠️ From 10-K but customer not named → Research industry reports

**Action:** 
1. Quick Google search: "[Supplier ticker] largest customer"
2. Check Bloomberg/Reuters articles
3. If confirmed, mark `needs_verification: false`
4. If unclear, mark `needs_verification: true` with notes

---

### Low-Confidence (Full verification needed)
- ❌ LLM-generated → Don't trust, research manually
- ❌ Unclear from 10-K → Need industry reports
- ❌ Customer name "UNKNOWN" → Must research
- ❌ Single source, no confirmation

**Action:**
1. Research using multiple sources:
   - Company 10-K filings
   - Industry reports (Gartner, IDC, etc.)
   - News articles (Bloomberg, Reuters, WSJ)
   - Company investor relations pages
2. Document findings in `verification_notes`
3. Update `confidence` level based on findings
4. Mark `needs_verification: false` only if confirmed

---

## Verification Process

### Step 1: Review Database
```bash
# Open the database
cat data/supply_chain_relationships.json | jq '.relationships | keys'
```

### Step 2: Identify Relationships Needing Verification
```bash
# Find all relationships that need verification
cat data/supply_chain_relationships.json | jq '.relationships[].suppliers[]? | select(.needs_verification == true)'
cat data/supply_chain_relationships.json | jq '.relationships[].customers[]? | select(.needs_verification == true)'
```

### Step 3: Research Each Relationship

**For Supplier Relationships:**
1. Check if supplier is in Apple's official list (if for AAPL)
2. Search: "[Company] supplies [Product] to [Customer]"
3. Check supplier's 10-K for customer mentions
4. Verify product/service matches

**For Customer Relationships:**
1. If customer is "UNKNOWN" from 10-K:
   - Search: "[Supplier] largest customer"
   - Check supplier's investor presentations
   - Review industry reports
2. If customer is named:
   - Verify ticker is correct
   - Check if relationship is current (not historical)
   - Verify percentage matches 10-K disclosure

**For Competitor Relationships:**
1. Usually high confidence (known industry relationships)
2. Verify if needed: "[Company A] vs [Company B] competitors"

### Step 4: Update Database

After verification, update the relationship entry:

```json
{
  "ticker": "TSM",
  "name": "Taiwan Semiconductor",
  "confidence": "high",  // Updated from "low"
  "needs_verification": false,  // Updated from true
  "verification_notes": "Confirmed in Apple Supplier List 2024 and TSMC 10-K",
  "verified_date": "2026-01-25",
  "verified_by": "Manual research"
}
```

---

## Common Issues & Solutions

### Issue 1: Customer Name Not Disclosed
**Problem:** 10-K says "Customer A accounted for 20% of revenue" but doesn't name them.

**Solution:**
1. Search: "[Supplier] 20% customer"
2. Check supplier's investor relations presentations (often name major customers)
3. Review industry reports
4. Check news articles about supplier partnerships
5. If still unknown, mark as `ticker: "UNKNOWN"` and add research notes

### Issue 2: Ticker Format Mismatch
**Problem:** Company name found but ticker doesn't match (e.g., "Intel" vs "INTC")

**Solution:**
1. Use ticker lookup: https://www.sec.gov/cgi-bin/browse-edgar?company=
2. Verify on Yahoo Finance or Bloomberg
3. Update ticker in database

### Issue 3: Historical vs Current Relationship
**Problem:** Relationship found in old 10-K but may no longer be current.

**Solution:**
1. Check most recent 10-K
2. Search recent news for relationship changes
3. Add `last_verified_date` field
4. Mark as `needs_verification: true` if >2 years old

### Issue 4: Indirect vs Direct Relationship
**Problem:** Company A supplies to Company B, but B is not a direct customer (e.g., through distributor).

**Solution:**
1. Clarify relationship type in `relationship_type` field
2. Add note: "Indirect relationship through [Distributor]"
3. Lower confidence if indirect

---

## Verification Sources

### Primary Sources (Highest Confidence)
1. **SEC 10-K Filings** - Official company disclosures
2. **Company Investor Relations** - Presentations, earnings calls
3. **Apple Supplier List** - Official annual report
4. **Company Annual Reports** - Non-US companies

### Secondary Sources (Medium Confidence)
1. **Bloomberg Terminal** - Supply chain data
2. **Reuters** - Industry news
3. **WSJ** - Business news
4. **Industry Reports** - Gartner, IDC, etc.

### Tertiary Sources (Low Confidence - Use for Validation Only)
1. **Wikipedia** - May be outdated
2. **General News** - May be inaccurate
3. **LLM Responses** - As shown in test, only 32.7% accurate

---

## Database Schema

Each relationship entry should have:

```json
{
  "ticker": "TSM",                    // Stock ticker (or "UNKNOWN")
  "name": "Taiwan Semiconductor",     // Company name
  "supplies": "Chips/Foundry",       // What they supply (for suppliers)
  "concentration_pct": 20,           // % of revenue (for customers)
  "confidence": "high",               // high | medium | low
  "source": "Apple Supplier List",    // Where relationship was found
  "last_verified": "2026-01",         // Date last verified
  "needs_verification": false,        // true if needs manual check
  "verification_notes": "",          // Notes from verification
  "verified_date": "2026-01-25",     // When verified
  "verified_by": "Manual research"    // Who/what verified it
}
```

---

## Quick Reference

**High Confidence → Accept**
- Apple supplier list
- Named in 10-K
- 2+ sources confirm

**Medium Confidence → Quick Check**
- Google search
- One news article
- Verify ticker

**Low Confidence → Full Research**
- Unknown customer
- LLM-generated
- Single unclear source

---

**Last Updated:** 2026-01-25
