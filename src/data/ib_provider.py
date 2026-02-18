"""
IB Data Provider - Interactive Brokers data provider
Ported and adapted from wealth_signal_mvp_v1/core/data/loader_ibkr.py
"""
import os
import pickle
import time
from typing import Dict, List, Optional
import pandas as pd
import nest_asyncio
from ib_insync import IB, Stock, util, Future, Forex, Crypto

from src.data.base_provider import BaseDataProvider
from src.utils.logger import setup_logger
from src.utils.client_id_rotation import next_client_id

logger = setup_logger()

# Apply nest_asyncio for Jupyter/IPython compatibility
nest_asyncio.apply()


class IBDataProvider(BaseDataProvider):
    """Interactive Brokers data provider."""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 7497, 
                 client_id: Optional[int] = None, cache_dir: Optional[str] = None):
        """
        Initialize IB data provider.
        
        Args:
            host: TWS/IB Gateway host (default: 127.0.0.1)
            port: Port (7497 = paper, 7496 = live)
            client_id: Client ID (if None, uses rotation starting at IBKR_CLIENT_ID_START env, default 99)
            cache_dir: Cache directory for historical data
        """
        self.host = host
        self.port = port
        self.client_id = client_id if client_id is not None else next_client_id()
        self.cache_dir = cache_dir or os.path.join("data", "cache", "ibkr")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self.ib = IB()
        self._connect()
        logger.info(f"IBDataProvider initialized: {host}:{port}, client_id={self.client_id}")
    
    def _connect(self):
        """Connect to TWS/IB Gateway."""
        timeout = 10
        try:
            if self.ib.isConnected():
                self.ib.disconnect()
            
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            
            start_time = time.time()
            while not self.ib.isConnected():
                if time.time() - start_time > timeout:
                    raise TimeoutError("IBKR connection timed out.")
                time.sleep(0.2)
            
            logger.info("Connected to IB TWS/Gateway")
        except Exception as e:
            raise ConnectionError(f"Could not connect to TWS/IBGateway: {str(e)}")
    
    def get_historical_data(
        self,
        ticker: str,
        start_date: str = "2010-01-01",
        end_date: Optional[str] = None,
        exchange: str = "SMART",
        currency: str = "USD",
        **kwargs
    ) -> pd.Series:
        """
        Get historical data from IB with caching.
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD), optional
            exchange: Exchange (default: SMART)
            currency: Currency (default: USD)
            **kwargs: Additional parameters
            
        Returns:
            Series of close prices with datetime index
        """
        # Check cache
        cache_key = f"ibkr_{ticker}_{start_date}_{end_date}_{exchange}_{currency}"
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.pkl")
        
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'rb') as f:
                    cached_data = pickle.load(f)
                    logger.debug(f"Loaded cached data for {ticker}")
                    return cached_data
            except Exception as e:
                logger.warning(f"Cache load failed for {ticker}: {e}")
        
        # Determine contract type
        crypto_tickers = {'BTC', 'ETH', 'LTC', 'BCH', 'SOL', 'ADA', 'XRP', 'DOGE', 'AVAX', 'LINK', 'SUI'}
        fx_tickers = {'DXY'}
        
        if ticker in crypto_tickers:
            contract = Crypto(ticker, exchange, currency)
        elif ticker in fx_tickers:
            contract = Forex(ticker)
        else:
            # Default to stock
            contract = Stock(ticker, exchange, currency)
        
        # Calculate duration
        if end_date:
            end_dt = pd.to_datetime(end_date)
            start_dt = pd.to_datetime(start_date)
            years = (end_dt - start_dt).days / 365.25
            duration_str = f'{int(years)} Y' if years >= 1 else f'{int((end_dt - start_dt).days)} D'
        else:
            duration_str = '2 Y'
        
        # Request historical data
        try:
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
                logger.warning(f"No data returned from IBKR for {ticker}")
                return pd.Series(dtype=float)
            
            df = util.df(bars)
            df['date'] = pd.to_datetime(df['date'])
            df['date'] = df['date'].dt.tz_localize(None)
            df.set_index("date", inplace=True)
            df = df[df.index >= pd.Timestamp(start_date)]
            
            if df.empty:
                logger.warning(f"Empty dataframe after filtering for {ticker}")
                return pd.Series(dtype=float)
            
            series = df["close"].rename(ticker)
            
            # Save to cache
            try:
                with open(cache_path, 'wb') as f:
                    pickle.dump(series, f)
            except Exception as e:
                logger.warning(f"Cache save failed for {ticker}: {e}")
            
            logger.debug(f"Loaded {len(series)} data points for {ticker} from IB")
            return series
            
        except Exception as e:
            logger.error(f"Error fetching data for {ticker}: {e}")
            return pd.Series(dtype=float)
    
    def get_current_price(self, ticker: str) -> float:
        """
        Get current/latest price from IB.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Current price
        """
        try:
            contract = Stock(ticker, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            ticker_obj = self.ib.reqMktData(contract, '', False, False)
            self.ib.sleep(1)  # Wait for data
            
            if ticker_obj.marketPrice():
                return float(ticker_obj.marketPrice())
            elif ticker_obj.last:
                return float(ticker_obj.last)
            else:
                # Fallback to latest historical
                series = self.get_historical_data(ticker, start_date="2020-01-01")
                if not series.empty:
                    return float(series.iloc[-1])
                return 0.0
        except Exception as e:
            logger.error(f"Error getting current price for {ticker}: {e}")
            return 0.0

    # Tick type 8 = Last size (volume) for US equities; IB reports in 100s, so we apply x100
    US_EQUITY_VOLUME_MULTIPLIER = 100

    def get_realtime_volume(self, ticker: str, apply_us_equity_multiplier: bool = True) -> float:
        """
        Get real-time volume via reqMktData with genericTickList Tick 8.

        For US equities, IB reports volume in 100s; apply x100 to get actual volume.

        Args:
            ticker: Stock ticker symbol.
            apply_us_equity_multiplier: If True, multiply by 100 for US equities (default True).

        Returns:
            Volume (actual shares if apply_us_equity_multiplier=True for US equities).
        """
        try:
            contract = Stock(ticker, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            # genericTickList: "8" = Last size (volume)
            ticker_obj = self.ib.reqMktData(contract, genericTickList="8", snapshot=False)
            self.ib.sleep(1)
            vol = 0.0
            if hasattr(ticker_obj, "lastSize") and ticker_obj.lastSize is not None:
                vol = float(ticker_obj.lastSize)
            elif hasattr(ticker_obj, "volume") and ticker_obj.volume is not None:
                vol = float(ticker_obj.volume)
            self.ib.cancelMktData(contract)
            if apply_us_equity_multiplier and vol is not None:
                vol = vol * self.US_EQUITY_VOLUME_MULTIPLIER
            return vol
        except Exception as e:
            logger.error(f"Error getting realtime volume for {ticker}: {e}")
            return 0.0
    
    def get_account_info(self) -> Dict:
        """
        Get account summary, positions, and margin information.
        
        Returns:
            Dict with 'margin_info' and 'positions'
        """
        try:
            account_summary = self.ib.accountSummary()
            positions = self.ib.positions()
            
            margin_info = {
                item.tag: item.value for item in account_summary 
                if item.tag in ['NetLiquidation', 'TotalCashValue', 'EquityWithLoanValue',
                              'InitMarginReq', 'MaintMarginReq', 'BuyingPower', 'AvailableFunds',
                              'ExcessLiquidity', 'FullInitMarginReq', 'FullMaintMarginReq',
                              'FullAvailableFunds', 'FullExcessLiquidity']
            }
            
            pos_list = [
                {
                    'symbol': pos.contract.symbol,
                    'position': pos.position,
                    'avgCost': pos.avgCost
                }
                for pos in positions
            ]
            
            return {
                'margin_info': margin_info,
                'positions': pos_list
            }
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {'margin_info': {}, 'positions': []}
    
    def get_name(self) -> str:
        """Return provider name."""
        return "IB"
    
    def is_available(self) -> bool:
        """Check if IB connection is active."""
        return self.ib.isConnected()
    
    def disconnect(self):
        """Disconnect from IB."""
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected from IB")
    
    def __del__(self):
        """Ensure IB connection is closed when object is destroyed."""
        try:
            if hasattr(self, 'ib') and self.ib.isConnected():
                self.ib.disconnect()
        except:
            pass
