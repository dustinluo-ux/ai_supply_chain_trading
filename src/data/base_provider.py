"""
Base Data Provider Interface
Abstract base class for all data providers
"""
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
        """
        Get historical price data.
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD), optional
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Series of prices with datetime index
        """
        pass
    
    @abstractmethod
    def get_current_price(self, ticker: str) -> float:
        """
        Get current/latest price.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Current price as float
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """
        Return provider name.
        
        Returns:
            Provider name string
        """
        pass
    
    def is_available(self) -> bool:
        """
        Check if provider is available/connected.
        
        Returns:
            True if available, False otherwise
        """
        return True
