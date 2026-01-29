"""
IB Executor - Interactive Brokers order execution
"""
import pandas as pd
from typing import Dict, Optional
from ib_insync import MarketOrder, LimitOrder, Order
from src.execution.base_executor import BaseExecutor
from src.data.ib_provider import IBDataProvider
from src.utils.logger import setup_logger

logger = setup_logger()


class IBExecutor(BaseExecutor):
    """Interactive Brokers executor for live/paper trading."""
    
    def __init__(self, ib_provider: IBDataProvider, account: str):
        """
        Initialize IB executor.
        
        Args:
            ib_provider: IBDataProvider instance (must be connected)
            account: Account number (paper or live)
        """
        self.ib_provider = ib_provider
        self.ib = ib_provider.ib
        self.account = account
        logger.info(f"IBExecutor initialized for account: {account}")
    
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
        Submit order to IB.
        
        Args:
            ticker: Stock ticker
            quantity: Number of shares
            side: 'BUY' or 'SELL'
            order_type: 'MARKET' or 'LIMIT'
            limit_price: Required for LIMIT orders
            **kwargs: Additional parameters
            
        Returns:
            Dict with order information
        """
        from ib_insync import Stock
        
        try:
            # Create contract
            contract = Stock(ticker, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            # Create order
            if order_type.upper() == 'MARKET':
                order = MarketOrder(side.upper(), quantity)
            elif order_type.upper() == 'LIMIT':
                if limit_price is None:
                    raise ValueError("limit_price required for LIMIT orders")
                order = LimitOrder(side.upper(), quantity, limit_price)
            else:
                raise ValueError(f"Unsupported order type: {order_type}")
            
            order.account = self.account
            
            # Submit order
            trade = self.ib.placeOrder(contract, order)
            
            logger.info(f"Order submitted: {side} {quantity} {ticker} ({order_type})")
            
            return {
                'order_id': str(trade.order.orderId),
                'ticker': ticker,
                'quantity': quantity,
                'side': side.upper(),
                'order_type': order_type,
                'status': trade.orderStatus.status,
                'filled_quantity': trade.orderStatus.filled,
                'filled_price': trade.orderStatus.avgFillPrice if trade.orderStatus.avgFillPrice else 0.0
            }
        
        except Exception as e:
            logger.error(f"Error submitting order for {ticker}: {e}")
            raise
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if successful
        """
        try:
            # Find order
            trades = self.ib.openTrades()
            for trade in trades:
                if str(trade.order.orderId) == order_id:
                    self.ib.cancelOrder(trade.order)
                    logger.info(f"Order cancelled: {order_id}")
                    return True
            
            logger.warning(f"Order not found: {order_id}")
            return False
        
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def get_positions(self) -> pd.DataFrame:
        """
        Get current positions from IB.
        
        Returns:
            DataFrame with positions
        """
        try:
            positions = self.ib.positions()
            
            if not positions:
                return pd.DataFrame(columns=['symbol', 'quantity', 'avg_cost', 'market_value'])
            
            data = []
            for pos in positions:
                if pos.position != 0:
                    data.append({
                        'symbol': pos.contract.symbol,
                        'quantity': pos.position,
                        'avg_cost': pos.avgCost,
                        'market_value': pos.position * pos.avgCost  # Simplified
                    })
            
            return pd.DataFrame(data)
        
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return pd.DataFrame(columns=['symbol', 'quantity', 'avg_cost', 'market_value'])
    
    def get_account_value(self) -> float:
        """
        Get account value from IB.
        
        Returns:
            Account value (NAV)
        """
        try:
            account_info = self.ib_provider.get_account_info()
            margin_info = account_info.get('margin_info', {})
            nav = float(margin_info.get('NetLiquidation', 0))
            if nav == 0:
                nav = float(margin_info.get('TotalCashValue', 0))
            return nav
        except Exception as e:
            logger.error(f"Error getting account value: {e}")
            return 0.0
    
    def get_name(self) -> str:
        """Return executor name."""
        return "IB"
