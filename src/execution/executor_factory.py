"""
Executor Factory - Creates executors based on configuration
"""
import yaml
import os
from typing import Optional
from src.execution.base_executor import BaseExecutor
from src.execution.mock_executor import MockExecutor
from src.execution.ib_executor import IBExecutor
from src.data.provider_factory import DataProviderFactory
from src.utils.logger import setup_logger

logger = setup_logger()


class ExecutorFactory:
    """Factory for creating executors."""
    
    @staticmethod
    def create(executor_type: str, data_provider=None, **kwargs) -> BaseExecutor:
        """
        Create an executor instance.
        
        Args:
            executor_type: Type of executor ('mock', 'ib_paper', 'ib_live')
            data_provider: Optional data provider (for IB executor)
            **kwargs: Executor-specific parameters
            
        Returns:
            Executor instance
        """
        if executor_type.lower() == 'mock':
            initial_capital = kwargs.get('initial_capital', 100000.0)
            return MockExecutor(initial_capital=initial_capital)
        
        elif executor_type.lower() in ['ib_paper', 'ib_live']:
            if data_provider is None:
                # Create IB provider if not provided
                host = kwargs.get('host', '127.0.0.1')
                port = kwargs.get('port', 7497)
                client_id = kwargs.get('client_id', None)
                from src.data.ib_provider import IBDataProvider
                data_provider = IBDataProvider(host=host, port=port, client_id=client_id)
            
            account = kwargs.get('account', None)
            if account is None:
                raise ValueError("Account number required for IB executor")
            
            return IBExecutor(ib_provider=data_provider, account=account)
        
        else:
            raise ValueError(f"Unknown executor type: {executor_type}")
    
    @staticmethod
    def from_config_file(config_path: Optional[str] = None) -> BaseExecutor:
        """
        Create executor from config file.
        
        Args:
            config_path: Path to config file (default: config/trading_config.yaml)
            
        Returns:
            Executor instance
        """
        if config_path is None:
            config_path = os.path.join('config', 'trading_config.yaml')
        
        if not os.path.exists(config_path):
            logger.warning(f"Config file not found: {config_path}, using Mock executor")
            return MockExecutor()
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            trading_config = config.get('trading', {})
            executor_type = trading_config.get('executor', 'mock')
            mode = trading_config.get('mode', 'backtest')
            
            # Get executor-specific config
            execution_config = trading_config.get('execution', {})
            initial_capital = trading_config.get('initial_capital', 100000.0)
            
            if executor_type in ['ib_paper', 'ib_live']:
                # Create IB data provider
                ib_config = trading_config.get('ib', {})
                data_provider = DataProviderFactory.create('ib', **ib_config)
                
                # Get account number
                if executor_type == 'ib_paper':
                    account = execution_config.get('paper_account', None)
                else:
                    account = execution_config.get('live_account', None)
                
                if account is None:
                    logger.warning("No account number in config, using Mock executor")
                    return MockExecutor(initial_capital=initial_capital)
                
                return IBExecutor(ib_provider=data_provider, account=account)
            
            else:
                # Mock executor
                return MockExecutor(initial_capital=initial_capital)
        
        except Exception as e:
            logger.error(f"Error loading config: {e}, using Mock executor")
            return MockExecutor()
