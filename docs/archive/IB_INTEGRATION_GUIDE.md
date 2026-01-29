# IB Integration Guide - Step-by-Step

**Date:** 2026-01-25  
**Purpose:** Step-by-step guide to porting and integrating IB components

---

## OVERVIEW

This guide walks through porting IB components from `wealth_signal_mvp_v1` to `ai_supply_chain_trading` and integrating them with the existing system.

---

## STEP 1: SETUP DEPENDENCIES

### 1.1 Update requirements.txt

**File:** `requirements.txt`

Add these lines:
```
ib_insync>=0.9.86
nest_asyncio>=1.5.6
```

**Command:**
```bash
pip install ib_insync nest_asyncio
```

---

## STEP 2: PORT IB DATA PROVIDER

### 2.1 Create Base Provider Interface

**File:** `src/data/base_provider.py`

```python
from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd

class BaseDataProvider(ABC):
    """Abstract base class for data providers."""
    
    @abstractmethod
    def get_historical_data(
        self,
        ticker: str,
        start_date: str,
        end_date: Optional[str] = None,
        **kwargs
    ) -> pd.Series:
        """Get historical price data."""
        pass
    
    @abstractmethod
    def get_current_price(self, ticker: str) -> float:
        """Get current/latest price."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Return provider name."""
        pass
```

### 2.2 Port IB Data Provider

**File:** `src/data/ib_provider.py`

**Source:** `wealth_signal_mvp_v1/core/data/loader_ibkr.py`

**Changes needed:**
1. Rename `IBKRDataLoader` → `IBDataProvider`
2. Inherit from `BaseDataProvider`
3. Update method signatures to match interface
4. Keep all IB connection logic
5. Keep caching logic
6. Keep futures/crypto/forex support

**Key methods to port:**
- `__init__()` - Connection setup
- `get_historical_data()` - Historical bars
- `get_account_info()` - Account/margin info
- `get_current_price()` - Real-time price (add if missing)

---

## STEP 3: CREATE CSV PROVIDER

### 3.1 Create CSV Provider

**File:** `src/data/csv_provider.py`

**Purpose:** For backtesting with existing CSV files

**Implementation:** See `docs/INTEGRATION_ARCHITECTURE.md` for full code

---

## STEP 4: CREATE PROVIDER FACTORY

### 4.1 Create Factory

**File:** `src/data/provider_factory.py`

**Purpose:** Create providers based on config

**Implementation:** See `docs/INTEGRATION_ARCHITECTURE.md` for full code

---

## STEP 5: PORT POSITION MANAGER

### 5.1 Port Position Manager

**File:** `src/execution/position_manager.py`

**Source:** `wealth_signal_mvp_v1/core/portfolio/position_manager.py`

**Changes needed:**
1. Update import: `from src.data.ib_provider import IBDataProvider`
2. Keep all position calculation logic
3. Keep delta trade calculation
4. No changes to core logic

---

## STEP 6: IMPLEMENT IB EXECUTOR

### 6.1 Create Base Executor

**File:** `src/execution/base_executor.py`

**Implementation:** See `docs/INTEGRATION_ARCHITECTURE.md` for full code

### 6.2 Create Mock Executor

**File:** `src/execution/mock_executor.py`

**Purpose:** For backtesting (no real orders)

**Implementation:** See `docs/INTEGRATION_ARCHITECTURE.md` for full code

### 6.3 Implement IB Executor

**File:** `src/execution/ib_executor.py`

**Implementation:** See `docs/INTEGRATION_ARCHITECTURE.md` for full code

**Key features:**
- Order submission (market/limit)
- Order cancellation
- Order status tracking
- Position reading
- Account value retrieval

---

## STEP 7: CREATE EXECUTOR FACTORY

### 7.1 Create Factory

**File:** `src/execution/executor_factory.py`

**Purpose:** Create executors based on config

**Implementation:** See `docs/INTEGRATION_ARCHITECTURE.md` for full code

---

## STEP 8: CREATE TRADING CONFIG

### 8.1 Create Config File

**File:** `config/trading_config.yaml`

```yaml
trading:
  mode: "backtest"  # Options: backtest, paper, live
  
  data_provider: "csv"  # Options: csv, ib
  executor: "mock"      # Options: mock, ib_paper, ib_live
  
  initial_capital: 100000
  
  # IB Settings
  ib:
    host: "127.0.0.1"
    port: 7497  # 7497 = paper, 7496 = live
    client_id: 1
    
  # Data Settings
  data:
    csv_dir: "data/price_data"
    cache_dir: "data/cache"
    
  # Execution Settings
  execution:
    paper_account: "DU123456"  # Your paper account
    live_account: "U123456"     # Your live account (if applicable)
    min_order_size: 1
    max_position_size: 10000
```

---

## STEP 9: UPDATE test_signals.py

### 9.1 Add Provider/Executor Imports

**File:** `test_signals.py`

Add at top:
```python
from src.data.provider_factory import DataProviderFactory
from src.execution.executor_factory import ExecutorFactory
import yaml
```

