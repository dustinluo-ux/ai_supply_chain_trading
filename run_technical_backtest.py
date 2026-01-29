"""
Technical-Only Backtest
Runs backtest using ONLY technical indicators (no news/LLM data required)
Perfect for testing infrastructure without historical news data
"""
import sys
import os
import yaml
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
import argparse
import traceback

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logger
from src.utils.defensive import (
    set_debug_mode, with_timeout, ProgressLogger,
    safe_read_yaml, safe_read_parquet, safe_write_parquet,
    safe_read_csv, safe_write_csv, TimeoutError, DEBUG_MODE
)
from src.data.price_fetcher import PriceFetcher
from src.signals.technical_indicators import TechnicalIndicators
from src.signals.signal_combiner import SignalCombiner
from src.backtest.backtest_engine import BacktestEngine

logger = setup_logger()

# Set style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")


def load_config():
    """Load configuration with error handling"""
    try:
        config_path = project_root / "config" / "config.yaml"
        logger.info(f"Loading config from: {config_path}")
        return safe_read_yaml(str(config_path))
    except FileNotFoundError as e:
        logger.error(f"Config file not found: {config_path}")
        raise
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        logger.error(traceback.format_exc())
        raise


@with_timeout(timeout_seconds=300, operation_name="Generate Technical Signals")
def generate_technical_signals_weekly(config, prices_df):
    """
    Generate weekly technical signals for all dates in backtest period
    
    Returns:
        Dict mapping date strings to DataFrames of top stocks
    """
    logger.info("Generating weekly technical signals...")
    
    try:
        # Initialize components
        tech_indicators = TechnicalIndicators(
            data_dir="data/prices",
            output_dir="data"
        )
        
        signal_combiner = SignalCombiner(
            data_dir="data",
            output_dir="data/signals"
        )
        
        # Get all Mondays in date range
        start_date = pd.to_datetime(config['data']['date_range']['start'])
        end_date = pd.to_datetime(config['data']['date_range']['end'])
        mondays = pd.date_range(start=start_date, end=end_date, freq='W-MON')
        
        weekly_signals = {}
        
        # Calculate technical indicators for all tickers
        tickers = prices_df.columns.tolist()
        logger.info(f"Calculating technical indicators for {len(tickers)} tickers...")
        
        # Progress logging for technical indicators
        progress = ProgressLogger(interval_seconds=10, operation_name="Technical Indicators")
        progress.start(total_items=len(tickers))
        
        try:
            indicators_df = tech_indicators.process_all_tickers(
                tickers,
                short_momentum=config['technical']['momentum_short'],
                long_momentum=config['technical']['momentum_long'],
                volume_window=config['technical']['volume_window'],
                rsi_period=config['technical']['rsi_period'],
                bb_period=config['technical']['bollinger_period'],
                bb_std=config['technical']['bollinger_std']
            )
        finally:
            progress.finish()
        
        if indicators_df.empty:
            logger.error("No technical indicators generated")
            return {}
        
        logger.info(f"Generated technical indicators for {indicators_df['ticker'].nunique()} tickers")
        
        # Generate signals for each Monday with progress logging
        progress = ProgressLogger(interval_seconds=10, operation_name="Weekly Signals")
        progress.start(total_items=len(mondays))
        
        try:
            for idx, monday in enumerate(mondays, 1):
                date_str = monday.strftime("%Y-%m-%d")
                progress.update(date_str, current_index=idx, total=len(mondays))
                
                try:
                    # Get top stocks using technical-only mode
                    top_stocks = signal_combiner.get_top_stocks(
                        date=date_str,
                        top_n=config['backtest']['portfolio_size'],
                        mode="technical_only",
                        min_price_momentum=0.0  # Only positive momentum
                    )
                    
                    if not top_stocks.empty:
                        weekly_signals[date_str] = top_stocks
                        logger.debug(f"Generated signals for {date_str}: {len(top_stocks)} stocks")
                
                except Exception as e:
                    logger.warning(f"Error generating signals for {date_str}: {e}")
                    if DEBUG_MODE:
                        logger.debug(traceback.format_exc())
                    continue
        finally:
            progress.finish()
        
        logger.info(f"Generated weekly signals for {len(weekly_signals)} dates")
        return weekly_signals
    
    except TimeoutError:
        logger.error("Technical signals generation timed out after 5 minutes")
        raise
    except Exception as e:
        logger.error(f"Error in generate_technical_signals_weekly: {e}")
        logger.error(traceback.format_exc())
        raise
    
    except TimeoutError:
        logger.error("Technical backtest timed out after 5 minutes")
        raise
    except Exception as e:
        logger.error(f"Error in run_technical_backtest: {e}")
        logger.error(traceback.format_exc())
        raise


