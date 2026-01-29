"""
Phase 3: Backtesting & Performance Analysis
Runs full backtest with performance analytics and parameter sensitivity
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

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logger
from src.backtest.backtest_engine import BacktestEngine

logger = setup_logger()

# Set style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")


def load_config():
    """Load configuration"""
    config_path = project_root / "config" / "config.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def plot_equity_curve(results: dict, benchmark_comparison: dict, output_dir: str = "backtests/results"):
    """Plot equity curve"""
    os.makedirs(output_dir, exist_ok=True)
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Portfolio equity curve
    portfolio_cum = results['cumulative_returns']
    ax.plot(portfolio_cum.index, portfolio_cum.values, label='Portfolio', linewidth=2)
    
    # Benchmark if available
    if benchmark_comparison and 'portfolio_cumulative' in benchmark_comparison:
        benchmark_cum = benchmark_comparison['benchmark_cumulative']
        ax.plot(benchmark_cum.index, benchmark_cum.values, label='SPY Benchmark', linewidth=2, alpha=0.7)
    
    ax.set_xlabel('Date')
    ax.set_ylabel('Cumulative Return')
    ax.set_title('Equity Curve: AI Supply Chain Strategy')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'equity_curve.png'), dpi=300, bbox_inches='tight')
    logger.info(f"Saved equity curve to {output_dir}/equity_curve.png")
    plt.close()


def generate_performance_report(results: dict, benchmark_comparison: dict, 
                               output_dir: str = "backtests/results"):
    """Generate comprehensive performance report"""
    os.makedirs(output_dir, exist_ok=True)
    
    report = []
    report.append("=" * 60)
    report.append("BACKTEST PERFORMANCE REPORT")
    report.append("=" * 60)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    
    # Strategy Metrics
    report.append("STRATEGY METRICS")
    report.append("-" * 60)
    report.append(f"Total Return:        {results['total_return']:.2%}")
    report.append(f"Sharpe Ratio:        {results['sharpe_ratio']:.2f}")
    report.append(f"Max Drawdown:        {results['max_drawdown']:.2%}")
    report.append(f"Win Rate:            {results['win_rate']:.2%}")
    report.append(f"Number of Trades:    {results['num_trades']}")
    report.append("")
    
    # Benchmark Comparison
    if benchmark_comparison:
        report.append("BENCHMARK COMPARISON (vs SPY)")
        report.append("-" * 60)
        report.append(f"Portfolio Return:    {benchmark_comparison['portfolio_total_return']:.2%}")
        report.append(f"Benchmark Return:    {benchmark_comparison['benchmark_total_return']:.2%}")
        report.append(f"Excess Return:       {benchmark_comparison['excess_return']:.2%}")
        report.append("")
    
    # Target Performance Check
    report.append("TARGET PERFORMANCE CHECK")
    report.append("-" * 60)
    sharpe_target = 1.5
    drawdown_target = -0.15
    winrate_target = 0.55
    
    sharpe_pass = results['sharpe_ratio'] > sharpe_target
    drawdown_pass = results['max_drawdown'] > drawdown_target
    winrate_pass = results['win_rate'] > winrate_target
    
    report.append(f"Sharpe > {sharpe_target}:     {'✅ PASS' if sharpe_pass else '❌ FAIL'} ({results['sharpe_ratio']:.2f})")
    report.append(f"Max DD < {abs(drawdown_target):.0%}:      {'✅ PASS' if drawdown_pass else '❌ FAIL'} ({results['max_drawdown']:.2%})")
    report.append(f"Win Rate > {winrate_target:.0%}:  {'✅ PASS' if winrate_pass else '❌ FAIL'} ({results['win_rate']:.2%})")
    
    if benchmark_comparison:
        beat_benchmark = benchmark_comparison['excess_return'] > 0
        report.append(f"Beat SPY:            {'✅ PASS' if beat_benchmark else '❌ FAIL'} ({benchmark_comparison['excess_return']:.2%})")
    
    report.append("")
    report.append("=" * 60)
    
    # Save report
    report_text = "\n".join(report)
    report_path = os.path.join(output_dir, 'performance_report.txt')
    with open(report_path, 'w') as f:
        f.write(report_text)
    
    logger.info(f"Saved performance report to {report_path}")
    print("\n" + report_text)
    
    return report_text


def run_parameter_sensitivity(config, output_dir: str = "backtests/results"):
    """Run parameter sensitivity analysis"""
    os.makedirs(output_dir, exist_ok=True)
    
    logger.info("Running parameter sensitivity analysis...")
    
    # Parameter ranges to test
    param_ranges = {
        'supply_chain_weight': [0.3, 0.4, 0.5],
        'sentiment_weight': [0.2, 0.3, 0.4],
        'portfolio_size': [5, 10, 15, 20],
        'stop_loss': [-0.05, -0.08, -0.10]
    }
    
    results_list = []
    
    # Base parameters
    base_config = config.copy()
    
    # Test variations (simplified - in production, use grid search)
    logger.info("Testing parameter variations...")
    
    for sc_weight in param_ranges['supply_chain_weight']:
        for port_size in param_ranges['portfolio_size']:
            for stop_loss in param_ranges['stop_loss']:
                # Update config
                test_config = base_config.copy()
                test_config['signal_weights']['supply_chain_score'] = sc_weight
                test_config['signal_weights']['sentiment_momentum'] = 1.0 - sc_weight - 0.2 - 0.1  # Adjust others
                test_config['backtest']['portfolio_size'] = port_size
                test_config['backtest']['stop_loss_pct'] = stop_loss
                
                # Run backtest (simplified - would need full pipeline)
                # For now, just record parameter set
                results_list.append({
                    'supply_chain_weight': sc_weight,
                    'sentiment_weight': test_config['signal_weights']['sentiment_momentum'],
                    'portfolio_size': port_size,
                    'stop_loss': stop_loss,
                    'sharpe_ratio': np.nan,  # Would be filled by actual backtest
                    'total_return': np.nan,
                    'max_drawdown': np.nan
                })
    
    # Save results
    sensitivity_df = pd.DataFrame(results_list)
    sensitivity_path = os.path.join(output_dir, 'parameter_sensitivity.csv')
    sensitivity_df.to_csv(sensitivity_path, index=False)
    
    logger.info(f"Parameter sensitivity results saved to {sensitivity_path}")
    logger.warning("Note: Sensitivity analysis requires full backtest runs. "
                  "Sharpe ratios need to be calculated by running backtests for each parameter set.")
    
    return sensitivity_df


def run_phase3_backtest(config):
    """Run complete Phase 3 backtest"""
    logger.info("=" * 60)
    logger.info("PHASE 3: Backtesting & Performance Analysis")
    logger.info("=" * 60)
    
    # Initialize backtest engine
    engine = BacktestEngine(
        initial_capital=config['backtest']['initial_capital'],
        trading_fees=config['backtest']['trading_fees'],
        stop_loss_pct=config['backtest']['stop_loss_pct'],
        max_drawdown_pct=config['backtest']['max_drawdown_pct']
    )
    
    # Get tickers from signals
    signal_dir = Path("data/signals")
    signal_files = list(signal_dir.glob("top_stocks_*.csv"))
    
    if not signal_files:
        logger.error("No signal files found. Run Phase 2 first.")
        return None
    
    # Load latest signals to get ticker list
    latest_signal = sorted(signal_files)[-1]
    signals_df = pd.read_csv(latest_signal)
    tickers = signals_df['ticker'].tolist()
    
    logger.info(f"Running backtest for {len(tickers)} tickers")
    
    # Load price data
    date_range = config['data']['date_range']
    prices_df = engine.load_price_data(
        tickers,
        start_date=date_range['start'],
        end_date=date_range['end']
    )
    
    if prices_df.empty:
        logger.error("No price data loaded. Run Phase 1 first.")
        return None
    
    # Get mode from config
    mode = config['backtest'].get('mode', 'full_with_news')
    
    # Generate weekly signals
    positions_df = engine.generate_weekly_signals(
        prices_df,
        portfolio_size=config['backtest']['portfolio_size'],
        buffer_size=config['backtest']['buffer_size'],
        start_date=date_range['start'],
        end_date=date_range['end'],
        mode=mode
    )
    
    # Apply stop loss
    positions_df = engine.apply_stop_loss(prices_df, positions_df)
    
    # Run backtest
    results = engine.run_backtest(prices_df, positions_df)
    
    # Compare to benchmark
    benchmark_comparison = engine.compare_to_benchmark(
        results['portfolio_returns'],
        benchmark_ticker="SPY",
        start_date=date_range['start'],
        end_date=date_range['end']
    )
    
    # Generate plots and reports
    plot_equity_curve(results, benchmark_comparison)
    report = generate_performance_report(results, benchmark_comparison)
    
    # Parameter sensitivity (placeholder - requires full pipeline runs)
    sensitivity_df = run_parameter_sensitivity(config)
    
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 3 COMPLETE")
    logger.info("=" * 60)
    
    return {
        'results': results,
        'benchmark_comparison': benchmark_comparison,
        'sensitivity': sensitivity_df
    }


if __name__ == "__main__":
    config = load_config()
    results = run_phase3_backtest(config)
    
    if results:
        print("\n✅ Phase 3 backtest complete!")
        print("Check backtests/results/ for:")
        print("  - equity_curve.png")
        print("  - performance_report.txt")
        print("  - parameter_sensitivity.csv")
