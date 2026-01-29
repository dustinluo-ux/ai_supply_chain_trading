"""
Backtest Engine using vectorbt
Implements weekly rebalancing strategy with risk controls
"""
import os
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

try:
    import vectorbt as vbt
except ImportError:
    raise ImportError("vectorbt required. Install with: pip install vectorbt")

from src.utils.logger import setup_logger

logger = setup_logger()


class BacktestEngine:
    """Backtesting engine for AI supply chain strategy"""
    
    def __init__(self, initial_capital: float = 100000, trading_fees: float = 0.001,
                 stop_loss_pct: float = -0.08, max_drawdown_pct: float = -0.15):
        self.initial_capital = initial_capital
        self.trading_fees = trading_fees
        self.stop_loss_pct = stop_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        logger.info(f"BacktestEngine initialized: capital=${initial_capital:,.0f}, fees={trading_fees*100:.2f}%")
    
    def load_price_data(self, tickers: List[str], data_dir: str = "data/prices",
                       start_date: str = "2023-01-01", end_date: str = "2024-12-31") -> pd.DataFrame:
        """Load and combine price data for multiple tickers"""
        price_data = {}
        
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        for ticker in tickers:
            price_path = os.path.join(data_dir, f"{ticker}.parquet")
            
            if not os.path.exists(price_path):
                logger.warning(f"No price data for {ticker}, skipping")
                continue
            
            try:
                df = pd.read_parquet(price_path)
                
                # Ensure datetime index
                if not isinstance(df.index, pd.DatetimeIndex):
                    if 'date' in df.columns:
                        df = df.set_index('date')
                    else:
                        logger.warning(f"Could not set datetime index for {ticker}")
                        continue
                
                # Filter by date range
                df = df[(df.index >= start_dt) & (df.index <= end_dt)]
                
                if not df.empty and 'close' in df.columns:
                    price_data[ticker] = df['close']
            
            except Exception as e:
                logger.error(f"Error loading {ticker}: {e}")
                continue
        
        if not price_data:
            logger.error("No price data loaded")
            return pd.DataFrame()
        
        # Combine into DataFrame
        prices_df = pd.DataFrame(price_data)
        prices_df = prices_df.sort_index()
        
        logger.info(f"Loaded price data for {len(prices_df.columns)} tickers, {len(prices_df)} dates")
        return prices_df
    
    def load_signals(self, data_dir: str = "data/signals", date: Optional[str] = None, 
                    mode: str = "full_with_news") -> pd.DataFrame:
        """Load signal rankings"""
        mode_suffix = "_technical" if mode == "technical_only" else ""
        
        if date:
            signal_path = os.path.join(data_dir, f"top_stocks_{date}{mode_suffix}.csv")
        else:
            # Get latest signal file (try mode-specific first, then fallback)
            signal_files = [f for f in os.listdir(data_dir) 
                          if f.startswith("top_stocks_") and f.endswith(f"{mode_suffix}.csv")]
            
            if not signal_files:
                # Fallback to any signal file
                signal_files = [f for f in os.listdir(data_dir) if f.startswith("top_stocks_") and f.endswith(".csv")]
            
            if not signal_files:
                logger.error("No signal files found")
                return pd.DataFrame()
            
            # Sort by filename (which includes date)
            signal_files.sort(reverse=True)
            signal_path = os.path.join(data_dir, signal_files[0])
        
        if not os.path.exists(signal_path):
            logger.error(f"Signal file not found: {signal_path}")
            return pd.DataFrame()
        
        try:
            signals = pd.read_csv(signal_path)
            return signals
        except Exception as e:
            logger.error(f"Error loading signals: {e}")
            return pd.DataFrame()
    
    def generate_weekly_signals(self, prices_df: pd.DataFrame, portfolio_size: int = 10,
                                buffer_size: int = 15, start_date: str = "2023-01-01",
                                end_date: str = "2024-12-31", mode: str = "full_with_news") -> pd.DataFrame:
        """
        Generate weekly rebalancing signals
        
        Strategy:
        - Every Monday: select top N stocks
        - Hold until stock drops out of top M (buffer)
        - Weekly rebalance
        """
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        # Get all Mondays in date range
        mondays = pd.date_range(start=start_dt, end=end_dt, freq='W-MON')
        
        # Initialize positions DataFrame
        positions = pd.DataFrame(0.0, index=prices_df.index, columns=prices_df.columns)
        
        current_holdings = set()
        
        logger.info(f"Generating weekly signals for {len(mondays)} rebalance dates...")
        
        for monday in mondays:
            # Get signal for this date (use previous week's signal)
            signal_date = (monday - timedelta(days=7)).strftime("%Y-%m-%d")
            signals = self.load_signals(date=signal_date, mode=mode)
            
            if signals.empty:
                # Try latest available signal
                signals = self.load_signals(date=None, mode=mode)
            
            if signals.empty:
                logger.warning(f"No signals available for {monday}")
                continue
            
            # Get top N stocks
            top_stocks = signals.head(portfolio_size)['ticker'].tolist()
            top_stocks_set = set(top_stocks)
            
            # Get buffer stocks (top M)
            buffer_stocks = signals.head(buffer_size)['ticker'].tolist()
            buffer_stocks_set = set(buffer_stocks)
            
            # Exit stocks that dropped out of buffer
            to_exit = current_holdings - buffer_stocks_set
            
            # Enter new stocks from top N
            to_enter = top_stocks_set - current_holdings
            
            # Update holdings
            current_holdings = (current_holdings - to_exit) | (top_stocks_set & buffer_stocks_set)
            
            # Set positions (equal weight)
            if current_holdings:
                weight_per_stock = 1.0 / len(current_holdings)
                
                # Find next trading day
                next_trading_day = prices_df.index[prices_df.index >= monday]
                if len(next_trading_day) > 0:
                    rebalance_date = next_trading_day[0]
                    
                    # Set positions for all future dates until next rebalance
                    future_dates = prices_df.index[prices_df.index >= rebalance_date]
                    if len(future_dates) > 0:
                        next_monday_idx = mondays[mondays > monday]
                        if len(next_monday_idx) > 0:
                            end_rebalance = next_monday_idx[0]
                            future_dates = future_dates[future_dates < end_rebalance]
                        
                        for ticker in current_holdings:
                            if ticker in positions.columns:
                                positions.loc[future_dates, ticker] = weight_per_stock
            
            logger.debug(f"{monday}: Holdings={len(current_holdings)}, Enter={len(to_enter)}, Exit={len(to_exit)}")
        
        return positions
    
    def apply_stop_loss(self, prices_df: pd.DataFrame, positions_df: pd.DataFrame) -> pd.DataFrame:
        """Apply stop loss: exit position if drops -8% from entry"""
        positions_with_stop = positions_df.copy()
        
        for ticker in positions_df.columns:
            prices = prices_df[ticker]
            positions = positions_df[ticker]
            
            entry_price = None
            entry_date = None
            
            for date in positions_df.index:
                current_pos = positions.loc[date]
                current_price = prices.loc[date]
                
                # Check if entering position
                if current_pos > 0 and (entry_price is None or entry_date is None):
                    entry_price = current_price
                    entry_date = date
                
                # Check stop loss
                if entry_price is not None and current_price < entry_price * (1 + self.stop_loss_pct):
                    # Stop loss triggered
                    positions_with_stop.loc[date:, ticker] = 0.0
                    entry_price = None
                    entry_date = None
                    logger.debug(f"Stop loss triggered for {ticker} on {date}")
                
                # Check if exiting position
                if current_pos == 0 and entry_price is not None:
                    entry_price = None
                    entry_date = None
        
        return positions_with_stop
    
    def run_backtest(self, prices_df: pd.DataFrame, positions_df: pd.DataFrame) -> Dict:
        """Run backtest using vectorbt"""
        # Calculate returns
        returns = prices_df.pct_change()
        
        # Calculate portfolio returns
        portfolio_returns = (positions_df.shift(1) * returns).sum(axis=1)
        
        # Apply trading fees (on rebalancing)
        rebalance_dates = positions_df.diff().abs().sum(axis=1) > 0.01
        portfolio_returns[rebalance_dates] -= self.trading_fees
        
        # Calculate cumulative returns
        cumulative_returns = (1 + portfolio_returns).cumprod()
        
        # Calculate metrics
        total_return = cumulative_returns.iloc[-1] - 1
        
        # Sharpe ratio (annualized, assuming 252 trading days)
        if portfolio_returns.std() > 0:
            sharpe_ratio = (portfolio_returns.mean() * 252) / (portfolio_returns.std() * np.sqrt(252))
        else:
            sharpe_ratio = 0.0
        
        # Max drawdown
        running_max = cumulative_returns.expanding().max()
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # Win rate (positive return days)
        positive_days = (portfolio_returns > 0).sum()
        total_days = len(portfolio_returns[portfolio_returns != 0])
        win_rate = positive_days / total_days if total_days > 0 else 0.0
        
        # Number of trades
        num_trades = rebalance_dates.sum()
        
        # Check max drawdown kill switch
        if max_drawdown < self.max_drawdown_pct:
            logger.warning(f"Max drawdown {max_drawdown:.2%} exceeded limit {self.max_drawdown_pct:.2%}")
        
        results = {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'num_trades': num_trades,
            'cumulative_returns': cumulative_returns,
            'portfolio_returns': portfolio_returns,
            'positions': positions_df
        }
        
        logger.info(f"Backtest complete: Return={total_return:.2%}, Sharpe={sharpe_ratio:.2f}, "
                   f"MaxDD={max_drawdown:.2%}, WinRate={win_rate:.2%}")
        
        return results
    
    def compare_to_benchmark(self, portfolio_returns: pd.Series, benchmark_ticker: str = "SPY",
                            start_date: str = "2023-01-01", end_date: str = "2024-12-31") -> Dict:
        """Compare strategy to benchmark (SPY)"""
        try:
            import yfinance as yf
            
            benchmark = yf.download(benchmark_ticker, start=start_date, end=end_date, progress=False)
            
            if benchmark.empty:
                logger.warning(f"Could not load benchmark {benchmark_ticker}")
                return {}
            
            benchmark_returns = benchmark['Close'].pct_change()
            
            # Align dates
            aligned_returns = portfolio_returns.reindex(benchmark_returns.index).fillna(0)
            aligned_benchmark = benchmark_returns.reindex(portfolio_returns.index).fillna(0)
            
            # Calculate excess returns
            excess_returns = aligned_returns - aligned_benchmark
            
            # Cumulative comparison
            portfolio_cum = (1 + aligned_returns).cumprod()
            benchmark_cum = (1 + aligned_benchmark).cumprod()
            
            results = {
                'portfolio_total_return': portfolio_cum.iloc[-1] - 1,
                'benchmark_total_return': benchmark_cum.iloc[-1] - 1,
                'excess_return': (portfolio_cum.iloc[-1] / benchmark_cum.iloc[-1] - 1) if benchmark_cum.iloc[-1] > 0 else 0,
                'portfolio_cumulative': portfolio_cum,
                'benchmark_cumulative': benchmark_cum
            }
            
            return results
        
        except Exception as e:
            logger.error(f"Error comparing to benchmark: {e}")
            return {}


if __name__ == "__main__":
    # Test script
    logger = setup_logger()
    
    engine = BacktestEngine()
    
    # This requires price data and signals to be generated first
    # Run Phase 1 and Phase 2 first
    
    print("Backtest engine ready. Run full backtest via run_phase3_backtest.py")
