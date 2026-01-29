# Incremental Supply Chain Database Implementation

**Date:** 2026-01-25  
**Status:** ✅ Implemented

---

## Overview

The supply chain database now supports intelligent incremental updates with freshness tracking. The database automatically expands as new stocks appear in backtests.

---

## Components

### 1. Supply Chain Manager (`src/data/supply_chain_manager.py`)

**Features:**
- ✅ Checks if stock exists in database
- ✅ Tracks data freshness (default: 6 months)
- ✅ Auto-downloads missing stocks (with 10-K parsing)
- ✅ Updates stale data
- ✅ Incremental growth (adds stocks as needed)
- ✅ Manual research queue for stocks that can't be auto-researched

**Key Methods:**
- `is_covered(ticker)` - Check if ticker exists
- `is_stale(ticker, max_age_months)` - Check if data is stale
- `ensure_coverage(stocks, auto_research=True)` - Ensure all stocks are covered
- `get_suppliers(ticker)` - Get supplier relationships
- `get_customers(ticker)` - Get customer relationships
- `get_competitors(ticker)` - Get competitor relationships
- `get_related_companies(ticker)` - Get all related companies
- `get_coverage_report()` - Generate statistics

### 2. Database Expansion Script (`scripts/expand_database_core_stocks.py`)

**Purpose:** Expand database to 20 core AI supply chain stocks

**What it does:**
1. Adds Apple suppliers from official list
2. Adds known competitor relationships
3. Auto-researches missing stocks (reverse lookup, 10-K parsing)
4. Flags stocks needing manual research

**Usage:**
```bash
python scripts/expand_database_core_stocks.py
```

### 3. Backtest Integration (`test_signals.py`)

**Location:** Lines 108-125

**What it does:**
- Checks supply chain database coverage before backtest
- Warns if stocks are missing or stale
- Suggests running expansion script
- Does NOT auto-download during backtest (avoids delays)

---

## Database Structure

### Metadata
```json
{
  "metadata": {
    "last_updated": "2026-01-25",
    "version": "1.0",
    "default_stale_months": 6
  }
}
```

### Company Entry
```json
{
  "AAPL": {
    "last_verified": "2026-01-25",
    "data_source": "Apple Supplier List 2024",
    "needs_manual_verification": false,
    "suppliers": [...],
    "customers": [...],
    "competitors": [...]
  }
}
```

**Fields:**
- `last_verified`: Date last verified (YYYY-MM-DD or YYYY-MM)
- `data_source`: Where data came from
- `needs_manual_verification`: `true` if needs manual check
- `suppliers`: List of supplier relationships
- `customers`: List of customer relationships
- `competitors`: List of competitor relationships

---

## Current Coverage

**Total Companies:** 14
- AAPL (27 suppliers, high confidence)
- NVDA, AMD, TSLA, MSFT (competitors only)
- QCOM, AVGO, MU, TXN (added via reverse lookup from AAPL)
- TSM, ASML, INTC, GOOGL, AMZN (competitors only)

**Total Relationships:** 55
- Suppliers: 27 (all high confidence)
- Customers: 4 (reverse lookup from suppliers)
- Competitors: 24 (all high confidence)

**Research Queue:** 6 stocks
- META, LRCX, KLAC, AMAT, SNPS, CDNS
- See: `docs/RESEARCH_QUEUE.txt`

---

## Auto-Research Methods

### Method 1: Reverse Lookup
**How it works:**
- If ticker X is a supplier to company Y (already in DB)
- Then X is a customer of Y
- Automatically adds customer relationship

**Example:**
- QCOM is supplier to AAPL (from Apple list)
- Auto-adds: QCOM is customer of AAPL

**Success Rate:** High (for stocks already in database as suppliers)

### Method 2: 10-K Parsing
**How it works:**
- Downloads ticker's latest 10-K from SEC EDGAR
- Extracts customer concentration disclosures
- Extracts supplier mentions
- Adds partial data (needs verification)

**Success Rate:** Medium (requires network access, may miss relationships)

### Method 3: Manual Research Queue
**How it works:**
- If auto-research fails, adds to `docs/RESEARCH_QUEUE.txt`
- User manually researches and adds to database

**Success Rate:** 100% (but requires manual work)

---

## Usage Examples

### Check Coverage Before Backtest
```python
from src.data.supply_chain_manager import SupplyChainManager

manager = SupplyChainManager()
status = manager.ensure_coverage(
    ['AAPL', 'NVDA', 'TSM'],
    max_age_months=6,
    auto_research=False  # Don't auto-download during backtest
)

missing = [t for t, s in status.items() if s != 'ok']
if missing:
    print(f"Missing: {missing}")
```

### Get Related Companies
```python
# Get all companies related to AAPL
related = manager.get_related_companies('AAPL')
# Returns: ['TSM', 'QCOM', 'AVGO', 'MU', 'TXN', ...]
```

### Get Coverage Report
```python
report = manager.get_coverage_report()
print(f"Total companies: {report['total_companies']}")
print(f"Total relationships: {report['total_relationships']}")
print(f"Average age: {report['avg_age_days']:.0f} days")
```

---

## Workflow

### Initial Setup
1. Run expansion script: `python scripts/expand_database_core_stocks.py`
2. Review research queue: `docs/RESEARCH_QUEUE.txt`
3. Manually research flagged stocks
4. Verify relationships: `docs/VERIFICATION_CHECKLIST.md`

### During Backtest
1. Backtest checks coverage automatically
2. Warns if stocks missing/stale
3. Suggests running expansion script
4. Continues with available data

### Incremental Growth
1. New stock appears in backtest
2. Manager checks if covered
3. If missing, adds to research queue
4. User runs expansion script periodically
5. Database grows automatically

---

## Freshness Tracking

**Default Stale Period:** 6 months

**How it works:**
- Each company entry has `last_verified` date
- Manager checks age: `(now - last_verified) / 30 days`
- If age > `max_age_months`, marks as stale
- Stale entries trigger update attempt

**Example:**
- AAPL last verified: 2026-01-25
- Current date: 2026-07-25
- Age: 6 months
- Status: Stale (if max_age_months = 6)

---

## Next Steps

1. **Manual Research:** Research 6 stocks in queue (META, LRCX, KLAC, AMAT, SNPS, CDNS)
2. **Expand Coverage:** Add more stocks beyond core 20
3. **Improve 10-K Parsing:** Better customer name deduction
4. **Add Relationship Strength:** Major vs minor relationships
5. **Temporal Tracking:** Track when relationships start/end

---

## Files

- `src/data/supply_chain_manager.py` - Smart database manager
- `scripts/expand_database_core_stocks.py` - Expansion script
- `data/supply_chain_relationships.json` - Database file
- `docs/RESEARCH_QUEUE.txt` - Manual research queue
- `docs/VERIFICATION_CHECKLIST.md` - Verification guide
- `docs/SUPPLY_CHAIN_DB_GUIDE.md` - Usage guide

---

**Last Updated:** 2026-01-25
