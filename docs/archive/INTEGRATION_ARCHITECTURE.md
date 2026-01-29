# IB Integration Architecture

**Date:** 2026-01-25  
**Purpose:** Design abstraction layer for data providers and executors with mode switching

---

## ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────┐
│                    Trading System Core                       │
│  (test_signals.py, signal generation, portfolio logic)     │
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│  ┌──────────────────┐         ┌──────────────────┐         │
│  │  Data Provider   │         │   Executor       │         │
│  │   (Abstract)     │         │   (Abstract)      │         │
│  └────────┬─────────┘         └────────┬─────────┘         │
│           │                             │                    │
│  ┌────────┴─────────┐         ┌────────┴─────────┐         │
│  │                  │         │                  │         │
│  │ CSV Provider     │         │ Mock Executor    │         │
│  │ IB Provider      │         │ IB Executor      │         │
│  │ Yahoo Provider   │         │ Paper Executor   │         │
│  │                  │         │                  │         │
│  └──────────────────┘         └──────────────────┘         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## MODE SWITCHING

### Configuration-Based Mode Selection

**File:** `config/trading_config.yaml`

```yaml
trading:
  mode: "backtest"  # Options: backtest, paper, live
  
  data_provider: "csv"  # Options: csv, ib, yahoo
  executor: "mock"      # Options: mock, ib_paper, ib_live
  
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
    paper_account: "DU123456"  # Paper trading account
    live_account: "U123456"     # Live account
    min_order_size: 1
    max_position_size: 10000
```

---

## DATA PROVIDER ABSTRACTION

### Base Interface

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
    
    def is_available(self) -> bool:
        """Check if provider is available."""
        return True
```

### CSV Provider (Existing)

**File:** `src/data/csv_provider.py`

```python
from src.data.base_provider import BaseDataProvider
import pandas as pd
from pathlib import Path

class CSVDataProvider(BaseDataProvider):
    """CSV-based data provider for backtesting."""
    
    def __init__(self, data_dir: str = "data/price_data"):
        self.data_dir = Path(data_dir)
    
    def get_historical_data(self, ticker: str, start_date: str, 
                          end_date: Optional[str] = None, **kwargs) -> pd.Series:
        csv_file = self.data_dir / f"{ticker}.csv"
        if not csv_file.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_file}")
        
        df = pd.read_csv(csv_file, index_col=0, parse_dates=True)
        series = df['close'] if 'close' in df.columns else df.iloc[:, 0]
        
        if start_date:
            series = series[series.index >= pd.Timestamp(start_date)]
        if end_date:
            series = series[series.index <= pd.Timestamp(end_date)]
        
        return series
    
    def get_current_price(self, ticker: str) -> float:
        series = self.get_historical_data(ticker, start_date="2020-01-01")
        return float(series.iloc[-1])
    
    def get_name(self) -> str:
        return "csv"
```

### IB Provider (To Port)

**File:** `src/data/ib_provider.py`

```python
from src.data.base_provider import BaseDataProvider
from ib_insync import IB, Stock, util
import pandas as pd
from typing import Optional
import nest_asyncio

