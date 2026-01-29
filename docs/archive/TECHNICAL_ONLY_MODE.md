# Technical-Only Mode

## Overview

The system now supports two modes:
- **`technical_only`**: Uses only technical indicators (no news/LLM data required)
- **`full_with_news`**: Full pipeline with news, LLM analysis, sentiment, and technical indicators

## Configuration

Edit `config/config.yaml`:

```yaml
backtest:
  mode: "technical_only"  # Options: "technical_only", "full_with_news"
```

## Technical-Only Signal Weights

When in technical-only mode, signals use:
- **Price Momentum (50%)**: (close_5d - close_20d) / close_20d
- **Volume Spike (30%)**: current_volume / avg_volume_30d
- **RSI Score (20%)**: Normalized RSI (0-1 scale, higher RSI = higher signal)

## Usage

### Run Technical-Only Backtest

```bash
python run_technical_backtest.py
```

This will:
1. Fetch price data (if needed)
2. Calculate technical indicators
3. Generate weekly signals using only technical indicators
4. Run backtest with weekly rebalancing
5. Generate performance report and equity curve

### Run Full Pipeline (with news)

```bash
# Set mode in config.yaml to "full_with_news"
python run_strategy.py --phase all
```

## Technical-Only Signal Generation

The `SignalCombiner.calculate_technical_only_signal()` method:
- Loads technical indicators (momentum, volume, RSI)
- Normalizes RSI: (RSI - 30) / 40, clipped to 0-1
- Filters: Only positive momentum stocks
- Combines: 50% momentum + 30% volume + 20% RSI
- Ranks: Top N stocks by technical signal

## Filters Applied

- **Market Cap**: $500M - $5B (from price fetcher)
- **Price Momentum**: >= 0.0 (only positive momentum, no shorts)

## Backtest Parameters

- **Period**: 2023-01-01 to 2024-12-31
- **Rebalancing**: Weekly (every Monday)
- **Portfolio Size**: Top 10 stocks
- **Position Sizing**: Equal weight (10% per stock)
- **Stop Loss**: -8% per position
- **Max Drawdown**: -15% portfolio (kill switch)
- **Trading Fees**: 10 bps (0.001)

## Output Files

- `backtests/results/technical_backtest_equity_curve.png` - Equity curve plot
- `backtests/results/technical_backtest_report.txt` - Performance metrics
- `data/signals/top_stocks_YYYY-MM-DD_technical.csv` - Weekly signal rankings

## Switching Modes

1. **To Technical-Only**: Set `backtest.mode: "technical_only"` in config.yaml
2. **To Full Pipeline**: Set `backtest.mode: "full_with_news"` in config.yaml

No code changes needed - just flip the config toggle!

## Benefits

✅ **Test Infrastructure**: Run backtests without historical news data
✅ **Fast Iteration**: Technical indicators are quick to calculate
✅ **Baseline Performance**: Establish technical-only baseline before adding news
✅ **Easy Toggle**: Switch modes with one config line

## Example Output

```
TECHNICAL-ONLY BACKTEST RESULTS
================================
Total Return:        15.30%
Sharpe Ratio:         1.25
Max Drawdown:         -12.50%
Win Rate:             55.20%
Number of Trades:     104

Benchmark (SPY):
  Portfolio Return:   15.30%
  Benchmark Return:    12.50%
  Excess Return:       2.80%
```
