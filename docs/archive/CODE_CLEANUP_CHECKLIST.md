# Code Cleanup Checklist

**Date:** 2026-01-28  
**Purpose:** Identify code improvements needed (not critical bugs)

---

## 1. Unused Imports/Files

### Potential Unused Files
- `simple_backtest_v2.py` - May be superseded by inline backtest in `test_signals.py`
- **Action:** Verify if still used, archive if not

### Duplicate Imports
- `test_signals.py` line 16: `import yaml` appears twice (lines 9 and 16)
- **Action:** Remove duplicate

---

## 2. Inconsistent Naming

### Default Provider Name
- **File:** `src/signals/supply_chain_scanner.py` line 24
- **Issue:** Default `llm_provider="finbert"` but system uses Gemini
- **Current:** `universe_loader.py` overrides to `"gemini"` (line 478)
- **Impact:** Misleading default, but override works
- **Action:** Consider changing default to `"gemini"` or add comment explaining override

### Function/Variable Names
- ✅ Generally consistent
- ✅ Clear naming conventions

---

## 3. Hard-Coded Values

### Data Directory Path
- **File:** `config/data_config.yaml` line 8
- **Issue:** Hard-coded OneDrive path: `"C:/Users/dusro/OneDrive/Programming/ai_supply_chain_trading/data/stock_market_data"`
- **Impact:** Not portable across machines
- **Action:** Use relative path or environment variable

### Debug Constants
- **File:** `test_signals.py` lines 26-30
- **Issue:** Debug mode constants at top level
- **Status:** ✅ Acceptable for development, documented
- **Action:** None (intentional for debugging)

---

## 4. Debug Code Left In

### Print Statements
- **File:** `test_signals.py`
- **Count:** ~20 print statements
- **Status:** ✅ Most are intentional logging (not debug)
- **Action:** Review if any should be logger calls instead

### Commented Code
- **Status:** ✅ Minimal commented code found
- **Action:** None

---

## 5. Test Files Confusion

### Main Entry Point
- **File:** `test_signals.py` - ✅ Confirmed as main entry point
- **Status:** Clear from docstring and usage

### Other Scripts
- `run_phase2_pipeline.py` - Purpose unclear, may be legacy
- **Action:** Verify if still used, document or archive

---

## 6. Code Quality Issues

### Error Handling
- ✅ Generally good error handling
- ✅ Fallbacks in place (alphabetical ordering if ranking fails)

### Type Hints
- ⚠️ Some functions missing type hints
- **Action:** Low priority, consider adding for clarity

### Docstrings
- ✅ Most functions have docstrings
- ✅ Clear descriptions

---

## Summary

**Critical Issues:** None

**Minor Issues:**
1. Duplicate `import yaml` in `test_signals.py`
2. Hard-coded OneDrive path in `data_config.yaml`
3. Default `"finbert"` in `SupplyChainScanner` (overridden, but misleading)

**Low Priority:**
1. Consider type hints
2. Review print statements vs logger calls
3. Verify legacy scripts (`simple_backtest_v2.py`, `run_phase2_pipeline.py`)

**Status:** Code is functional and well-structured. Cleanup items are minor improvements, not blockers.