class IBDataProvider(BaseDataProvider):
    """Interactive Brokers data provider."""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 7497, 
                 client_id: int = 1):
        self.ib = IB()
        nest_asyncio.apply()
        self.host = host
        self.port = port
        self.client_id = client_id
        self._connect()
    
    def _connect(self):
        """Connect to IB TWS/IBGateway."""
        if self.ib.isConnected():
            self.ib.disconnect()
        self.ib.connect(self.host, self.port, clientId=self.client_id)
    
    def get_historical_data(self, ticker: str, start_date: str,
                          end_date: Optional[str] = None, 
                          exchange: str = "SMART",
                          currency: str = "USD", **kwargs) -> pd.Series:
        """Get historical data from IB."""
        contract = Stock(ticker, exchange, currency)
        
        duration_str = '2 Y'
        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime=end_date if end_date else '',
            durationStr=duration_str,
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )
        
        if not bars:
            raise ValueError(f"No data returned from IB for {ticker}")
        
        df = util.df(bars)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index("date", inplace=True)
        df = df[df.index >= pd.Timestamp(start_date)]
        
        return df["close"].rename(ticker)
    
    def get_current_price(self, ticker: str) -> float:
        """Get current market price."""
        contract = Stock(ticker, "SMART", "USD")
        self.ib.qualifyContracts(contract)
        ticker_data = self.ib.reqMktData(contract, '', False, False)
        self.ib.sleep(1)  # Wait for data
        return float(ticker_data.last)
    
    def get_name(self) -> str:
        return "ib"
    
    def is_available(self) -> bool:
        """Check if IB connection is available."""
        try:
            return self.ib.isConnected()
        except:
            return False
    
    def __del__(self):
        """Cleanup connection."""
        if hasattr(self, 'ib') and self.ib.isConnected():
            self.ib.disconnect()
```

### Provider Factory

**File:** `src/data/provider_factory.py`

```python
from src.data.base_provider import BaseDataProvider
from src.data.csv_provider import CSVDataProvider
from src.data.ib_provider import IBDataProvider
from typing import Optional
import yaml

class DataProviderFactory:
    """Factory for creating data providers based on config."""
    
    @staticmethod
    def create(config: dict) -> BaseDataProvider:
        """Create data provider from config."""
        provider_type = config.get('data_provider', 'csv')
        
        if provider_type == 'csv':
            return CSVDataProvider(
                data_dir=config.get('data', {}).get('csv_dir', 'data/price_data')
            )
        elif provider_type == 'ib':
            ib_config = config.get('ib', {})
            return IBDataProvider(
                host=ib_config.get('host', '127.0.0.1'),
                port=ib_config.get('port', 7497),
                client_id=ib_config.get('client_id', 1)
            )
        else:
            raise ValueError(f"Unknown data provider: {provider_type}")
    
    @staticmethod
    def from_config_file(config_path: str = "config/trading_config.yaml") -> BaseDataProvider:
        """Load provider from config file."""
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return DataProviderFactory.create(config.get('trading', {}))
```

---

## EXECUTOR ABSTRACTION

### Base Interface

**File:** `src/execution/base_executor.py`

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import pandas as pd

class BaseExecutor(ABC):
    """Abstract base class for trade executors."""
    
    @abstractmethod
    def submit_order(
        self,
        ticker: str,
        quantity: int,
        side: str,  # 'BUY' or 'SELL'
        order_type: str = 'MARKET',
        limit_price: Optional[float] = None
    ) -> Dict:
        """Submit an order."""
        pass
    
    @abstractmethod
    def get_positions(self) -> pd.DataFrame:
        """Get current positions."""
        pass
    
    @abstractmethod
    def get_account_value(self) -> float:
        """Get account value (NAV)."""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict:
        """Get order status."""
        pass
    
    def get_name(self) -> str:
        """Return executor name."""
        pass
```

### Mock Executor (For Backtesting)

**File:** `src/execution/mock_executor.py`

```python
from src.execution.base_executor import BaseExecutor
import pandas as pd
from typing import Dict, Optional
from datetime import datetime

class MockExecutor(BaseExecutor):
    """Mock executor for backtesting (no real orders)."""
    
    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.positions = {}  # ticker -> quantity
        self.order_history = []
        self.cash = initial_capital
    
    def submit_order(self, ticker: str, quantity: int, side: str,
                    order_type: str = 'MARKET',
                    limit_price: Optional[float] = None) -> Dict:
        """Simulate order submission."""
        order_id = f"MOCK_{len(self.order_history)}"
        
        # Update positions
        if side == 'BUY':
            self.positions[ticker] = self.positions.get(ticker, 0) + quantity
        elif side == 'SELL':
            self.positions[ticker] = self.positions.get(ticker, 0) - quantity
        
        order = {
            'order_id': order_id,
            'ticker': ticker,
            'quantity': quantity,
            'side': side,
            'status': 'FILLED',
            'timestamp': datetime.now()
        }
        self.order_history.append(order)
        
        return order
    
    def get_positions(self) -> pd.DataFrame:
        """Get current positions."""
        if not self.positions:
            return pd.DataFrame(columns=['ticker', 'quantity'])
        
        return pd.DataFrame([
            {'ticker': ticker, 'quantity': qty}
            for ticker, qty in self.positions.items() if qty != 0
        ])
    
    def get_account_value(self) -> float:
        """Get account value."""
        return self.initial_capital  # Simplified
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel order (mock)."""
        return True
    
    def get_order_status(self, order_id: str) -> Dict:
        """Get order status."""
        for order in self.order_history:
            if order['order_id'] == order_id:
                return order
        return {'status': 'NOT_FOUND'}
    
    def get_name(self) -> str:
        return "mock"
```

