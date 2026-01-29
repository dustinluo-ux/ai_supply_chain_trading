# Documentation Audit

**Date:** 2026-01-28  
**Purpose:** Identify duplicate, outdated, inconsistent, or conflicting documentation

---

## 1. Duplicate Content

### Supply Chain Scoring (Multiple Docs)
- **Canonical:** `STRATEGY_MATH.md` (section "Supply Chain Scoring (Universe Ranking)")
- **Duplicates in archive:**
  - `SUPPLY_CHAIN_SCORING_ISSUE.md` - Historical issue analysis
  - `SCORING_ISSUE_SUMMARY.md` - Summary of same issue
  - `GEMINI_RANKING_VERIFICATION.md` - Verification of fix
  - `GEMINI_RANKING_VERIFICATION_FINAL.md` - Final verification
- **Action:** Archive docs are historical, keep for reference. Canonical doc is authoritative.

### Verification Reports (Multiple Docs)
- **Canonical:** `CHANGELOG_BUGFIXES.md` (documents fixes)
- **Duplicates in archive:**
  - `VERIFICATION_ANSWERS.md`
  - `VERIFICATION_REPORT.md`
  - `VERIFICATION_COMPLETE.md`
  - `VERIFICATION_CHECKLIST.md`
  - `VERIFICATION_TEST_SETUP.md`
- **Action:** All archived. Canonical changelog is source of truth.

### Integration Status (Multiple Docs)
- **Canonical:** `EXECUTION_IB.md` (current status)
- **Duplicates in archive:**
  - `IB_INTEGRATION_GUIDE.md`
  - `IB_INTEGRATION_SUMMARY.md`
  - `INTEGRATION_STATUS.md`
  - `INTEGRATION_COMPLETE.md`
  - `INTEGRATION_FINAL_SUMMARY.md`
  - `INTEGRATION_PROGRESS.md`
  - `INTEGRATION_ARCHITECTURE.md`
- **Action:** All archived. Canonical doc is current.

---

## 2. Outdated Information

### FinBERT References (120+ matches in archived docs)
- **Issue:** Many archived docs reference FinBERT as primary/default provider
- **Reality:** System now uses Gemini by default for universe ranking
- **Files affected:** All archived docs mentioning FinBERT (historical context only)
- **Action:** Archived docs are historical. Canonical docs (`SYSTEM_SPEC.md`, `CHANGELOG_BUGFIXES.md`) correctly state Gemini usage.

### Default Provider Mismatch
- **Issue:** `src/signals/supply_chain_scanner.py` line 24 has default `llm_provider="finbert"`
- **Reality:** `universe_loader.py` line 478 explicitly overrides to `"gemini"`
- **Impact:** Low - override works, but default is misleading
- **Action:** Consider changing default to `"gemini"` or documenting why default exists

---

## 3. Inconsistent Terminology

### "Supply Chain Score" vs "AI Relevance Score"
- **Canonical:** `STRATEGY_MATH.md` clarifies two different scores:
  1. Supply Chain Relevance Score (universe ranking)
  2. Supply Chain News Signal Score (weekly trading)
- **Status:** ✅ Resolved in canonical doc

### "Paper Trading" vs "Backtest"
- **Canonical:** `SYSTEM_SPEC.md` has clear definitions
- **Status:** ✅ Resolved with "Trading Modes" section

---

## 4. Conflicting Statements

### None Found
- All canonical docs are consistent
- Archived docs are historical and clearly marked as such

---

## 5. Redundant Files

### Status Documents
- **Canonical:** `SYSTEM_SPEC.md` (current system status)
- **Redundant in archive:**
  - `PROJECT_STATUS.md` - Old status
  - `SYSTEM_TRUTH_AUDIT.md` - Historical audit
  - `SYSTEM_TRUTH_EXECUTIVE_SUMMARY.md` - Summary of audit
- **Action:** All archived. Canonical doc is current.

### Component Inventories
- **Redundant in archive:**
  - `ALL_COMPONENTS_INVENTORY.md`
  - `BEYOND_IB_INVENTORY.md`
  - `COMPREHENSIVE_COMPONENT_INVENTORY.md`
  - `NOT_PORTED_COMPONENTS.md`
- **Action:** All archived. Historical reference only.

---

## Summary

**Canonical Docs (7):** ✅ Clean, consistent, up-to-date
- `README.md`
- `SYSTEM_SPEC.md`
- `STRATEGY_MATH.md`
- `DATA.md`
- `EXECUTION_IB.md`
- `SUPPLY_CHAIN_DB.md`
- `CHANGELOG_BUGFIXES.md`

**Archived Docs (77):** Historical reference only, no conflicts with canonical docs

**Action Items:**
1. ✅ Canonical docs are clean
2. ⚠️ Consider changing `SupplyChainScanner` default from `"finbert"` to `"gemini"` (or document override)
3. ✅ All redundant/outdated content properly archived

---

**Status:** Documentation is well-organized. Canonical docs are authoritative. Archived docs provide historical context without causing confusion.