@with_timeout(timeout_seconds=300, operation_name="Technical Backtest")
def run_technical_backtest(config):
    """Run complete technical-only backtest"""
    logger.info("=" * 60)
    logger.info("TECHNICAL-ONLY BACKTEST")
    logger.info("=" * 60)
    
    try:
        # Step 1: Fetch price data if needed
        logger.info("\n[Step 1/5] Checking price data...")
        try:
            price_fetcher = PriceFetcher(
                data_dir="data/prices",
                min_market_cap=config['market_cap']['min'],
                max_market_cap=config['market_cap']['max']
            )
        except Exception as e:
            logger.error(f"Error initializing PriceFetcher: {e}")
            logger.error(traceback.format_exc())
            raise
        
        # Get tickers from price data directory
        price_dir = Path("data/prices")
        try:
            if price_dir.exists():
                tickers = [f.stem for f in price_dir.glob("*.parquet")]
            else:
                logger.warning("No price data found. Fetching...")
                price_fetcher.run(
                    start_date=config['data']['date_range']['start'],
                    end_date=config['data']['date_range']['end']
                )
                tickers = [f.stem for f in price_dir.glob("*.parquet")]
        except Exception as e:
            logger.error(f"Error reading price data directory: {e}")
            logger.error(traceback.format_exc())
            raise
        
        if not tickers:
            logger.error("No tickers available. Run price fetcher first.")
            return None
        
        logger.info(f"Found {len(tickers)} tickers with price data")
    
        # Step 2: Generate technical indicators
        logger.info("\n[Step 2/5] Generating technical indicators...")
        try:
            tech_indicators = TechnicalIndicators(
                data_dir="data/prices",
                output_dir="data"
            )
        except Exception as e:
            logger.error(f"Error initializing TechnicalIndicators: {e}")
            logger.error(traceback.format_exc())
            raise
        
        # Progress logging for technical indicators
        progress = ProgressLogger(interval_seconds=10, operation_name="Technical Indicators")
        progress.start(total_items=len(tickers))
        
        try:
            indicators_df = tech_indicators.process_all_tickers(
                tickers,
                short_momentum=config['technical']['momentum_short'],
                long_momentum=config['technical']['momentum_long'],
                volume_window=config['technical']['volume_window'],
                rsi_period=config['technical']['rsi_period'],
                bb_period=config['technical']['bollinger_period'],
                bb_std=config['technical']['bollinger_std']
            )
        except Exception as e:
            logger.error(f"Error processing technical indicators: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            progress.finish()
        
        if indicators_df.empty:
            logger.error("No technical indicators generated")
            return None
        
        logger.info(f"✅ Generated technical indicators for {indicators_df['ticker'].nunique()} tickers")
        
        # Step 3: Generate weekly signals
        logger.info("\n[Step 3/5] Generating weekly technical signals...")
        
        # Initialize backtest engine to load prices
        try:
            engine = BacktestEngine(
                initial_capital=config['backtest']['initial_capital'],
                trading_fees=config['backtest']['trading_fees'],
                stop_loss_pct=config['backtest']['stop_loss_pct'],
                max_drawdown_pct=config['backtest']['max_drawdown_pct']
            )
        except Exception as e:
            logger.error(f"Error initializing BacktestEngine: {e}")
            logger.error(traceback.format_exc())
            raise
        
        date_range = config['data']['date_range']
        try:
            prices_df = engine.load_price_data(
                tickers,
                start_date=date_range['start'],
                end_date=date_range['end']
            )
        except Exception as e:
            logger.error(f"Error loading price data: {e}")
            logger.error(traceback.format_exc())
            raise
        
        if prices_df.empty:
            logger.error("No price data loaded")
            return None
        
        # Generate signals for each week
        try:
            signal_combiner = SignalCombiner(data_dir="data", output_dir="data/signals")
        except Exception as e:
            logger.error(f"Error initializing SignalCombiner: {e}")
            logger.error(traceback.format_exc())
            raise
        
        # Get all Mondays
        start_dt = pd.to_datetime(date_range['start'])
        end_dt = pd.to_datetime(date_range['end'])
        mondays = pd.date_range(start=start_dt, end=end_dt, freq='W-MON')
        
        # Progress logging for weekly signals
        progress = ProgressLogger(interval_seconds=10, operation_name="Weekly Signals")
        progress.start(total_items=len(mondays))
        
        weekly_signals = {}
        try:
            for idx, monday in enumerate(mondays, 1):
                date_str = monday.strftime("%Y-%m-%d")
                progress.update(date_str, current_index=idx, total=len(mondays))
                
                try:
                    top_stocks = signal_combiner.get_top_stocks(
                        date=date_str,
                        top_n=config['backtest']['portfolio_size'],
                        mode="technical_only",
                        min_price_momentum=0.0
                    )
                    if not top_stocks.empty:
                        weekly_signals[date_str] = top_stocks
                except Exception as e:
                    logger.warning(f"Error generating signals for {date_str}: {e}")
                    if DEBUG_MODE:
                        logger.debug(traceback.format_exc())
                    continue
        finally:
            progress.finish()
        
        logger.info(f"✅ Generated signals for {len(weekly_signals)} weeks")
        
        # Step 4: Generate positions for backtest
        logger.info("\n[Step 4/5] Generating positions for backtest...")
        
        try:
            # Create positions DataFrame
            positions = pd.DataFrame(0.0, index=prices_df.index, columns=prices_df.columns)
            current_holdings = set()
            
            for monday in mondays:
                date_str = monday.strftime("%Y-%m-%d")
                
                if date_str not in weekly_signals:
                    continue
                
                top_stocks_df = weekly_signals[date_str]
                top_stocks = top_stocks_df['ticker'].tolist()
                top_stocks_set = set(top_stocks)
                
                # Get buffer stocks (top M)
                buffer_size = config['backtest']['buffer_size']
                buffer_stocks = top_stocks[:buffer_size]
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
                        next_monday_idx = mondays[mondays > monday]
                        if len(next_monday_idx) > 0:
                            end_rebalance = next_monday_idx[0]
                            future_dates = future_dates[future_dates < end_rebalance]
                        
                        for ticker in current_holdings:
                            if ticker in positions.columns:
                                positions.loc[future_dates, ticker] = weight_per_stock
            
            # Apply stop loss
            positions = engine.apply_stop_loss(prices_df, positions)
        except Exception as e:
            logger.error(f"Error generating positions: {e}")
            logger.error(traceback.format_exc())
            raise
        
        logger.info(f"✅ Generated positions for backtest")
        
        # Step 5: Run backtest
        logger.info("\n[Step 5/5] Running backtest...")
        try:
            results = engine.run_backtest(prices_df, positions)
        except Exception as e:
            logger.error(f"Error running backtest: {e}")
            logger.error(traceback.format_exc())
            raise
        
        # Compare to benchmark
        try:
            benchmark_comparison = engine.compare_to_benchmark(
                results['portfolio_returns'],
                benchmark_ticker="SPY",
                start_date=date_range['start'],
                end_date=date_range['end']
            )
        except Exception as e:
            logger.warning(f"Error comparing to benchmark: {e}")
            benchmark_comparison = None
        
        # Generate report
        logger.info("\n" + "=" * 60)
        logger.info("BACKTEST RESULTS")
        logger.info("=" * 60)
        logger.info(f"Total Return:        {results['total_return']:.2%}")
        logger.info(f"Sharpe Ratio:        {results['sharpe_ratio']:.2f}")
        logger.info(f"Max Drawdown:        {results['max_drawdown']:.2%}")
        logger.info(f"Win Rate:            {results['win_rate']:.2%}")
        logger.info(f"Number of Trades:    {results['num_trades']}")
        
        if benchmark_comparison:
            logger.info(f"\nBenchmark (SPY):")
            logger.info(f"  Portfolio Return:  {benchmark_comparison['portfolio_total_return']:.2%}")
            logger.info(f"  Benchmark Return:  {benchmark_comparison['benchmark_total_return']:.2%}")
            logger.info(f"  Excess Return:     {benchmark_comparison['excess_return']:.2%}")
        
        # Plot equity curve
        try:
            os.makedirs("backtests/results", exist_ok=True)
            fig, ax = plt.subplots(figsize=(12, 6))
            
            portfolio_cum = results['cumulative_returns']
            ax.plot(portfolio_cum.index, portfolio_cum.values, label='Technical Strategy', linewidth=2)
            
            if benchmark_comparison and 'benchmark_cumulative' in benchmark_comparison:
                benchmark_cum = benchmark_comparison['benchmark_cumulative']
                ax.plot(benchmark_cum.index, benchmark_cum.values, label='SPY Benchmark', linewidth=2, alpha=0.7)
            
            ax.set_xlabel('Date')
            ax.set_ylabel('Cumulative Return')
            ax.set_title('Technical-Only Strategy: Equity Curve')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.savefig("backtests/results/technical_backtest_equity_curve.png", dpi=300, bbox_inches='tight')
            logger.info(f"\n✅ Saved equity curve to backtests/results/technical_backtest_equity_curve.png")
            plt.close()
        except Exception as e:
            logger.error(f"Error creating equity curve plot: {e}")
            logger.error(traceback.format_exc())
        
        # Save performance report
        report_path = "backtests/results/technical_backtest_report.txt"
        try:
            with open(report_path, 'w') as f:
                f.write("=" * 60 + "\n")
                f.write("TECHNICAL-ONLY BACKTEST REPORT\n")
                f.write("=" * 60 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("STRATEGY METRICS\n")
                f.write("-" * 60 + "\n")
                f.write(f"Total Return:        {results['total_return']:.2%}\n")
                f.write(f"Sharpe Ratio:        {results['sharpe_ratio']:.2f}\n")
                f.write(f"Max Drawdown:        {results['max_drawdown']:.2%}\n")
                f.write(f"Win Rate:            {results['win_rate']:.2%}\n")
                f.write(f"Number of Trades:    {results['num_trades']}\n\n")
                
                if benchmark_comparison:
                    f.write("BENCHMARK COMPARISON (vs SPY)\n")
                    f.write("-" * 60 + "\n")
                    f.write(f"Portfolio Return:    {benchmark_comparison['portfolio_total_return']:.2%}\n")
                    f.write(f"Benchmark Return:    {benchmark_comparison['benchmark_total_return']:.2%}\n")
                    f.write(f"Excess Return:       {benchmark_comparison['excess_return']:.2%}\n\n")
                
                f.write("SIGNAL WEIGHTS\n")
                f.write("-" * 60 + "\n")
                f.write(f"Price Momentum:      50%\n")
                f.write(f"Volume Spike:        30%\n")
                f.write(f"RSI Score:           20%\n")
            
            logger.info(f"✅ Saved performance report to {report_path}")
        except Exception as e:
            logger.error(f"Error saving performance report: {e}")
            logger.error(traceback.format_exc())
        
        return {
            'results': results,
            'benchmark_comparison': benchmark_comparison
        }
    
    except TimeoutError:
        logger.error("Technical backtest timed out after 5 minutes")
        raise
    except Exception as e:
        logger.error(f"Error in run_technical_backtest: {e}")
        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    config = load_config()
    
    # Ensure mode is set to technical_only
    if config['backtest'].get('mode') != 'technical_only':
        logger.warning("Config backtest.mode is not 'technical_only'. Setting it for this run...")
        config['backtest']['mode'] = 'technical_only'
    
    results = run_technical_backtest(config)
    
    if results:
        print("\n✅ Technical-only backtest complete!", flush=True)
        print("Check backtests/results/ for:", flush=True)
        print("  - technical_backtest_equity_curve.png", flush=True)
        print("  - technical_backtest_report.txt", flush=True)
