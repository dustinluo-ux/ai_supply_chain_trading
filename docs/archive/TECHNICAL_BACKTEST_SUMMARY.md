# Technical-Only Backtest Implementation ✅

## What Was Built

A complete technical-only backtest mode that allows testing the infrastructure without requiring historical news data.

### Key Features

1. **Config Toggle**: Switch between modes via `config.yaml`
   ```yaml
   backtest:
     mode: "technical_only"  # or "full_with_news"
   ```

2. **Technical-Only Signal Generation**
   - Price Momentum (50%): (close_5d - close_20d) / close_20d
   - Volume Spike (30%): current_volume / avg_volume_30d
   - RSI Score (20%): Normalized RSI (0-1 scale)

3. **Filters Applied**
   - Market cap: $500M - $5B
   - Only positive momentum (no shorts)

4. **Complete Backtest Pipeline**
   - Weekly rebalancing (every Monday)
   - Top 10 stocks, equal weight
   - Stop loss: -8% per position
   - Max drawdown: -15% portfolio
   - Trading fees: 10 bps

## Files Created/Modified

### New Files
- `run_technical_backtest.py` - Standalone technical-only backtest script
- `TECHNICAL_ONLY_MODE.md` - User guide
- `TECHNICAL_BACKTEST_SUMMARY.md` - This file

### Modified Files
- `config/config.yaml` - Added `backtest.mode` and `technical_signal_weights`
- `src/signals/signal_combiner.py` - Added `calculate_technical_only_signal()` method
- `src/backtest/backtest_engine.py` - Added `mode` parameter to signal loading
- `run_phase2_pipeline.py` - Added conditional logic for technical-only mode
- `run_phase3_backtest.py` - Added mode support

## Usage

### Run Technical-Only Backtest

```bash
python run_technical_backtest.py
```

This will:
1. ✅ Check/fetch price data
2. ✅ Calculate technical indicators (momentum, volume, RSI)
3. ✅ Generate weekly signals (technical-only)
4. ✅ Run backtest with weekly rebalancing
5. ✅ Generate performance report and equity curve

### Switch to Full Pipeline

Edit `config.yaml`:
```yaml
backtest:
  mode: "full_with_news"
```

Then run:
```bash
python run_strategy.py --phase all
```

## Signal Calculation

**Technical-Only Mode:**
```python
technical_signal = (
    0.5 * normalized_price_momentum +
    0.3 * normalized_volume_spike +
    0.2 * normalized_rsi_score
)
```

**RSI Normalization:**
- RSI (0-100) → Score (0-1)
- Formula: `(RSI - 30) / 40`, clipped to [0, 1]
- RSI 30 → Score 0
- RSI 70 → Score 1
- Higher RSI = Higher signal

## Output Files

- `backtests/results/technical_backtest_equity_curve.png`
- `backtests/results/technical_backtest_report.txt`
- `data/signals/top_stocks_YYYY-MM-DD_technical.csv` (weekly signals)

## Benefits

✅ **Test Infrastructure**: Run backtests without news data
✅ **Fast Iteration**: Technical indicators are quick to calculate
✅ **Baseline Performance**: Establish technical-only baseline
✅ **Easy Toggle**: Switch modes with one config line
✅ **Nothing Deleted**: All news/LLM code remains intact

## Next Steps

1. Run technical-only backtest: `python run_technical_backtest.py`
2. Review performance metrics
3. When news data is available, switch to `full_with_news` mode
4. Compare technical-only vs full pipeline performance

The system is ready to test end-to-end with technical indicators only!
