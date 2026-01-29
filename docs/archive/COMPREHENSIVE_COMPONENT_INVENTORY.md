# Comprehensive Component Inventory - All Useful Modules

**Date:** 2026-01-25  
**Source Project:** `wealth_signal_mvp_v1`  
**Current Project:** `ai_supply_chain_trading`  
**Purpose:** Identify ALL useful components beyond IB integration

---

## EXECUTIVE SUMMARY

**Total Components Found:** 25+ modules  
**Already in Current Project:** 3 modules (basic backtest, technical indicators, logger)  
**Missing & Useful:** 22+ modules

---

## COMPONENT COMPARISON

### ✅ Already Exists (Current Project)

| Component | Current Project | Old Project | Status |
|-----------|----------------|-------------|--------|
| Backtest Engine | `src/backtest/backtest_engine.py` (vectorbt-based) | `core/simulation/backtest_engine.py` (comprehensive) | ⚠️ **EXISTS BUT SIMPLER** |
| Technical Indicators | `src/signals/technical_indicators.py` | `core/ta_lib/features.py` | ✅ **EXISTS** |
| Logger | `src/utils/logger.py` | `core/utils/logger.py` | ✅ **EXISTS** |

---

## MISSING COMPONENTS (High Value)

### 1. BACKTESTING & SIMULATION

#### 1.1 PnL Simulator ✅ **HIGH VALUE**

**File:** `core/simulation/pnl_simulator.py`  
**Status:** ✅ **READY TO PORT**

**Capabilities:**
- Trade-based PnL simulation (horizon-based)
- Position-based PnL simulation (mark-to-market)
- Forward return calculation
- Cumulative PnL tracking

**Key Functions:**
```python
def simulate_pnl_from_trades(trade_series, price_series, horizon=21) -> pd.DataFrame
def simulate_pnl_position_mode(positions, price_series) -> pd.DataFrame
```

**Why Useful:**
- More flexible than current vectorbt approach
- Supports different holding periods
- Position-based mode for continuous strategies

**Port To:** `src/backtesting/pnl_simulator.py`

---

#### 1.2 Portfolio Simulator ✅ **HIGH VALUE**

**File:** `core/simulation/portfolio_simulator.py`  
**Status:** ✅ **READY TO PORT**

**Capabilities:**
- Multi-asset portfolio simulation
- Weight-based rebalancing
- Portfolio-level metrics (Sharpe, drawdown)
- Per-asset return tracking

**Key Function:**
```python
def simulate_portfolio(assets, weights, price_data, initial_capital=100000) -> Dict
```

**Why Useful:**
- Current project doesn't have multi-asset portfolio simulation
- Supports rebalancing strategies
- Comprehensive metrics

**Port To:** `src/backtesting/portfolio_simulator.py`

---

#### 1.3 Enhanced Backtest Engine ✅ **MEDIUM VALUE**

**File:** `core/simulation/backtest_engine.py`  
**Status:** ✅ **READY TO PORT** (but current project has basic version)

**Additional Features:**
- Multiple backtest modes (trade, position, portfolio)
- Performance metrics calculation
- Backtest comparison
- Signal diagnostics

**Why Useful:**
- More comprehensive than current vectorbt-based engine
- Supports multiple backtest types
- Better metrics calculation

**Port To:** `src/backtesting/enhanced_backtest_engine.py` (or enhance existing)

---

### 2. PORTFOLIO MANAGEMENT

#### 2.1 Portfolio Optimizer ✅ **HIGH VALUE**

**File:** `core/portfolio/portfolio_optimizer.py`  
**Status:** ✅ **READY TO PORT**

**Capabilities:**
- Risk-scaled position sizing
- Model blending
- Cost-aware optimization
- Liquidity constraints
- Leverage limits
- Volatility targeting

**Key Features:**
- Normalize forecasts (z-score, rank)
- Risk scaling (volatility-adjusted)
- Model filtering (vol/corr based)
- Cost calculation (commissions, spreads, impact)
- Order generation

**Why Useful:**
- Current project doesn't have portfolio optimization
- Sophisticated risk management
- Cost-aware trading
- Multi-model support

**Port To:** `src/portfolio/optimizer.py`

---

#### 2.2 Position Sizing ✅ **HIGH VALUE**

**File:** `core/ta_lib/sizing.py`  
**Status:** ✅ **READY TO PORT**

**Capabilities:**
- Position sizing from weights
- Cost calculation (commissions, spreads)
- Liquidity capping (ADV-based)
- No-trade bands (cost threshold)
- Futures/equities support

**Key Functions:**
```python
def position_sizer(weights, acct, asset_meta) -> pd.DataFrame
def no_trade_band(current_qty, target_qty, asset_meta, costs) -> pd.Series
def liquidity_cap(delta_qty, asset_meta, limits) -> pd.Series
```

**Why Useful:**
- Current project doesn't have position sizing logic
- Cost-aware trading
- Liquidity management
- Prevents overtrading