### 9.2 Initialize Providers

Add after config loading:
```python
# Load trading config
with open('config/trading_config.yaml', 'r') as f:
    trading_config = yaml.safe_load(f).get('trading', {})

# Initialize data provider and executor
data_provider = DataProviderFactory.from_config_file()
executor = ExecutorFactory.from_config_file()

print(f"Data Provider: {data_provider.get_name()}")
print(f"Executor: {executor.get_name()}")
print(f"Mode: {trading_config.get('mode', 'backtest')}")
```

### 9.3 Replace Price Data Loading

**Find:** Where price data is loaded (likely in UniverseLoader)

**Replace with:**
```python
# Use configured data provider
price_data = data_provider.get_historical_data(
    ticker=ticker,
    start_date=start_date,
    end_date=end_date
)
```

### 9.4 Add Trade Execution (Optional)

If you want to execute trades:
```python
# Execute trade
def execute_trade(ticker: str, quantity: int, side: str):
    """Execute trade using configured executor."""
    try:
        order = executor.submit_order(
            ticker=ticker,
            quantity=quantity,
            side=side,
            order_type='MARKET'
        )
        print(f"Order submitted: {order}")
        return order
    except Exception as e:
        print(f"Order failed: {e}")
        return None
```

---

## STEP 10: TESTING

### 10.1 Test CSV Provider (Backtest Mode)

**Config:**
```yaml
trading:
  mode: "backtest"
  data_provider: "csv"
  executor: "mock"
```

**Test:**
```python
python test_signals.py --universe-size 5
```

**Expected:** Should work exactly as before (using CSV files)

---

### 10.2 Test IB Provider (Paper Trading)

**Prerequisites:**
1. Install TWS or IB Gateway
2. Enable API connections in TWS/Gateway
3. Start TWS/Gateway
4. Note your paper trading account number

**Config:**
```yaml
trading:
  mode: "paper"
  data_provider: "ib"
  executor: "ib_paper"
  ib:
    host: "127.0.0.1"
    port: 7497
    client_id: 1
  execution:
    paper_account: "DU123456"  # Your paper account
```

**Test:**
```python
# Test connection
from src.data.ib_provider import IBDataProvider

provider = IBDataProvider(host="127.0.0.1", port=7497, client_id=1)
data = provider.get_historical_data("AAPL", "2024-01-01", "2024-12-31")
print(f"Got {len(data)} data points")
```

**Expected:** Should fetch data from IB

---

### 10.3 Test IB Executor (Paper Trading)

**Test:**
```python
from src.execution.ib_executor import IBExecutor

executor = IBExecutor(host="127.0.0.1", port=7497, client_id=2, 
                     account="DU123456")

# Get positions
positions = executor.get_positions()
print(f"Current positions: {positions}")

# Get account value
nav = executor.get_account_value()
print(f"Account value: ${nav:,.2f}")

# Submit test order (small quantity)
order = executor.submit_order("AAPL", 1, "BUY", order_type="MARKET")
print(f"Order: {order}")
```

**Expected:** Should submit order to paper account

---

## STEP 11: INTEGRATION CHECKLIST

### Pre-Integration
- [ ] Install `ib_insync` and `nest_asyncio`
- [ ] Set up TWS/IB Gateway
- [ ] Get paper trading account number
- [ ] Test IB connection manually

### Integration
- [ ] Port IB data provider
- [ ] Create CSV provider
- [ ] Create provider factory
- [ ] Port position manager
- [ ] Implement IB executor
- [ ] Create mock executor
- [ ] Create executor factory
- [ ] Create trading config
- [ ] Update test_signals.py

### Testing
- [ ] Test CSV provider (backtest mode)
- [ ] Test IB provider (paper mode)
- [ ] Test IB executor (paper mode)
- [ ] Test mode switching
- [ ] Test end-to-end flow

### Production Readiness
- [ ] Add error handling
- [ ] Add logging
- [ ] Add position limits
- [ ] Add alerts
- [ ] Test with small positions
- [ ] Document live trading setup

---

## TROUBLESHOOTING

### IB Connection Issues

**Problem:** Can't connect to TWS/IB Gateway

**Solutions:**
1. Check TWS/Gateway is running
2. Enable API connections in TWS settings
3. Check port (7497 = paper, 7496 = live)
4. Check firewall settings
5. Try different client_id

### Order Submission Issues

**Problem:** Orders not submitting

**Solutions:**
1. Check account number is correct
2. Check account has sufficient buying power
3. Check order size is valid
4. Check market hours
5. Review IB error messages

### Data Retrieval Issues

**Problem:** No data returned

**Solutions:**
1. Check ticker symbol is correct
2. Check date range is valid
3. Check market data subscriptions
4. Try different exchange
5. Check IB connection status

---

## NEXT STEPS

After completing integration:

1. **Test thoroughly in paper trading**
2. **Add risk management** (position limits, alerts)
3. **Add monitoring** (position tracking, alerts)
4. **Document live trading setup**
5. **Start with small positions**

---

**Status:** ✅ **READY FOR IMPLEMENTATION**
