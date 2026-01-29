# System Truth - Executive Summary

**Date:** 2026-01-25  
**Audit Status:** ✅ Complete

---

## WHAT ACTUALLY RUNS

### ✅ Core System (test_signals.py)

1. **Universe Selection** → `UniverseLoader` → CSV files → Optional Gemini ranking
2. **Price Data** → Direct CSV reads (no provider abstraction)
3. **News Analysis** → `NewsAnalyzer` → Gemini API → Supply chain + sentiment
4. **Technical Signals** → Inline calculation (momentum, volume, RSI)
5. **Signal Combination** → `SignalCombiner` → Weighted or ML
6. **Portfolio Construction** → Top N stocks, proportional/equal weights
7. **Backtesting** → Inline calculation (not using `BacktestEngine` class)

**Result:** CSV-based backtesting with Gemini news analysis

---

## WHAT EXISTS BUT IS UNUSED

### ⚠️ Dead Code (Never Imported)

- `src/data/ib_provider.py` - IB data provider
- `src/execution/ib_executor.py` - IB order execution
- `src/data/provider_factory.py` - Data provider factory
- `src/execution/executor_factory.py` - Executor factory
- `src/risk/risk_calculator.py` - Risk calculations
- `src/backtest/backtest_engine.py` - Backtest engine class
- `config/trading_config.yaml` - Trading configuration (never read)

**Impact:** Documentation claims "IB integration complete" but it's never used.

---

## CRITICAL GAPS

1. **No Live Trading:** IB code exists but `test_signals.py` doesn't use it
2. **No Risk Management:** Risk calculator exists but never called
3. **No Position Limits:** Single stock can get 100% weight
4. **No Mode Switching:** Only CSV backtesting works
5. **No Portfolio Optimizer:** Never ported (documentation is misleading)

---

## DOCUMENTATION LIES

| Claim | Reality |
|-------|---------|
| "IB Integration Complete" | Code exists but unused |
| "Mode Switching (backtest/paper/live)" | Doesn't exist in main script |
| "21 Components Ported" | Many are unused |
| "Risk Management" | Code exists but never called |
| "Backtest Engine" | Class exists but inline code runs instead |

---

## WHAT TO FIX

### Immediate (Documentation)

1. Update all integration summaries: "Code exists but not used in main script"
2. Add "USED" vs "UNUSED" status to component inventories
3. Archive planning docs (INTEGRATION_ARCHITECTURE, IB_INTEGRATION_GUIDE)

### Future (Code)

1. **Option A:** Integrate IB into `test_signals.py` (use provider/executor factories)
2. **Option B:** Remove unused IB code (if not planning to use it)
3. **Option C:** Create separate `live_trading.py` script that uses IB components

---

## BOTTOM LINE

**What Works:** CSV backtesting with Gemini news analysis  
**What Doesn't Work:** Live trading, risk management, mode switching  
**What's Misleading:** Documentation claims features are "complete" when code is unused

**Recommendation:** Update documentation to distinguish "code exists" from "code is used"

---

See `docs/SYSTEM_TRUTH_AUDIT.md` for full details.