**Port To:** `src/portfolio/sizing.py`

---

### 3. TRADING POLICIES

#### 3.1 Exit Policies ✅ **HIGH VALUE**

**File:** `core/policies/exit_policies.py`  
**Status:** ✅ **READY TO PORT**

**Capabilities:**
- Fixed threshold policy (entry/exit thresholds)
- Trailing stop policy (dynamic stop-loss)
- Regime-based suppression
- Time-based stops

**Key Classes:**
```python
class FixedThresholdPolicy:
    def apply(predicted_series) -> pd.Series  # +1, 0, -1 signals

class TrailingStopPolicy:
    def apply(predicted_series, price) -> pd.Series  # Position series
```

**Why Useful:**
- Current project has basic stop-loss, but not sophisticated exit policies
- Trailing stops for profit protection
- Regime-aware trading
- More flexible than fixed stop-loss

**Port To:** `src/policies/exit_policies.py`

---

#### 3.2 Target to Trade Mapper ✅ **MEDIUM VALUE**

**File:** `core/policies/target_to_trade_mapper.py`  
**Status:** ✅ **READY TO PORT**

**Capabilities:**
- Convert continuous signals to discrete trades
- Threshold-based mapping
- Regime suppression

**Key Function:**
```python
def map_signals_to_trades(signal_series, upper_threshold, lower_threshold, regime_series) -> pd.Series
```

**Why Useful:**
- Clean signal-to-trade conversion
- Regime-aware trading
- Threshold management

**Port To:** `src/policies/signal_mapper.py`

---

### 4. RISK MANAGEMENT

#### 4.1 Risk Calculator ✅ **HIGH VALUE**

**File:** `core/utils/risk_calculator.py`  
**Status:** ✅ **READY TO PORT**

**Capabilities:**
- Position-level VaR
- Portfolio-level VaR (with correlations)
- Margin utilization tracking
- Risk warnings

**Key Functions:**
```python
def calculate_position_risk(price, quantity, volatility, point_value) -> float
def calculate_portfolio_risk(positions, correlation_matrix) -> float
def calculate_margin_utilization(current_margin, total_margin) -> tuple
```

**Why Useful:**
- Current project doesn't have risk calculations
- VaR for position sizing
- Margin monitoring
- Risk-based position limits

**Port To:** `src/risk/risk_calculator.py`

---

### 5. UTILITIES

#### 5.1 Trading Parameters Manager ✅ **MEDIUM VALUE**

**File:** `core/utils/trading_parameters.py`  
**Status:** ✅ **READY TO PORT**

**Capabilities:**
- Watchlist management
- Trading parameter loading
- Asset type filtering
- Asset-specific parameters

**Key Class:**
```python
class TradingParameters:
    watchlist -> pd.DataFrame
    parameters -> Dict
    get_assets_by_type(asset_type) -> List[str]
    get_asset_params(symbol) -> Dict
```

**Why Useful:**
- Centralized parameter management
- Watchlist support
- Asset configuration

**Port To:** `src/utils/trading_parameters.py`

---

#### 5.2 Audit Logger ✅ **MEDIUM VALUE**

**File:** `core/logging/audit_logger.py`  
**Status:** ✅ **READY TO PORT**

**Capabilities:**
- Run-level audit logging
- Metrics tracking
- Config snapshot
- Trade summary logging

**Key Function:**
```python
def log_audit_record(run_id, model_metrics, config, output_paths, trade_summary) -> str
```

**Why Useful:**
- Better than basic logging
- Run tracking
- Reproducibility
- Performance tracking

**Port To:** `src/logging/audit_logger.py`

---

#### 5.3 Error Handler ✅ **LOW VALUE**

**File:** `core/utils/error_handler.py`  
**Status:** ✅ **READY TO PORT**

**Capabilities:**
- Error handling utilities
- Exception management

**Why Useful:**
- Better error handling
- But current project may have similar

**Port To:** `src/utils/error_handler.py` (if needed)

---

### 6. MACRO & REGIME

#### 6.1 Macro Regime Classifier ✅ **MEDIUM VALUE**

**File:** `core/regimes/macro_regime_classifier.py`  
**Status:** ✅ **READY TO PORT**

**Capabilities:**
- Macro regime classification
- Regime labels (risk_on, recession, volatile, stagflation)
- Based on yield curve, ISM, CPI, credit spreads

**Key Function:**
```python
def classify_macro_regime(df_macro) -> pd.Series
```

**Why Useful:**
- Regime-aware trading
- Risk management
- Can suppress trades in hostile regimes

**Port To:** `src/regimes/macro_classifier.py`

---

### 7. TECHNICAL ANALYSIS

#### 7.1 TA Features ✅ **LOW VALUE** (Current project has similar)

**File:** `core/ta_lib/features.py`  
**Status:** ⚠️ **SIMILAR EXISTS**

**Capabilities:**
- TA feature engineering
- SMA, EMA, RSI, ADX, Bollinger Bands, ATR

