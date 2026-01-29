# Supply Chain Database Guide

**Purpose:** Guide for building and maintaining the supply chain relationship database

---

## Overview

The supply chain database (`data/supply_chain_relationships.json`) contains supplier-customer-competitor relationships for stocks in our trading universe. This database is used for network propagation (Feature #2) where news about one company affects related companies.

---

## Database Structure

```json
{
  "metadata": {
    "last_updated": "2026-01-25",
    "method": "SEC 10-K parsing + Apple supplier list",
    "coverage": "Top 20 AI supply chain stocks",
    "version": "1.0"
  },
  "relationships": {
    "AAPL": {
      "suppliers": [...],
      "customers": [...],
      "competitors": [...]
    }
  }
}
```

### Relationship Entry Schema

```json
{
  "ticker": "TSM",
  "name": "Taiwan Semiconductor",
  "supplies": "Chips/Foundry",
  "country": "Taiwan",
  "concentration_pct": 20,
  "confidence": "high",
  "source": "Apple Supplier List 2024",
  "last_verified": "2026-01",
  "needs_verification": false,
  "verification_notes": "",
  "verified_date": "2026-01-25",
  "verified_by": "Manual research"
}
```

**Fields:**
- `ticker`: Stock ticker (or "UNKNOWN" if not identified)
- `name`: Company name
- `supplies`: What they supply (for suppliers only)
- `concentration_pct`: % of revenue (for customers only)
- `confidence`: `high` | `medium` | `low`
- `source`: Where relationship was found
- `needs_verification`: `true` if needs manual check
- `verification_notes`: Notes from verification process

---

## Building the Database

### Automated Build

```bash
python scripts/build_supply_chain_db.py
```

**What it does:**
1. Downloads Apple's official supplier list → populates AAPL suppliers (high confidence)
2. Analyzes supplier 10-Ks for customer concentration disclosures
3. Adds known competitor relationships
4. Saves to `data/supply_chain_relationships.json`

**Current Status:**
- ✅ Apple suppliers: 27 relationships (high confidence)
- ⚠️ 10-K analysis: Requires network access (SEC EDGAR API)
- ✅ Competitors: 12 relationships (high confidence)

### Manual Additions

To add relationships manually, edit `data/supply_chain_relationships.json`:

```json
{
  "relationships": {
    "NVDA": {
      "suppliers": [
        {
          "ticker": "TSM",
          "name": "Taiwan Semiconductor",
          "confidence": "high",
          "source": "Manual research",
          "needs_verification": false
        }
      ]
    }
  }
}
```

---

## Verification Process

See `docs/VERIFICATION_CHECKLIST.md` for detailed verification guide.

**Quick Reference:**
- **High Confidence:** Apple list, named in 10-K, 2+ sources → Accept
- **Medium Confidence:** Single source, deduced → Quick Google check
- **Low Confidence:** LLM-generated, unknown customer → Full research needed

---

## Using the Database

### Load Relationships

```python
import json

with open('data/supply_chain_relationships.json') as f:
    db = json.load(f)

# Get AAPL suppliers
aapl_suppliers = db['relationships']['AAPL']['suppliers']
for supplier in aapl_suppliers:
    print(f"{supplier['ticker']}: {supplier['name']}")
```

### Find Related Companies

```python
def get_related_companies(ticker: str, db: dict) -> List[str]:
    """Get all related companies (suppliers, customers, competitors)"""
    if ticker not in db['relationships']:
        return []
    
    rels = db['relationships'][ticker]
    related = []
    
    # Suppliers
    related.extend([s['ticker'] for s in rels.get('suppliers', [])])
    
    # Customers
    related.extend([c['ticker'] for c in rels.get('customers', []) if c['ticker'] != 'UNKNOWN'])
    
    # Competitors
    related.extend([c['ticker'] for c in rels.get('competitors', [])])
    
    return list(set(related))  # Remove duplicates
```

---

## Current Coverage

**Companies in Database:** 5
- AAPL (27 suppliers)
- NVDA, AMD, TSLA, MSFT (competitors only)

**Total Relationships:** 39
- Suppliers: 27 (all high confidence)
- Customers: 0 (10-K analysis requires network)
- Competitors: 12 (all high confidence)

**Next Steps:**
1. Run with network access to download 10-Ks
2. Expand to top 50 stocks in universe
3. Manually verify all relationships
4. Add customer relationships from 10-K disclosures

---

## Limitations

1. **10-K Downloads:** Require network access and SEC rate limiting (10 req/sec)
2. **Customer Identification:** Many 10-Ks use "Customer A" instead of names
3. **Coverage:** Currently only 5 companies (need to expand to 50+)
4. **Verification:** All relationships should be manually verified

---

## Future Enhancements

1. **Automated 10-K Analysis:** Improve customer name deduction
2. **Bloomberg API:** Use structured data sources for higher accuracy
3. **News-Based Discovery:** Extract relationships from news articles
4. **Relationship Strength:** Add relationship strength scores (major vs minor)
5. **Temporal Tracking:** Track when relationships start/end

---

**Last Updated:** 2026-01-25
