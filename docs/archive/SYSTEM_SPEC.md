# System Specification

**Last Updated:** 2026-01-25

---

## What This System Does

AI Supply Chain Thematic Trading System: Uses LLM analysis (Gemini) to identify AI supply chain beneficiaries from news articles, combines with technical indicators, and generates weekly trading signals.

**Entry Point:** `test_signals.py`

**Current Status:** CSV-based backtesting only. IB integration code exists but is unused.

---

## System Architecture

### Execution Flow

1. **Universe Selection** (`UniverseLoader`)
   - Loads tickers from CSV files in `data/prices/` subdirectories
   - Optional: Ranks by supply chain relevance using Gemini
   - Filters by date range, data quality, price thresholds

2. **Data Loading**
   - **Price data:** Direct CSV reads (`pd.read_csv`)
   - **News data:** JSON files from `data/news/{ticker}_news.json`
   - No data provider abstraction (IB code exists but unused)

3. **Signal Generation** (pre-calculated)
   - **Technical:** Inline calculation (momentum, volume, RSI)
   - **News:** `NewsAnalyzer` → `GeminiNewsAnalyzer` → Gemini API
   - Cached before backtest

4. **Signal Combination**
   - `SignalCombiner.combine_signals_direct()`
   - Weighted combination or optional ML prediction
   - Ranks stocks by combined score

5. **Portfolio Construction**
   - Selects top N stocks by score
   - Assigns weights (proportional or equal)
   - No position limits, no risk scaling

6. **Backtesting** (inline)
   - Calculates portfolio returns
   - Applies 10 bps transaction costs on rebalance
   - Computes Sharpe, return, drawdown

7. **Output**
   - Runs 3 backtests: technical-only, news-only, combined
   - Compares Sharpe ratios
   - Logs to `outputs/backtest_log_*.txt`

---

## How to Run

### Backtest Mode (Current)

```bash
python test_signals.py --universe-size 15 --top-n 10
```

**What it does:**
- Loads price data from CSV files
- Analyzes news with Gemini API
- Runs backtest and outputs metrics

**Requirements:**
- Price data in `data/prices/` (CSV format)
- News data in `data/news/` (JSON format)
- `GEMINI_API_KEY` environment variable set

**Configuration:**
- `config/signal_weights.yaml` - Signal weights
- `config/data_config.yaml` - Data directory paths
- `config/model_config.yaml` - ML model settings (optional)

### Paper Trading (Not Implemented)

IB integration code exists (`src/data/ib_provider.py`, `src/execution/ib_executor.py`) but is **not used** in `test_signals.py`.

**To enable:**
1. Modify `test_signals.py` to use `DataProviderFactory` and `ExecutorFactory`
2. Set `config/trading_config.yaml` mode to `"paper"`
3. Connect to IB Gateway/TWS

**Status:** Code exists but requires integration work.

### Live Trading (Not Implemented)

Same as paper trading - code exists but unused.

---

## Key Assumptions

1. **Data Format:**
   - Price: CSV with `close` column, date index
   - News: JSON array with `publishedAt`, `title`, `content`

2. **Date Alignment:**
   - Uses "best coverage" month (most tickers with news)
   - Requires overlap between price and news data

3. **Signal Quality:**
   - News signals can be `None` (no fallback)
   - Technical signals have defaults if insufficient data

4. **Trading:**
   - Weekly rebalancing on Mondays
   - No slippage modeling (only 10 bps transaction cost)
   - No position limits or risk constraints

---

## What Is Out of Scope

1. **Live Trading:** IB code exists but not integrated
2. **Risk Management:** Risk calculator exists but never called
3. **Position Limits:** Single stock can get 100% weight
4. **Portfolio Optimizer:** Never ported
5. **Advanced Backtesting:** No walk-forward, Monte Carlo, significance tests

---

## File Structure

```
test_signals.py          # Main entry point
src/
  data/
    universe_loader.py   # Universe selection
    supply_chain_manager.py  # Supply chain DB
  signals/
    news_analyzer.py     # News analysis wrapper
    gemini_news_analyzer.py  # Gemini API calls
    supply_chain_scanner.py  # Supply chain scoring
    signal_combiner.py   # Signal combination
  data/
    ib_provider.py       # IB data (exists, unused)
  execution/
    ib_executor.py       # IB execution (exists, unused)
config/
  signal_weights.yaml    # Signal weights
  data_config.yaml       # Data paths
  trading_config.yaml    # Trading config (exists, unused)
data/
  prices/                # CSV price files
  news/                  # JSON news files
  cache/                 # Gemini API cache
  supply_chain_relationships.json  # Supply chain DB
```

---

## Dependencies

**Required:**
- `pandas`, `numpy`, `yaml`
- `google-generativeai` (Gemini API)

**Optional:**
- `ib_insync` (for IB integration, if enabled)
- `scikit-learn` (for ML model, if enabled)

See `requirements.txt` for full list.

---

## Configuration Files

### `config/signal_weights.yaml`

```yaml
signal_weights:
  supply_chain: 0.40
  sentiment: 0.30
  momentum: 0.20
  volume: 0.10

weighting_method: "proportional"  # or "equal"

technical_indicators:
  momentum_period: 20
  volume_period: 30
  rsi_period: 14

news_analysis:
  enabled: true
  lookback_days: 7
  min_articles: 1
```

### `config/data_config.yaml`

```yaml
data_sources:
  data_dir: "data/prices"
  file_format: "auto"

universe_selection:
  max_tickers: 50
  min_data_points: 252
  date_range:
    start: "2023-01-01"
    end: "2024-12-31"
```

---

## Environment Variables

```bash
export GEMINI_API_KEY="your_key_here"
```

---

## Output

**Logs:** `outputs/backtest_log_YYYYMMDD_HHMMSS.txt`

**Metrics:**
- Sharpe ratio
- Total return
- Max drawdown
- Comparison: technical-only vs news-only vs combined

---

## Limitations

1. **Single Month Backtest:** Uses best-coverage month, not full multi-month
2. **No Risk Management:** No position limits, no volatility targeting
3. **Simple Transaction Costs:** 10 bps only, no slippage
4. **No Live Trading:** IB code exists but unused
5. **News Dependency:** Returns `None` if no news found (no fallback)

---

See `docs/STRATEGY_MATH.md` for signal formulas and `docs/DATA.md` for data sources.
