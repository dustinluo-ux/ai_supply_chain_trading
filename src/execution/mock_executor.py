"""
Mock Executor - For backtesting (no real orders)
"""
import pandas as pd
from typing import Dict, List, Optional
from src.execution.base_executor import BaseExecutor
from src.utils.logger import setup_logger

logger = setup_logger()


class MockExecutor(BaseExecutor):
    """Mock executor for backtesting - logs orders but doesn't execute."""
    
    def __init__(self, initial_capital: float = 100000.0):
        """
        Initialize mock executor.
        
        Args:
            initial_capital: Starting capital for simulation
        """
        self.initial_capital = initial_capital
        self.positions = {}  # ticker -> quantity
        self.orders = []  # List of submitted orders
        self.account_value = initial_capital
        logger.info(f"MockExecutor initialized with capital: ${initial_capital:,.2f}")
    
    def submit_order(
        self,
        ticker: str,
        quantity: int,
        side: str,
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
        **kwargs
    ) -> Dict:
        """
        Submit a mock order (logs but doesn't execute).
        
        Args:
            ticker: Stock ticker
            quantity: Number of shares
            side: 'BUY' or 'SELL'
            order_type: Order type
            limit_price: Limit price (ignored for mock)
            **kwargs: Additional parameters
            
        Returns:
            Dict with order information
        """
        order_id = f"MOCK_{len(self.orders)}"
        
        # Update positions (simplified - no price tracking)
        current_qty = self.positions.get(ticker, 0)
        if side.upper() == 'BUY':
            new_qty = current_qty + quantity
        elif side.upper() == 'SELL':
            new_qty = current_qty - quantity
        else:
            logger.warning(f"Unknown side: {side}")
            new_qty = current_qty
        
        self.positions[ticker] = new_qty
        
        order_info = {
            'order_id': order_id,
            'ticker': ticker,
            'quantity': quantity,
            'side': side.upper(),
            'order_type': order_type,
            'status': 'FILLED',
            'filled_quantity': quantity,
            'filled_price': 0.0  # Mock doesn't track prices
        }
        
        self.orders.append(order_info)
        logger.info(f"Mock order submitted: {side} {quantity} {ticker}")
        
        return order_info
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a mock order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if found and cancelled
        """
        for order in self.orders:
            if order['order_id'] == order_id:
                order['status'] = 'CANCELLED'
                logger.info(f"Mock order cancelled: {order_id}")
                return True
        return False
    
    def get_positions(self) -> pd.DataFrame:
        """
        Get current mock positions.
        
        Returns:
            DataFrame with positions
        """
        if not self.positions:
            return pd.DataFrame(columns=['symbol', 'quantity', 'avg_cost', 'market_value'])
        
        data = []
        for ticker, qty in self.positions.items():
            if qty != 0:
                data.append({
                    'symbol': ticker,
                    'quantity': qty,
                    'avg_cost': 0.0,  # Mock doesn't track costs
                    'market_value': 0.0  # Mock doesn't track market values
                })
        
        return pd.DataFrame(data)
    
    def get_account_value(self) -> float:
        """
        Get account value (returns initial capital for mock).
        
        Returns:
            Account value
        """
        return self.account_value
    
    def get_name(self) -> str:
        """Return executor name."""
        return "Mock"
    
    def reset(self):
        """Reset executor state (for new backtest)."""
        self.positions = {}
        self.orders = []
        self.account_value = self.initial_capital
        logger.info("MockExecutor reset")