**Why Useful:**
- Current project has `technical_indicators.py`
- May have different features
- Could merge/enhance

**Port To:** `src/signals/ta_features.py` (or enhance existing)

---

#### 7.2 TA Rules ✅ **LOW VALUE**

**File:** `core/ta_lib/rules.py`  
**Status:** ✅ **READY TO PORT** (if needed)

**Capabilities:**
- Technical trading rules
- Pattern recognition

**Why Useful:**
- May have useful rules
- But current project may not need

**Port To:** `src/signals/ta_rules.py` (optional)

---

### 8. DATA & FEATURES

#### 8.1 Feature Engineering ✅ **LOW VALUE** (May overlap)

**File:** `core/features/feature_engineering.py`  
**Status:** ⚠️ **MAY OVERLAP**

**Capabilities:**
- Feature engineering pipeline
- Signal diagnostics

**Why Useful:**
- Current project has signal generation
- May have useful diagnostics

**Port To:** `src/features/feature_engineering.py` (if different from current)

---

## PRIORITY RANKING

### 🔴 HIGH PRIORITY (Core Trading Features)

1. **Portfolio Optimizer** - Sophisticated risk-scaled optimization
2. **Position Sizing** - Cost-aware, liquidity-capped sizing
3. **PnL Simulator** - Flexible backtesting
4. **Portfolio Simulator** - Multi-asset simulation
5. **Exit Policies** - Trailing stops, regime-aware exits
6. **Risk Calculator** - VaR, margin monitoring

### 🟡 MEDIUM PRIORITY (Enhancements)

7. **Target to Trade Mapper** - Signal conversion
8. **Trading Parameters Manager** - Configuration management
9. **Audit Logger** - Run tracking
10. **Macro Regime Classifier** - Regime-aware trading
11. **Enhanced Backtest Engine** - Better metrics

### 🟢 LOW PRIORITY (Nice to Have)

12. **TA Features** - If different from current
13. **TA Rules** - If needed
14. **Error Handler** - If current lacks
15. **Feature Engineering** - If different

---

## INTEGRATION PLAN

### Phase 1: Core Trading (2-3 days)

**Goal:** Enable sophisticated portfolio management

**Tasks:**
1. Port Portfolio Optimizer
2. Port Position Sizing
3. Port PnL Simulator
4. Port Portfolio Simulator
5. Port Exit Policies
6. Port Risk Calculator

**Deliverable:** Full portfolio management with risk controls

---

### Phase 2: Enhancements (1-2 days)

**Tasks:**
1. Port Trading Parameters Manager
2. Port Audit Logger
3. Port Macro Regime Classifier
4. Port Target to Trade Mapper

**Deliverable:** Enhanced trading system with regime awareness

---

### Phase 3: Polish (1 day)

**Tasks:**
1. Port TA Features (if different)
2. Port Error Handler (if needed)
3. Enhance existing backtest engine

**Deliverable:** Complete feature set

---

## FILES TO PORT

### High Priority (6 files)

1. `core/simulation/pnl_simulator.py` → `src/backtesting/pnl_simulator.py`
2. `core/simulation/portfolio_simulator.py` → `src/backtesting/portfolio_simulator.py`
3. `core/portfolio/portfolio_optimizer.py` → `src/portfolio/optimizer.py`
4. `core/ta_lib/sizing.py` → `src/portfolio/sizing.py`
5. `core/policies/exit_policies.py` → `src/policies/exit_policies.py`
6. `core/utils/risk_calculator.py` → `src/risk/risk_calculator.py`

### Medium Priority (4 files)

7. `core/policies/target_to_trade_mapper.py` → `src/policies/signal_mapper.py`
8. `core/utils/trading_parameters.py` → `src/utils/trading_parameters.py`
9. `core/logging/audit_logger.py` → `src/logging/audit_logger.py`
10. `core/regimes/macro_regime_classifier.py` → `src/regimes/macro_classifier.py`

### Low Priority (3 files)

11. `core/ta_lib/features.py` → `src/signals/ta_features.py` (if different)
12. `core/utils/error_handler.py` → `src/utils/error_handler.py` (if needed)
13. `core/simulation/backtest_engine.py` → Enhance existing (if better)

---

## DEPENDENCIES TO ADD

**requirements.txt additions:**
```
ta>=0.10.2              # Technical analysis library (for TA features)
scipy>=1.9.0            # For portfolio optimization (if needed)
```

**Note:** Most dependencies already exist (pandas, numpy, etc.)

---

## SUMMARY

**Total Components to Port:** 13 files  
**High Priority:** 6 files  
**Medium Priority:** 4 files  
**Low Priority:** 3 files

**Estimated Time:**
- Phase 1 (High Priority): 2-3 days
- Phase 2 (Medium Priority): 1-2 days
- Phase 3 (Low Priority): 1 day
- **Total:** 4-6 days

**Value:** Very High - Adds sophisticated portfolio management, risk controls, and trading policies

---

**Status:** ✅ **READY FOR PORTING**
