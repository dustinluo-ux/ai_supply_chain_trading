# Missing Components Analysis

**Date:** 2026-01-25  
**Purpose:** Identify components needed for live trading that don't exist yet

---

## EXECUTIVE SUMMARY

**Missing Components:** 4 major areas  
**Priority:** High (order execution), Medium (monitoring, news), Low (advanced features)

---

## 1. ORDER EXECUTION ❌

### Status: **CRITICAL - MISSING**

**Current State:**
- ✅ Position reading exists (`position_manager.py`)
- ⚠️ Only mock execution exists (`execution_stub.py`)
- ❌ No real IB order submission

**What's Needed:**

#### 1.1 IB Order Executor

**File to Create:** `src/execution/ib_executor.py`

**Requirements:**
- Submit market/limit orders to IB
- Track order status (pending, filled, cancelled)
- Handle order fills and partial fills
- Support order cancellation
- Error handling for rejected orders
- Connection management

**Implementation:**
```python
class IBExecutor:
    def submit_order(ticker, quantity, side, order_type='MARKET')
    def cancel_order(order_id)
    def get_order_status(order_id)
    def get_fills()  # Get recent fills
```

**Dependencies:** `ib_insync`

**Priority:** 🔴 **HIGH** - Required for live trading

---

#### 1.2 Order Manager

**File to Create:** `src/execution/order_manager.py`

**Requirements:**
- Track all orders (pending, filled, cancelled)
- Order history/logging
- Order reconciliation
- Fill reporting
- Order state machine

**Priority:** 🟡 **MEDIUM** - Important for production

---

## 2. LIVE NEWS PROVIDER ❌

### Status: **MISSING**

**Current State:**
- ✅ News analysis exists (Gemini-based)
- ✅ News storage exists (`data/news/`)
- ❌ No live news fetching

**What's Needed:**

#### 2.1 News Provider Interface

**File to Create:** `src/data/news_provider.py`

**Options:**
1. **Polygon.io** (Recommended)
   - Real-time and historical news
   - Good coverage
   - Free tier available
   - API: `polygon-api-client`

2. **NewsAPI**
   - General news (not finance-specific)
   - Free tier: 100 requests/day
   - API: `newsapi-python`

3. **Alpha Vantage**
   - News sentiment API
   - Limited free tier
   - API: `alpha_vantage`

**Implementation:**
```python
class NewsProvider(ABC):
    def fetch_latest_news(ticker: str, hours: int = 24) -> List[Dict]
    def fetch_historical_news(ticker: str, start_date: str, end_date: str) -> List[Dict]
```

**Priority:** 🟡 **MEDIUM** - Needed for live signal generation

---

## 3. MONITORING & ALERTS ❌

### Status: **MISSING**

**Current State:**
- ✅ Logging exists
- ❌ No real-time monitoring
- ❌ No alerts

**What's Needed:**

#### 3.1 Alert Manager

**File to Create:** `src/monitoring/alert_manager.py`

**Requirements:**
- Position alerts (large positions, losses)
- Risk alerts (margin, VaR breaches)
- Order alerts (fills, rejections)
- System alerts (connection issues, errors)
- Notification channels (email, Slack, SMS)

**Implementation:**
```python
class AlertManager:
    def send_alert(level: str, message: str, channel: str = 'email')
    def check_risk_limits(positions, account_value)
    def monitor_positions(positions)
```

**Priority:** 🟡 **MEDIUM** - Important for production

---

#### 3.2 Position Monitor

**File to Create:** `src/monitoring/position_monitor.py`

**Requirements:**
- Real-time position tracking
- P&L monitoring
- Position size limits
- Concentration risk checks

**Priority:** 🟡 **MEDIUM**

---

## 4. RISK MANAGEMENT ENHANCEMENTS ⚠️

### Status: **PARTIAL**

**Current State:**
- ✅ Basic risk calculator exists (`risk_calculator.py`)
- ⚠️ No position limits enforcement
- ⚠️ No stop-loss management

**What's Needed:**

#### 4.1 Position Limits

**File to Create:** `src/risk/position_limits.py`

**Requirements:**
- Maximum position size per ticker
- Maximum portfolio concentration
- Sector limits
- Daily loss limits
- Pre-trade checks

**Priority:** 🟡 **MEDIUM** - Important for risk control

---

#### 4.2 Stop-Loss Manager

**File to Create:** `src/risk/stop_loss_manager.py`

**Requirements:**
- Trailing stops
- Fixed stop-loss
- Stop-loss orders to IB
- Stop-loss monitoring

**Priority:** 🟢 **LOW** - Can be added later

---

## 5. CONFIGURATION MANAGEMENT ⚠️

### Status: **PARTIAL**

**Current State:**
- ✅ YAML config exists
- ⚠️ No mode switching config
- ⚠️ No IB-specific config

**What's Needed:**

