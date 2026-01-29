# Interactive Brokers Integration

**Last Updated:** 2026-01-25  
**Status:** ⚠️ Code exists but **not used** in main script

---

## Current Status

**Reality Check:**
- IB integration code exists in `src/data/ib_provider.py` and `src/execution/ib_executor.py`
- `test_signals.py` does **not** import or use these components
- System currently only does CSV-based backtesting
- `config/trading_config.yaml` exists but is **never read**

**To Enable:**
1. Modify `test_signals.py` to use `DataProviderFactory` and `ExecutorFactory`
2. Set `config/trading_config.yaml` mode to `"paper"` or `"live"`
3. Connect to IB Gateway/TWS

---

## Architecture

### Data Provider Abstraction

**Base Class:** `src/data/base_provider.py`

**Implementations:**
- `CSVDataProvider` - Reads CSV files (backtest)
- `IBDataProvider` - Fetches from IB (paper/live)

**Factory:** `src/data/provider_factory.py`

```python
from src.data.provider_factory import DataProviderFactory

provider = DataProviderFactory.create("ib", host="127.0.0.1", port=7497)
data = provider.get_historical_data("NVDA", "2023-01-01", "2023-12-31")
```

### Executor Abstraction

**Base Class:** `src/execution/base_executor.py`

**Implementations:**
- `MockExecutor` - Logs orders (backtest)
- `IBExecutor` - Submits orders to IB (paper/live)

**Factory:** `src/execution/executor_factory.py`

```python
from src.execution.executor_factory import ExecutorFactory

executor = ExecutorFactory.create("ib_paper", data_provider=provider, account="DU123456")
result = executor.submit_order("NVDA", quantity=100, side="BUY")
```

---

## Configuration

### `config/trading_config.yaml`

```yaml
trading:
  mode: "backtest"  # Options: backtest, paper, live
  data_provider: "csv"  # Options: csv, ib
  executor: "mock"      # Options: mock, ib_paper, ib_live
  initial_capital: 100000
  
  ib:
    host: "127.0.0.1"
    port: 7497  # 7497 = paper, 7496 = live
    client_id: 1
    
  data:
    csv_dir: "data/prices"
    cache_dir: "data/cache"
    
  execution:
    paper_account: "DU123456"
    live_account: "U123456"
    min_order_size: 1
    max_position_size: 10000
```

---

## IB Setup

### 1. Install IB Gateway or TWS

- **IB Gateway:** Lightweight, headless (recommended for automated trading)
- **TWS:** Full interface (for manual trading + API)

### 2. Enable API Access

**In TWS/Gateway:**
1. Configure → API → Settings
2. Enable "Enable ActiveX and Socket Clients"
3. Set port: `7497` (paper) or `7496` (live)
4. Add trusted IP: `127.0.0.1`

### 3. Connect

```python
from src.data.ib_provider import IBDataProvider

provider = IBDataProvider(host="127.0.0.1", port=7497, client_id=1)
provider._connect()  # Connects to IB Gateway/TWS
```

---

## IB Data Provider

### `src/data/ib_provider.py`

**Methods:**
- `get_historical_data(ticker, start_date, end_date)` - Historical bars
- `get_current_price(ticker)` - Real-time price
- `get_account_info()` - Account details

**Example:**
```python
provider = IBDataProvider(host="127.0.0.1", port=7497)
data = provider.get_historical_data("NVDA", "2023-01-01", "2023-12-31")
# Returns: pd.Series with close prices
```

**Caching:** Optional cache directory for historical data

---

## IB Executor

### `src/execution/ib_executor.py`

**Methods:**
- `submit_order(ticker, quantity, side, order_type, limit_price)` - Submit order
- `cancel_order(order_id)` - Cancel order
- `get_positions()` - Current positions
- `get_account_value()` - Account value

**Example:**
```python
executor = IBExecutor(ib_provider=provider, account="DU123456")
result = executor.submit_order("NVDA", quantity=100, side="BUY", order_type="MARKET")
# Returns: {"order_id": "...", "status": "submitted"}
```