### IB Executor (To Implement)

**File:** `src/execution/ib_executor.py`

```python
from src.execution.base_executor import BaseExecutor
from ib_insync import IB, Stock, MarketOrder, LimitOrder, util
import pandas as pd
from typing import Dict, Optional
import nest_asyncio

class IBExecutor(BaseExecutor):
    """Interactive Brokers executor for live trading."""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 7497,
                 client_id: int = 2, account: Optional[str] = None):
        self.ib = IB()
        nest_asyncio.apply()
        self.host = host
        self.port = port
        self.client_id = client_id
        self.account = account
        self._connect()
    
    def _connect(self):
        """Connect to IB."""
        if self.ib.isConnected():
            self.ib.disconnect()
        self.ib.connect(self.host, self.port, clientId=self.client_id)
    
    def submit_order(self, ticker: str, quantity: int, side: str,
                    order_type: str = 'MARKET',
                    limit_price: Optional[float] = None) -> Dict:
        """Submit order to IB."""
        contract = Stock(ticker, "SMART", "USD")
        self.ib.qualifyContracts(contract)
        
        # Create order
        if order_type == 'MARKET':
            order = MarketOrder('BUY' if side == 'BUY' else 'SELL', quantity)
        elif order_type == 'LIMIT':
            order = LimitOrder('BUY' if side == 'BUY' else 'SELL', 
                             quantity, limit_price)
        else:
            raise ValueError(f"Unsupported order type: {order_type}")
        
        if self.account:
            order.account = self.account
        
        # Submit order
        trade = self.ib.placeOrder(contract, order)
        
        return {
            'order_id': str(trade.order.orderId),
            'ticker': ticker,
            'quantity': quantity,
            'side': side,
            'status': trade.orderStatus.status,
            'timestamp': trade.orderStatus.submittedTime
        }
    
    def get_positions(self) -> pd.DataFrame:
        """Get current positions from IB."""
        positions = self.ib.positions()
        
        if not positions:
            return pd.DataFrame(columns=['ticker', 'quantity', 'avg_cost'])
        
        pos_data = []
        for pos in positions:
            pos_data.append({
                'ticker': pos.contract.symbol,
                'quantity': pos.position,
                'avg_cost': pos.avgCost
            })
        
        return pd.DataFrame(pos_data)
    
    def get_account_value(self) -> float:
        """Get account value from IB."""
        account_summary = self.ib.accountSummary()
        nav = next((item.value for item in account_summary 
                   if item.tag == 'NetLiquidation'), 0)
        return float(nav)
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel order."""
        # Find order by ID
        for trade in self.ib.openTrades():
            if str(trade.order.orderId) == order_id:
                self.ib.cancelOrder(trade.order)
                return True
        return False
    
    def get_order_status(self, order_id: str) -> Dict:
        """Get order status."""
        for trade in self.ib.openTrades() + self.ib.fills():
            if str(trade.order.orderId) == order_id:
                return {
                    'order_id': str(trade.order.orderId),
                    'status': trade.orderStatus.status,
                    'filled': trade.orderStatus.filled,
                    'remaining': trade.orderStatus.remaining
                }
        return {'status': 'NOT_FOUND'}
    
    def get_name(self) -> str:
        return "ib"
    
    def __del__(self):
        """Cleanup."""
        if hasattr(self, 'ib') and self.ib.isConnected():
            self.ib.disconnect()
```

