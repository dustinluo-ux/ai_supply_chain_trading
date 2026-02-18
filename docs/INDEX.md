# Documentation Index

**Last Updated:** 2026-02-15

**Single entry point for all project documentation.** This file lists the 11 canonical documents that define the system. All other documentation is either archived or superseded.

---

## Quick Start

**New to the project?** Read in this order:
1. **README.md** (project root) - Quick overview and setup
2. **ARCHITECTURE.md** - System design and structure
3. **WORKFLOW.md** - How to use the system
4. **PROJECT_STATUS.md** - Current state and capabilities

---

## Canonical Documentation (11 Files)

These are the **only** authoritative sources. All located in **`docs/`** directory.

### **For Understanding the System**

| Doc | Purpose | Read When |
|-----|---------|-----------|
| **ARCHITECTURE.md** | System design, data flow, module organization | Understanding structure |
| **WORKFLOW.md** | Execution stages (what happens, in order) | Running the system |
| **SYSTEM_MAP.md** | Code mapping (workflow → modules, entry points) | Finding code locations |
| **PROJECT_STATUS.md** | Current state, capabilities, action items | Checking readiness |

### **For Implementation Details**

| Doc | Purpose | Read When |
|-----|---------|-----------|
| **TECHNICAL_SPEC.md** | Indicator math, Master Score, LLM accuracy | Implementing signals |
| **STRATEGY_LOGIC.md** | Capital decision logic, propagation, ML | Understanding decisions |
| **STRATEGY_MATH.md** | Signal formulas, combination, portfolio math | Calculating scores |
| **SUPPLY_CHAIN_DB.md** | Database schema, build process, freshness | Working with relationships |

**Stage 4 (Position Sizing):** `src/portfolio/position_sizer.py` — ATR-based sizing; config: `config/trading_config.yaml` → `position_sizing`; regime BEAR → 0 exposure. See SYSTEM_MAP.md § Stage 5.

### **For Decisions & Results**

| Doc | Purpose | Read When |
|-----|---------|-----------|
| **DECISIONS.md** | Architectural decision records (why choices made) | Understanding rationale |
| **BACKTEST_JOURNAL.md** | Execution assumptions, safety audits, results | Reviewing performance |

### **This File**

| Doc | Purpose |
|-----|---------|
| **INDEX.md** | Documentation index (you are here) |

---

## File Locations

```
project_root/
├── README.md                    # Quick start (root only)
├── AI_RULES.md                  # AI assistant guidelines (root only)
├── .cursorrules                 # Cursor behavior rules (root only)
│
└── docs/                        # All 11 canonical files here
    ├── INDEX.md                 # This file
    ├── ARCHITECTURE.md          # System design
    ├── WORKFLOW.md              # Usage guide
    ├── SYSTEM_MAP.md            # Code locations
    ├── PROJECT_STATUS.md        # Current state
    ├── TECHNICAL_SPEC.md        # Implementation details
    ├── STRATEGY_LOGIC.md        # Decision logic
    ├── STRATEGY_MATH.md         # Formulas
    ├── SUPPLY_CHAIN_DB.md       # Database
    ├── DECISIONS.md             # Decision records
    └── BACKTEST_JOURNAL.md      # Results
```

---

## What Happened to Other Docs?

**All other documentation has been:**
- **Archived** in `docs/archive/` (historical reference only)
- **Deleted** (duplicates, outdated troubleshooting, temporary status files)

**Why?** To maintain a single source of truth and prevent documentation drift.

---

## Adding New Documentation

**Don't create new standalone docs.** Instead:

1. **Is it system design?** → Update **ARCHITECTURE.md**
2. **Is it how to use?** → Update **WORKFLOW.md**
3. **Is it a decision?** → Add to **DECISIONS.md**
4. **Is it implementation?** → Update **TECHNICAL_SPEC.md** or **STRATEGY_LOGIC.md**
5. **Is it current status?** → Update **PROJECT_STATUS.md**

**Exception:** Temporary research notes go in `docs/research/` (not canonical)

---

## For AI Assistants (Cursor)

**Before any work, load in this order:**
1. **INDEX.md** (this file)
2. **ARCHITECTURE.md**
3. **WORKFLOW.md**
4. **SYSTEM_MAP.md**
5. **DECISIONS.md**

Then load task-specific docs as needed.

**Location rule:** All canonical docs are in `docs/`, not project root.

---

## Quick Reference

**Run backtest:**
```bash
python scripts/backtest_technical_library.py --tickers NVDA,AMD,TSM --start 2023-01-01 --end 2023-12-31
```

**Configuration:**
- `config/data_config.yaml` - Data paths
- `config/technical_master_score.yaml` - Signal weights
- `config/trading_config.yaml` - Execution settings

**Key directories:**
- `data/stock_market_data/` - Price CSVs
- `data/news/` - News JSON files
- `data/supply_chain_relationships.json` - Supply chain database

---

## Archived Code (Graveyard)

Per AI_RULES.md §5.2 (The Scavenge Protocol): search graveyard/ before
coding new utilities.

Two reference modules are retained for future use:

| File | Reusable logic |
|------|----------------|
| `graveyard/src/risk/risk_calculator.py` | Position VaR, portfolio VaR (with correlation), margin utilization warning |
| `graveyard/src/policies/exit_policies.py` | Trailing-stop exit (peak-based + time stop), fixed-threshold signal policy |

All other graveyard content has been retired.

---

**Questions?** Check the relevant canonical doc above. If uncertain which, start with ARCHITECTURE.md.
