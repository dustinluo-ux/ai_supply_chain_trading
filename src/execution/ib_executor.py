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
        order_comment: Optional[str] = None,
        stop_price: Optional[float] = None,
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
            order_comment: Optional ref/tag (e.g. PROHIBITED_LLM_DISCOVERY_LINK, LIVE_SPINE); set on order.orderRef
            stop_price: Optional; stored in return for bracket/stop; caller may place stop separately
            **kwargs: Additional parameters
            
        Returns:
            Dict with order information (includes stop_price, order_comment when provided)
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
            if order_comment is not None and isinstance(order_comment, str):
                order.orderRef = order_comment[:128]  # IB typically allows limited ref length
            
            # Submit order
            trade = self.ib.placeOrder(contract, order)
            
            # Optional: place stop order if stop_price provided (design: implementation detail)
            stop_order_id = None
            if stop_price is not None and quantity > 0:
                try:
                    from ib_insync import Order
                    stop_side = "SELL" if side.upper() == "BUY" else "BUY"
                    stop_order = Order()
                    stop_order.orderType = "STP"
                    stop_order.auxPrice = stop_price
                    stop_order.action = stop_side
                    stop_order.totalQuantity = quantity
                    stop_order.account = self.account
                    if order_comment:
                        stop_order.orderRef = order_comment[:128]
                    stop_trade = self.ib.placeOrder(contract, stop_order)
                    stop_order_id = str(stop_trade.order.orderId)
                except Exception as se:
                    logger.warning("Stop order placement failed (main order still placed): %s", se)
            
            logger.info(f"Order submitted: {side} {quantity} {ticker} ({order_type}) ref={order_comment!r} stop={stop_price}")
            
            out = {
                'order_id': str(trade.order.orderId),
                'ticker': ticker,
                'quantity': quantity,
                'side': side.upper(),
                'order_type': order_type,
                'status': trade.orderStatus.status,
                'filled_quantity': trade.orderStatus.filled,
                'filled_price': trade.orderStatus.avgFillPrice if trade.orderStatus.avgFillPrice else 0.0
            }
            if order_comment is not None:
                out['order_comment'] = order_comment
            if stop_price is not None:
                out['stop_price'] = stop_price
            if stop_order_id is not None:
                out['stop_order_id'] = stop_order_id
            return out
        
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