### Executor Factory

**File:** `src/execution/executor_factory.py`

```python
from src.execution.base_executor import BaseExecutor
from src.execution.mock_executor import MockExecutor
from src.execution.ib_executor import IBExecutor
from typing import Optional
import yaml

class ExecutorFactory:
    """Factory for creating executors based on config."""
    
    @staticmethod
    def create(config: dict) -> BaseExecutor:
        """Create executor from config."""
        mode = config.get('mode', 'backtest')
        executor_type = config.get('executor', 'mock')
        
        if mode == 'backtest' or executor_type == 'mock':
            return MockExecutor(
                initial_capital=config.get('initial_capital', 100000)
            )
        elif executor_type == 'ib_paper':
            ib_config = config.get('ib', {})
            exec_config = config.get('execution', {})
            return IBExecutor(
                host=ib_config.get('host', '127.0.0.1'),
                port=7497,  # Paper trading port
                client_id=ib_config.get('client_id', 2),
                account=exec_config.get('paper_account')
            )
        elif executor_type == 'ib_live':
            ib_config = config.get('ib', {})
            exec_config = config.get('execution', {})
            return IBExecutor(
                host=ib_config.get('host', '127.0.0.1'),
                port=7496,  # Live trading port
                client_id=ib_config.get('client_id', 2),
                account=exec_config.get('live_account')
            )
        else:
            raise ValueError(f"Unknown executor: {executor_type}")
    
    @staticmethod
    def from_config_file(config_path: str = "config/trading_config.yaml") -> BaseExecutor:
        """Load executor from config file."""
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return ExecutorFactory.create(config.get('trading', {}))
```

---

## INTEGRATION WITH EXISTING SYSTEM

### Update test_signals.py

**Changes needed:**

```python
# At top of file
from src.data.provider_factory import DataProviderFactory
from src.execution.executor_factory import ExecutorFactory
import yaml

# Load config
with open('config/trading_config.yaml', 'r') as f:
    config = yaml.safe_load(f)

trading_config = config.get('trading', {})

# Initialize providers
data_provider = DataProviderFactory.from_config_file()
executor = ExecutorFactory.from_config_file()

# Use in backtest/trading logic
def get_price_data(ticker: str, start_date: str, end_date: str = None):
    """Get price data using configured provider."""
    return data_provider.get_historical_data(ticker, start_date, end_date)

def execute_trade(ticker: str, quantity: int, side: str):
    """Execute trade using configured executor."""
    return executor.submit_order(ticker, quantity, side)
```

---

## MODE SWITCHING EXAMPLES

### Backtest Mode
```yaml
trading:
  mode: "backtest"
  data_provider: "csv"
  executor: "mock"
```

### Paper Trading Mode
```yaml
trading:
  mode: "paper"
  data_provider: "ib"
  executor: "ib_paper"
  ib:
    port: 7497  # Paper port
```

### Live Trading Mode
```yaml
trading:
  mode: "live"
  data_provider: "ib"
  executor: "ib_live"
  ib:
    port: 7496  # Live port
```

---

## SUMMARY

**Abstractions Created:**
- ✅ `BaseDataProvider` - Data provider interface
- ✅ `BaseExecutor` - Executor interface
- ✅ Factory pattern for provider/executor creation
- ✅ Config-based mode switching

**Providers:**
- ✅ CSV Provider (backtest)
- ✅ IB Provider (paper/live)

**Executors:**
- ✅ Mock Executor (backtest)
- ✅ IB Executor (paper/live)

**Next Steps:**
1. Port IB components
2. Implement IB executor
3. Update test_signals.py to use abstractions
4. Test mode switching

---

**Status:** ✅ **ARCHITECTURE DESIGNED - READY FOR IMPLEMENTATION**