**Order Types:**
- `"MARKET"` - Market order
- `"LIMIT"` - Limit order (requires `limit_price`)

---

## Position Manager

### `src/execution/position_manager.py`

**Methods:**
- `get_current_positions()` - Current holdings from IB
- `get_account_value()` - Total account value
- `calculate_delta_trades(current_weights, optimal_weights, account_value)` - Rebalancing trades

**Example:**
```python
from src.execution.position_manager import PositionManager

manager = PositionManager(ib_provider=provider)
positions = manager.get_current_positions()
# Returns: pd.DataFrame with ticker, quantity, value, weight
```

---

## Mode Switching (Not Implemented)

**Current:** `test_signals.py` only does CSV backtesting

**Planned (if integrated):**
```python
from src.data.provider_factory import DataProviderFactory
from src.execution.executor_factory import ExecutorFactory
import yaml

with open("config/trading_config.yaml") as f:
    config = yaml.safe_load(f)

# Create provider based on config
provider = DataProviderFactory.from_config_file()
executor = ExecutorFactory.from_config_file(data_provider=provider)

# Use provider/executor in backtest
if config["trading"]["mode"] == "backtest":
    # Use CSV data, mock executor
elif config["trading"]["mode"] == "paper":
    # Use IB data, IB executor (paper port)
elif config["trading"]["mode"] == "live":
    # Use IB data, IB executor (live port)
```

---

## Safety Notes

### Paper Trading First

**Always test in paper trading before live:**
1. Set `mode: "paper"` in config
2. Use paper account (`DU123456`)
3. Verify orders execute correctly
4. Check position tracking
5. Monitor for 1-2 weeks

### Risk Management

**Current limitations:**
- No position limits enforced
- No stop-losses
- No volatility targeting
- Risk calculator exists but unused

**Before live trading:**
1. Add position limits (max 15% per stock)
2. Add stop-losses
3. Add volatility targeting
4. Test risk management in paper

### Order Sizing

**Current:** Proportional/equal weighting (can result in large positions)

**Recommendations:**
- Add position size limits
- Use risk-scaled sizing
- Consider liquidity constraints

### Error Handling

**IB API can fail:**
- Network disconnections
- Rate limits
- Invalid orders
- Account restrictions

**Implement:**
- Retry logic
- Error logging
- Fallback behavior
- Position reconciliation

---

## Dependencies

```bash
pip install ib_insync>=0.9.86 nest_asyncio>=1.5.6
```

---

## Testing

### Test IB Connection

```python
from src.data.ib_provider import IBDataProvider

provider = IBDataProvider(host="127.0.0.1", port=7497)
if provider.is_available():
    print("Connected to IB")
    price = provider.get_current_price("NVDA")
    print(f"NVDA price: ${price}")
else:
    print("IB not available")
```

### Test Order Submission (Paper)

```python
from src.execution.ib_executor import IBExecutor

executor = IBExecutor(ib_provider=provider, account="DU123456")
result = executor.submit_order("NVDA", quantity=1, side="BUY", order_type="MARKET")
print(result)
```

---

## Known Issues

1. **Not Integrated:** Code exists but `test_signals.py` doesn't use it
2. **No Mode Switching:** Only CSV backtesting works
3. **No Risk Management:** Risk calculator exists but unused
4. **Async Complexity:** IB API uses asyncio (requires `nest_asyncio`)

---

## Future Work

1. **Integrate into `test_signals.py`:**
   - Use `DataProviderFactory` for data loading
   - Use `ExecutorFactory` for order execution
   - Add mode switching logic

2. **Add Risk Management:**
   - Position limits
   - Stop-losses
   - Volatility targeting

3. **Add Monitoring:**
   - Real-time position tracking
   - Alert system
   - Performance dashboard

---

**Status:** Code ready but requires integration work to use in main script.

See `docs/SYSTEM_SPEC.md` for current system status.
