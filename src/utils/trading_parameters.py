"""
Trading Parameters Manager - Watchlist and parameter management
Ported from wealth_signal_mvp_v1/core/utils/trading_parameters.py
"""
import os
import pandas as pd
from typing import Dict, List, Optional, Union
from src.utils.logger import setup_logger

logger = setup_logger()


class TradingParameters:
    """
    Manages trading parameters and watchlist.
    
    Expects:
    - assets/watchlist.csv: CSV with columns including 'enabled', 'type', 'symbol', 'timeframe', 'rolling_window'
    - assets/parameters.csv: CSV with columns 'parameter' and 'value'
    """
    
    def __init__(self, base_path: Optional[str] = None, assets_dir: Optional[str] = None):
        """
        Initialize trading parameters manager.
        
        Args:
            base_path: Base path for project (default: current directory)
            assets_dir: Directory containing watchlist.csv and parameters.csv
                       (default: assets/ relative to base_path)
        """
        if base_path is None:
            base_path = os.path.abspath(os.path.dirname(__file__))
            # Go up to project root
            base_path = os.path.dirname(os.path.dirname(base_path))
        
        self.base_path = base_path
        
        if assets_dir is None:
            assets_dir = os.path.join(base_path, 'assets')
        self.assets_dir = assets_dir
        
        self._watchlist = None
        self._parameters = None
        self._last_load_time = None
        
        logger.info(f"TradingParameters initialized: assets_dir={assets_dir}")
    
    @property
    def watchlist(self) -> pd.DataFrame:
        """
        Get active trading instruments with their parameters.
        
        Returns:
            DataFrame with enabled instruments
        """
        watchlist_path = os.path.join(self.assets_dir, 'watchlist.csv')
        if not os.path.exists(watchlist_path):
            logger.warning(f"Watchlist file not found: {watchlist_path}")
            return pd.DataFrame()
        
        try:
            # Read and filter for enabled instruments
            df = pd.read_csv(watchlist_path, comment='#')
            if 'enabled' in df.columns:
                return df[df['enabled'] == True]
            else:
                logger.warning("No 'enabled' column in watchlist, returning all")
                return df
        except Exception as e:
            logger.error(f"Error reading watchlist: {e}")
            return pd.DataFrame()
    
    @property
    def parameters(self) -> Dict[str, Union[float, str]]:
        """
        Get current trading parameters.
        
        Returns:
            Dict mapping parameter name to value
        """
        params_path = os.path.join(self.assets_dir, 'parameters.csv')
        if not os.path.exists(params_path):
            logger.warning(f"Parameters file not found: {params_path}")
            return {}
        
        try:
            df = pd.read_csv(params_path)
            if 'parameter' in df.columns and 'value' in df.columns:
                return df.set_index('parameter')['value'].to_dict()
            else:
                logger.warning("Parameters file missing required columns")
                return {}
        except Exception as e:
            logger.error(f"Error reading parameters: {e}")
            return {}
    
    def get_assets_by_type(self, asset_type: str) -> List[str]:
        """
        Get list of enabled assets for a specific type.
        
        Args:
            asset_type: Asset type (e.g., 'stock', 'crypto', 'future')
            
        Returns:
            List of asset symbols
        """
        df = self.watchlist
        if df.empty or 'type' not in df.columns:
            return []
        
        filtered = df[df['type'] == asset_type]
        if 'symbol' in filtered.columns:
            return filtered['symbol'].tolist()
        return []
    
    def get_asset_params(self, symbol: str) -> Dict:
        """
        Get parameters for a specific asset.
        
        Args:
            symbol: Asset symbol
            
        Returns:
            Dict with asset parameters
        """
        df = self.watchlist
        if df.empty:
            raise ValueError("Watchlist is empty")
        
        if 'symbol' not in df.columns:
            raise ValueError("Watchlist missing 'symbol' column")
        
        asset_row = df[df['symbol'] == symbol]
        if asset_row.empty:
            raise ValueError(f"Asset not found in watchlist: {symbol}")
        
        return asset_row.iloc[0].to_dict()
    
    def get_timeframe(self, symbol: str) -> str:
        """
        Get timeframe for a specific asset.
        
        Args:
            symbol: Asset symbol
            
        Returns:
            Timeframe string
        """
        params = self.get_asset_params(symbol)
        return params.get('timeframe', '1d')
    
    def get_rolling_window(self, symbol: str) -> str:
        """
        Get rolling window for a specific asset.
        
        Args:
            symbol: Asset symbol
            
        Returns:
            Rolling window string
        """
        params = self.get_asset_params(symbol)
        return params.get('rolling_window', '252')
