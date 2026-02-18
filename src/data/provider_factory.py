"""
Data Provider Factory - Creates data providers based on configuration
"""
import yaml
import os
from typing import Optional
from src.data.base_provider import BaseDataProvider
from src.data.csv_provider import CSVDataProvider
from src.data.ib_provider import IBDataProvider
from src.utils.logger import setup_logger

logger = setup_logger()


class DataProviderFactory:
    """Factory for creating data providers."""
    
    @staticmethod
    def create(provider_type: str, **kwargs) -> BaseDataProvider:
        """
        Create a data provider instance.
        
        Args:
            provider_type: Type of provider ('csv', 'ib')
            **kwargs: Provider-specific parameters
            
        Returns:
            Data provider instance
        """
        if provider_type.lower() == 'csv':
            data_dir = kwargs.get('data_dir', 'data/prices')
            return CSVDataProvider(data_dir=data_dir)
        
        elif provider_type.lower() == 'ib':
            host = kwargs.get('host', '127.0.0.1')
            port = kwargs.get('port', 7497)
            client_id = kwargs.get('client_id', None)
            cache_dir = kwargs.get('cache_dir', None)
            return IBDataProvider(host=host, port=port, client_id=client_id, cache_dir=cache_dir)
        
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")
    
    @staticmethod
    def from_config_file(config_path: Optional[str] = None) -> BaseDataProvider:
        """
        Create provider from config file.
        
        Args:
            config_path: Path to config file (default: config/trading_config.yaml)
            
        Returns:
            Data provider instance
        """
        if config_path is None:
            config_path = os.path.join('config', 'trading_config.yaml')
        
        if not os.path.exists(config_path):
            logger.warning(f"Config file not found: {config_path}, using CSV provider")
            return CSVDataProvider()
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            trading_config = config.get('trading', {})
            provider_type = trading_config.get('data_provider', 'csv')
            
            # Get provider-specific config
            if provider_type == 'ib':
                ib_config = trading_config.get('ib', {})
                data_config = trading_config.get('data', {})
                return IBDataProvider(
                    host=ib_config.get('host', '127.0.0.1'),
                    port=ib_config.get('port', 7497),
                    client_id=ib_config.get('client_id', None),
                    cache_dir=data_config.get('cache_dir', None)
                )
            else:
                data_config = trading_config.get('data', {})
                return CSVDataProvider(
                    data_dir=data_config.get('csv_dir', 'data/prices')
                )
        
        except Exception as e:
            logger.error(f"Error loading config: {e}, using CSV provider")
            return CSVDataProvider()
