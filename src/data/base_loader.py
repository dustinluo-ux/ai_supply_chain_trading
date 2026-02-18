"""
Base class for data loaders - source-agnostic design
Allows easy addition of new data sources (SEC filings, earnings, social media, etc.)
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class BaseDataLoader(ABC):
    """Abstract base class for all data loaders"""
    
    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def load(self, *args, **kwargs):
        """Load data from source"""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Return loader name"""
        pass
    
    def _handle_error(self, error: Exception, context: str = ""):
        """Centralized error handling"""
        self.logger.error(f"Error in {self.__class__.__name__}: {context} - {error}")
        raise
