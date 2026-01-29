# Supply Chain Database

**Last Updated:** 2026-01-25

---

## Overview

The supply chain database (`data/supply_chain_relationships.json`) contains supplier-customer-competitor relationships for stocks. Used for:
1. **Sentiment propagation:** News about one company affects related companies
2. **Universe ranking:** Rank stocks by AI supply chain relevance

---

## Database Structure

### Metadata

```json
{
  "metadata": {
    "last_updated": "2026-01-25",
    "method": "SEC 10-K parsing + Apple supplier list",
    "coverage": "Top 20 AI supply chain stocks",
    "version": "1.0",
    "default_stale_months": 6
  }
}
```

### Relationships

```json
{
  "relationships": {
    "AAPL": {
      "last_verified": "2026-01-25",
      "data_source": "Apple Supplier List 2024",
      "needs_manual_verification": false,
      "suppliers": [
        {
          "ticker": "TSM",
          "name": "Taiwan Semiconductor",
          "supplies": "Chips/Foundry",
          "country": "Taiwan",
          "concentration_pct": 20,
          "confidence": "high",
          "source": "Apple Supplier List 2024",
          "last_verified": "2026-01",
          "needs_verification": false
        }
      ],
      "customers": [],
      "competitors": [
        {
          "ticker": "GOOGL",
          "name": "Google",
          "confidence": "high",
          "source": "Manual research"
        }
      ]
    }
  }
}
```

### Relationship Entry Schema

**Fields:**
- `ticker`: Stock ticker (or "UNKNOWN" if not identified)
- `name`: Company name
- `supplies`: What they supply (for suppliers only)
- `concentration_pct`: % of revenue (for customers only)
- `confidence`: `high` | `medium` | `low`
- `source`: Where relationship was found
- `last_verified`: Date last verified (YYYY-MM-DD or YYYY-MM)
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

### Incremental Expansion

```bash
python scripts/expand_database_core_stocks.py
```

**What it does:**
1. Adds Apple suppliers from official list
2. Adds known competitor relationships
3. Auto-researches missing stocks (reverse lookup, 10-K parsing)
4. Flags stocks needing manual research in `docs/RESEARCH_QUEUE.txt`

**Coverage:** Expands to 20 core AI supply chain stocks

---

## Freshness Tracking

### Staleness Check

**Default:** Data is stale if > 6 months old

**Check:**
```python
from src.data.supply_chain_manager import SupplyChainManager

manager = SupplyChainManager()
is_stale = manager.is_stale("AAPL", max_age_months=6)
```

**Auto-Update:**
```python
coverage_status = manager.ensure_coverage(
    tickers=["AAPL", "NVDA"],
    max_age_months=6,
    auto_research=True  # Auto-download 10-Ks if stale
)
```

**Status Values:**
- `"current"` - Data is fresh
- `"stale"` - Data is > 6 months old
- `"missing"` - Ticker not in database

---

## Incremental Update Workflow

### 1. Check Coverage

**In backtest (`test_signals.py`):**
```python
from src.data.supply_chain_manager import SupplyChainManager

manager = SupplyChainManager()
coverage_status = manager.ensure_coverage(
    TICKERS,
    max_age_months=6,
    auto_research=False  # Don't auto-download during backtest
)

missing = [t for t, s in coverage_status.items() if s in ['missing', 'stale']]
if missing:
    print(f"WARNING: {len(missing)} stocks need supply chain data")
    print("Run: python scripts/expand_database_core_stocks.py")
```

### 2. Expand Database

**Run expansion script:**
```bash
python scripts/expand_database_core_stocks.py
```

**What happens:**
1. Checks which stocks are missing/stale
2. Attempts auto-research (10-K parsing)
3. Adds relationships from Apple supplier list
4. Flags stocks needing manual research

### 3. Manual Research Queue

**File:** `docs/RESEARCH_QUEUE.txt`

**Format:**
```
META - Added 2026-01-25 - Auto-research failed
LRCX - Added 2026-01-25 - Auto-research failed
KLAC - Added 2026-01-25 - Auto-research failed
```

**Process:**
1. Research each ticker manually
2. Add relationships to database
3. Remove from queue

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

### Supply Chain Manager API

```python
from src.data.supply_chain_manager import SupplyChainManager

manager = SupplyChainManager()

# Get suppliers
suppliers = manager.get_suppliers("AAPL")

# Get customers
customers = manager.get_customers("NVDA")

# Get competitors
competitors = manager.get_competitors("MSFT")

# Get all related companies
related = manager.get_related_companies("AAPL")

# Coverage report
report = manager.get_coverage_report()
print(f"Coverage: {report['total_companies']} companies, {report['total_relationships']} relationships")
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
1. Run expansion script to reach 20 core stocks
2. Manually research stocks in `RESEARCH_QUEUE.txt`
3. Add customer relationships from 10-K disclosures

---

## Verification Process

### Confidence Levels

**High Confidence:**
- Apple supplier list (official)
- Named in 10-K (explicit mention)
- 2+ independent sources

**Medium Confidence:**
- Single source
- Deduced from context
- Quick Google check recommended

**Low Confidence:**
- LLM-generated
- Unknown customer ("Customer A")
- Full research needed

### Verification Checklist

1. **Check source:** Is it reliable?
2. **Cross-reference:** Multiple sources agree?
3. **Date check:** Is relationship current?
4. **Context:** Does it make business sense?
5. **Update database:** Mark as verified

---

## Limitations

1. **10-K Downloads:** Require network access and SEC rate limiting (10 req/sec)
2. **Customer Identification:** Many 10-Ks use "Customer A" instead of names
3. **Coverage:** Currently only 5 companies (need to expand to 50+)
4. **Verification:** All relationships should be manually verified
5. **Temporal Tracking:** No tracking of when relationships start/end

---

## Future Enhancements

1. **Automated 10-K Analysis:** Improve customer name deduction
2. **Bloomberg API:** Use structured data sources for higher accuracy
3. **News-Based Discovery:** Extract relationships from news articles
4. **Relationship Strength:** Add relationship strength scores (major vs minor)
5. **Temporal Tracking:** Track when relationships start/end

---

## Research Queue

**File:** `docs/RESEARCH_QUEUE.txt`

**Purpose:** Tracks stocks that need manual research

**Format:**
```
TICKER - Added YYYY-MM-DD - Reason
```

**Process:**
1. Research each ticker
2. Add relationships to database
3. Remove from queue
4. Mark as verified

---

See `docs/DATA.md` for data sources and `docs/SYSTEM_SPEC.md` for system overview.
