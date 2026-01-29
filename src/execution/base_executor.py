"""
Base Executor Interface
Abstract base class for all executors
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import pandas as pd


class BaseExecutor(ABC):
    """Abstract base class for order executors."""
    
    @abstractmethod
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
        Submit an order.
        
        Args:
            ticker: Stock ticker symbol
            quantity: Number of shares/contracts
            side: 'BUY' or 'SELL'
            order_type: Order type ('MARKET', 'LIMIT', etc.)
            limit_price: Limit price (required for LIMIT orders)
            **kwargs: Additional order parameters
            
        Returns:
            Dict with order information
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    def get_positions(self) -> pd.DataFrame:
        """
        Get current positions.
        
        Returns:
            DataFrame with columns: symbol, quantity, avg_cost, market_value
        """
        pass
    
    @abstractmethod
    def get_account_value(self) -> float:
        """
        Get total account value (NAV).
        
        Returns:
            Account value in dollars
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """
        Return executor name.
        
        Returns:
            Executor name string
        """
        pass