#### 5.1 Trading Config

**File to Create:** `config/trading_config.yaml`

**Requirements:**
- Mode selection (backtest/paper/live)
- Data provider selection
- Executor selection
- IB connection settings
- Risk limits
- Order parameters

**Priority:** 🟡 **MEDIUM** - Needed for integration

---

## 6. TESTING & VALIDATION ❌

### Status: **MISSING**

**What's Needed:**

#### 6.1 Paper Trading Tests

**File to Create:** `tests/integration/test_ib_paper_trading.py`

**Requirements:**
- Test IB connection
- Test order submission (paper)
- Test position reading
- Test account info retrieval

**Priority:** 🟡 **MEDIUM** - Important before live trading

---

#### 6.2 Integration Tests

**File to Create:** `tests/integration/test_live_trading_integration.py`

**Requirements:**
- End-to-end test (signal → order → position)
- Mode switching tests
- Provider switching tests

**Priority:** 🟡 **MEDIUM**

---

## IMPLEMENTATION CHECKLIST

### Phase 1: Core Trading (Required for Live Trading)

- [ ] **Port IB Data Provider** (`src/data/ib_provider.py`)
  - Port from `wealth_signal_mvp_v1/core/data/loader_ibkr.py`
  - Adapt to `BaseDataProvider` interface
  - Test connection and data retrieval

- [ ] **Implement IB Executor** (`src/execution/ib_executor.py`)
  - Create order submission logic
  - Implement position reading
  - Add order status tracking
  - Test with paper trading account

- [ ] **Create Provider/Executor Factories**
  - `src/data/provider_factory.py`
  - `src/execution/executor_factory.py`
  - Config-based creation

- [ ] **Update test_signals.py**
  - Use data provider abstraction
  - Use executor abstraction
  - Support mode switching

- [ ] **Create Trading Config**
  - `config/trading_config.yaml`
  - Mode selection
  - IB settings

**Timeline:** 2-3 days

---

### Phase 2: Risk & Monitoring (Important for Production)

- [ ] **Position Limits** (`src/risk/position_limits.py`)
  - Max position size
  - Concentration limits
  - Pre-trade checks

- [ ] **Alert Manager** (`src/monitoring/alert_manager.py`)
  - Risk alerts
  - Order alerts
  - Email/Slack notifications

- [ ] **Position Monitor** (`src/monitoring/position_monitor.py`)
  - Real-time tracking
  - P&L monitoring

**Timeline:** 1-2 days

---

### Phase 3: Enhanced Features (Nice to Have)

- [ ] **Live News Provider** (`src/data/news_provider.py`)
  - Polygon.io integration
  - Real-time news fetching

- [ ] **Order Manager** (`src/execution/order_manager.py`)
  - Order tracking
  - Fill reporting

- [ ] **Stop-Loss Manager** (`src/risk/stop_loss_manager.py`)
  - Trailing stops
  - Stop-loss orders

**Timeline:** 1-2 days

---

## DEPENDENCIES TO ADD

**requirements.txt additions:**
```
ib_insync>=0.9.86          # IB API wrapper
nest_asyncio>=1.5.6        # Async support for IB
polygon-api-client>=1.13.0 # News provider (optional)
newsapi-python>=0.1.6      # Alternative news provider (optional)
```

---

## TESTING STRATEGY

### 1. Unit Tests
- Test each provider/executor in isolation
- Mock IB connections for testing

### 2. Integration Tests (Paper Trading)
- Test with IB paper trading account
- Verify order submission
- Verify position reading

### 3. End-to-End Tests
- Full signal → order → position flow
- Mode switching tests

### 4. Live Trading (After Paper Success)
- Start with small positions
- Monitor closely
- Gradual scaling

---

## RISK MITIGATION

### Before Live Trading:
1. ✅ Test all components in paper trading
2. ✅ Verify order submission works correctly
3. ✅ Test position reading
4. ✅ Test error handling
5. ✅ Set up monitoring/alerts
6. ✅ Implement position limits
7. ✅ Start with small position sizes

### During Live Trading:
1. Monitor all orders closely
2. Set up alerts for errors
3. Use position limits
4. Keep paper trading as backup
5. Regular reconciliation

---

## SUMMARY

**Critical (Phase 1):**
- IB Data Provider ✅ (exists, needs porting)
- IB Executor ❌ (needs implementation)
- Provider/Executor Factories ❌ (needs creation)
- Trading Config ❌ (needs creation)

**Important (Phase 2):**
- Position Limits ❌
- Alert Manager ❌
- Position Monitor ❌

**Nice to Have (Phase 3):**
- Live News Provider ❌
- Order Manager ❌
- Stop-Loss Manager ❌

**Total Estimated Time:** 4-7 days for full implementation

---

**Status:** ✅ **READY FOR IMPLEMENTATION PLANNING**
