# Model Specification - Complete Implementation Reference

**Last Updated:** 2026-01-25  
**Purpose:** Comprehensive documentation of ALL implementation choices, parameters, thresholds, filters, and assumptions in the trading system.

> **Auto-Update Policy:** This document should be updated whenever code changes affect any documented parameter, threshold, algorithm, or assumption. See "Maintenance" section at the end.

---

## Table of Contents

1. [Universe Selection & Filtering](#universe-selection--filtering)
2. [Date Range & Alignment](#date-range--alignment)
3. [Technical Signal Calculation](#technical-signal-calculation)
4. [News Signal Calculation](#news-signal-calculation)
5. [Sentiment Propagation](#sentiment-propagation)
6. [Signal Combination & Weighting](#signal-combination--weighting)
7. [ML Regression Framework](#ml-regression-framework)
8. [Portfolio Construction & Rebalancing](#portfolio-construction--rebalancing)
9. [Performance Measurement](#performance-measurement)
10. [Data Processing & Edge Cases](#data-processing--edge-cases)
11. [LLM Configuration](#llm-configuration)
12. [Supply Chain Database](#supply-chain-database)
13. [Maintenance](#maintenance)

---

## Universe Selection & Filtering

### Stock Universe Sources
- **Location:** `src/data/universe_loader.py` - `UniverseLoader.get_tickers()`
- **Sources:** NASDAQ, S&P 500, NYSE, Forbes 2000 CSV directories
- **Default Size:** 15 tickers (`--universe-size` parameter, default=15)
- **Deduplication:** Removes duplicate tickers across directories
- **Configurable:** Yes (via `--universe-size` CLI argument or `config/data_config.yaml`)

### Market Cap Filtering
- **Location:** `src/data/price_fetcher.py` - `filter_by_market_cap()`
- **Default Range:** $500M - $5B (500,000,000 to 5,000,000,000)
- **Purpose:** Focuses on mid-cap stocks (Russell 2000 range)
- **Configurable:** Yes (via `min_market_cap` and `max_market_cap` parameters)
- **Note:** Only applied if `use_market_cap_filter=True`

### Price Data Filtering
- **Location:** `test_signals.py` - Price data loading section (lines 224-244)
- **Date Priority:** Tries 2023 first, then 2022-2023, then 2020+
- **Minimum Data:** Requires at least 5 rows after filtering (`len(df_filtered) < 5` check)
- **Required Columns:** Must have 'close' column
- **Volume Handling:** Missing volume defaults to 1.0 (neutral signal)
- **Hardcoded:** Yes (date priority logic)

### Minimum Price Filter
- **Location:** `src/data/universe_loader.py` - `_default_config()`
- **Default:** $1.00 minimum price
- **Purpose:** Filters out penny stocks
- **Configurable:** Yes (via `config/data_config.yaml` - `filtering.min_price`)

### Ticker Filtering (DEBUG Mode)
- **Location:** `test_signals.py` - Lines 112-120
- **Behavior:** In DEBUG_MODE, filters to `DEBUG_STOCKS` list only
- **Configurable:** Yes (via `DEBUG_STOCKS` variable)

---

## Date Range & Alignment

### Best Coverage Algorithm
- **Location:** `test_signals.py` - Lines 282-430
- **Method:** Scans ALL news files, finds month with most ticker coverage
- **Alignment:** Prefers months aligned with price data years
- **Fallback:** Uses union approach if best coverage fails
- **Flag:** `USE_BEST_COVERAGE = True` (can be disabled)
- **Configurable:** Yes (via `USE_BEST_COVERAGE` flag)

### Date Range Detection
- **Price Data:** Uses intersection (max of starts, min of ends) for most restrictive range
- **News Data:** Scans all 3,720+ news files to find best coverage month
- **Overlap Calculation:** `overlap_start = max(price_start, news_start)`, `overlap_end = min(price_end, news_end)`
- **Location:** `test_signals.py` - Lines 500-515
- **Hardcoded:** Yes (intersection logic)

### Signal Date Range
- **Location:** `test_signals.py` - Lines 540-568
- **History Requirement:** Adds 30 days to start for technical indicator warmup
- **Adjustment:** If 30-day buffer exceeds end date, uses start date directly
- **Rebalance Frequency:** Weekly (Mondays only)
- **Hardcoded:** Yes (30-day buffer, Monday-only rebalancing)

### News Lookback Window
- **Location:** `src/signals/news_analyzer.py` - `lookback_days` parameter
- **Default:** 7 days before rebalance date
- **Configurable:** Yes (via `news_config['lookback_days']`)

---

## Technical Signal Calculation

### Momentum Calculation
- **Location:** `src/signals/technical_analyzer.py` - `calculate_momentum()`
- **Short Period:** 5 days (hardcoded in calculation)
- **Long Period:** 20 days (default, configurable via `momentum_period`)
- **Formula:** `(close[-5] - close[-20]) / close[-20]`
- **Minimum Data:** Requires at least `momentum_period` days
- **Default Value:** 0.0 if insufficient data
- **Configurable:** Yes (via `tech_config['momentum_period']`)

### Volume Spike Calculation
- **Location:** `src/signals/technical_analyzer.py` - `calculate_volume_ratio()`
- **Window:** 30 days rolling average (default, configurable)
- **Formula:** `current_volume / rolling_avg_30d`
- **Neutral Value:** 1.0 (if no volume data or insufficient history)
- **Minimum Data:** Requires at least `volume_period` days
- **Configurable:** Yes (via `tech_config['volume_period']`)

### RSI Calculation
- **Location:** `src/signals/technical_analyzer.py` - `calculate_rsi()`
- **Period:** 14 days (default, configurable)
- **Normalization:** `((RSI - 30) / 40).clip(0, 1)` - maps 30→0, 70→1
- **Neutral Value:** 0.5 if calculation fails
- **Minimum Data:** Uses `min_periods=1` (works with limited data)
- **Configurable:** Yes (via `tech_config['rsi_period']`)

### Technical Signal Defaults
- **Location:** `src/signals/technical_analyzer.py` - `calculate_signals()`
- **Momentum Default:** 0.0 (if insufficient data)
- **Volume Default:** 1.0 (neutral, if missing volume column)
- **RSI Default:** 0.5 (neutral, if calculation fails)
- **Hardcoded:** Yes (default values)

### Technical-Only Mode Weights
- **Location:** `test_signals.py` - Lines 767-768
- **Weights:** momentum=0.5, volume=0.3, rsi=0.2
- **RSI Combination:** In technical-only mode, RSI and momentum are combined first (0.7 momentum + 0.3 RSI)
- **Hardcoded:** Yes (mode-specific weights)

---

## News Signal Calculation

### Article Loading
- **Location:** `src/signals/gemini_news_analyzer.py` - `load_articles_for_ticker()`
- **File Format:** `{ticker}_news.json` in `data/news/` directory
- **Date Filtering:** Articles must have `publishedAt` in range `[start_date, end_date]`
- **Minimum Articles:** 1 article required (configurable via `min_articles`)
- **Returns None:** If insufficient articles or no articles found (NO FALLBACK)

### Article Batching
- **Location:** `src/signals/gemini_news_analyzer.py` - `analyze_news_for_ticker()`
- **Batch Size:** 3 articles per API call (default, configurable)
- **Purpose:** Optimizes token usage by combining multiple articles
- **Configurable:** Yes (via `batch_size` parameter in `__init__`)

### Text Truncation
- **Location:** `src/signals/gemini_news_analyzer.py` - `_create_supply_chain_prompt()`
- **Max Characters:** 100,000 chars per batch (reduced for token efficiency)
- **Truncation:** Cuts at limit and appends "..."
- **Hardcoded:** Yes (100,000 char limit)

### LLM Prompt Structure
- **Location:** `src/signals/gemini_news_analyzer.py` - `_create_supply_chain_prompt()`
- **Model:** Gemini 2.5 Flash Lite (paid tier)
- **Output Format:** JSON with `relationship`, `supply_chain_health_score`, `reasoning`
- **Reasoning Limit:** Max 15 words
- **Score Range:** -1.0 to 1.0 for supply chain health
- **Asymmetric Sentiment:** Prompt instructs LLM to consider ticker's role (Supplier/Buyer)
- **Hardcoded:** Yes (prompt template)

### List Response Handling
- **Location:** `src/signals/gemini_news_analyzer.py` - Lines 447-475
- **Behavior:** If LLM returns list instead of single dict, combines by averaging scores
- **Empty List:** Skips batch if empty list returned
- **Relationship:** Takes most common relationship from list
- **Reasoning:** Joins all reasonings with ` | ` separator
- **Hardcoded:** Yes (list handling logic)

### Rate Limiting
- **Location:** `src/signals/gemini_news_analyzer.py` - `rate_limit_seconds` parameter
- **Default:** 0.5 seconds between API calls (~300 RPM for paid tier)
- **Applied:** Between batches, not after last batch
- **Configurable:** Yes (via `rate_limit_seconds` parameter)

### Caching
- **Location:** `src/signals/gemini_news_analyzer.py` - `JSONCache` class
- **Cache Directory:** `data/cache/`
- **File Format:** `gemini_{ticker}_{date}.json`
- **Behavior:** Checks cache before API call, saves after
- **Hardcoded:** Yes (cache directory and file naming)

### News Signal Defaults
- **Location:** `test_signals.py` - Lines 802-809
- **No News:** Returns `{'supply_chain_score': 0.0, 'sentiment_score': 0.0, 'confidence': 0.0}`
- **News-Only Mode:** Skips ticker if all news signals are 0.0 (no fallback to technical)
- **Hardcoded:** Yes (default values and skip logic)

---

## Sentiment Propagation

### Propagation Engine
- **Location:** `src/signals/sentiment_propagator.py` - `SentimentPropagator` class
- **Purpose:** Propagates news sentiment from primary ticker to related companies (suppliers, customers, competitors)
- **Algorithm:** Directed graph BFS traversal with decay factors
- **Max Degrees:** 2 degrees of separation (configurable)
- **Configurable:** Yes (via `enable_propagation` parameter in `NewsAnalyzer`)

### Relationship Weighting
- **Location:** `src/signals/sentiment_propagator.py` - `calculate_relationship_weight()`
- **Revenue-Based:** If `concentration_pct` available:
  - ≥20% revenue: Weight = 0.8
  - ≥10% revenue: Weight = 0.5
  - ≥5% revenue: Weight = 0.3
  - <5% revenue: Weight = 0.2
- **Confidence-Based (Default):**
  - High confidence: Weight = 0.7
  - Medium confidence: Weight = 0.5
  - Low confidence: Weight = 0.3
- **Tier 1 Default:** 0.5 (if no revenue/confidence data)
- **Tier 2 Default:** 0.2 (indirect relationships)
- **Configurable:** Yes (via `tier1_weight` and `tier2_weight` parameters)

### Propagation Formula
- **Location:** `src/signals/sentiment_propagator.py` - `propagate()` method
- **Formula:** `Propagated_Sentiment = Original_Sentiment × Relationship_Weight × Cumulative_Decay`
- **Cumulative Decay:** Tier 2 applies Tier 1 weight × Tier 2 weight
- **Example:** AAPL (+0.8) → Foxconn (Tier 1, weight 0.7) = +0.56
- **Hardcoded:** Yes (propagation algorithm)

### Integration
- **Location:** `src/signals/news_analyzer.py` - `analyze_news_for_ticker()`
- **Enable Flag:** `enable_propagation` parameter (default: True)
- **Output:** Adds `propagated_signals` list to news result
- **Source Type:** Direct signals marked `source_type='direct'`, propagated marked `source_type='propagated'`
- **Configurable:** Yes (via `enable_propagation` parameter)

### Cycle Prevention
- **Location:** `src/signals/sentiment_propagator.py` - `propagate()` method
- **Method:** Tracks visited tickers with tier level
- **Logic:** Skips if ticker already visited at same or lower tier
- **Hardcoded:** Yes (cycle detection logic)

---

## Signal Combination & Weighting

### Normalization Methods

#### Momentum Normalization
- **Location:** `src/signals/signal_combiner.py` - `combine_signals_direct()`
- **Method:** `tanh(momentum * 5)` then maps to [0, 1] via `(tanh + 1) / 2`
- **Scale Factor:** 5 (hardcoded)
- **Zero Handling:** Returns 0.5 if momentum is near zero
- **Hardcoded:** Yes (tanh scaling factor)

#### Volume Normalization
- **Location:** `src/signals/signal_combiner.py` - `combine_signals_direct()`
- **Method:** Log scale: `log(volume) / log(3.0)` maps 0.5→0.0, 1.0→0.5, 3.0→1.0
- **Neutral Value:** 0.5 if volume == 1.0
- **Hardcoded:** Yes (log base 3.0)

#### Sentiment Normalization
- **Location:** `src/signals/signal_combiner.py` - `combine_signals_direct()`
- **Method:** `(sentiment + 1.0) / 2.0` to map [-1, 1] → [0, 1]
- **Zero Handling:** If `abs(sentiment) < 0.001`, keeps as 0.0 (not 0.5)
- **Hardcoded:** Yes (0.001 threshold)

#### RSI Normalization
- **Location:** `src/signals/technical_analyzer.py` - `calculate_rsi()`
- **Method:** `((RSI - 30) / 40).clip(0, 1)`
- **Hardcoded:** Yes (30-70 range mapping)

### Signal Weights (Combined Mode)
- **Location:** `config/signal_weights.yaml` (default) or `test_signals.py` line 139
- **Default Weights:** supply_chain=0.40, sentiment=0.30, momentum=0.20, volume=0.10
- **Normalization:** Weights are normalized to sum to 1.0 if they don't already
- **Configurable:** Yes (via config file or code)

### Mode-Specific Weights
- **Location:** `test_signals.py` - Lines 767-778
- **Technical-Only:** momentum=0.5, volume=0.3, rsi=0.2, supply_chain=0.0, sentiment=0.0
- **News-Only:** supply_chain=0.5, sentiment=0.5, momentum=0.0, volume=0.0, rsi=0.0
- **Combined:** Uses weights from config file
- **Hardcoded:** Yes (mode-specific overrides)

### Weight Validation
- **Location:** `src/signals/signal_combiner.py` - `combine_signals_direct()`
- **Zero Weight Handling:** If all weights are 0, returns 0.5 (neutral)
- **Normalization:** Always normalizes weights to sum to 1.0
- **Hardcoded:** Yes (validation logic)

### Score Clipping
- **Location:** `src/signals/signal_combiner.py` - `combine_signals_direct()`
- **Final Score:** Clipped to [0.0, 1.0] range
- **News Scores:** Clipped to [-1.0, 1.0] before normalization
- **Hardcoded:** Yes (clipping bounds)

### ML Model Alternative
- **Location:** `test_signals.py` - Lines 771-795 (training), 892-908 (prediction)
- **Enable Flag:** `use_ml` in `config/model_config.yaml` (default: false)
- **When Enabled:** Uses ML model predictions instead of weighted signal combination
- **Fallback:** If ML prediction fails, falls back to weighted signals
- **Configurable:** Yes (via `use_ml` config flag)

---

## ML Regression Framework

### Model Selection
- **Location:** `config/model_config.yaml` - `active_model` field
- **Available Models:** linear, ridge, lasso, xgboost
- **Default:** linear (when ML enabled)
- **Switching:** Change `active_model` in config (no code changes)
- **Configurable:** Yes (via config file)

### Model Registry
- **Location:** `src/models/model_factory.py` - `MODEL_REGISTRY` dict
- **Pattern:** Registry maps config names to model classes
- **Models:** LinearReturnPredictor, RidgeReturnPredictor, LassoReturnPredictor, XGBoostReturnPredictor
- **Extensible:** Add new models by registering in factory
- **Hardcoded:** Yes (registry definition)

### Training Pipeline
- **Location:** `src/models/train_pipeline.py` - `ModelTrainingPipeline` class
- **Training Period:** `config/model_config.yaml` - `training.train_start` to `training.train_end`
- **Validation Split:** 20% of training data (configurable via `validation_split`)
- **Feature Extraction:** momentum_20d, volume_ratio_30d, rsi_14d, news_supply_chain, news_sentiment
- **Target:** Forward 1-week return (date to date+7 days)
- **Configurable:** Yes (via config file)

### Model Hyperparameters
- **Location:** `config/model_config.yaml` - `models.{model_type}` section
- **Linear:** No hyperparameters
- **Ridge:** `alpha` (default: 1.0)
- **Lasso:** `alpha` (default: 0.1)
- **XGBoost:** `n_estimators` (100), `max_depth` (3), `learning_rate` (0.1), `subsample` (0.8), `colsample_bytree` (0.8), `random_state` (42)
- **Configurable:** Yes (via config file)

### Model Persistence
- **Location:** `src/models/base_predictor.py` - `save_model()` method
- **Save Directory:** `models/saved/` (configurable via `model_save_dir`)
- **File Format:** `{model_type}_{timestamp}.pkl`
- **Auto-Save:** Enabled if `save_models: true` in config
- **Configurable:** Yes (via config file)

### Feature Importance Logging
- **Location:** `src/models/train_pipeline.py` - `_log_feature_importance()` method
- **Output:** Console and JSON file
- **File Location:** `logs/models/feature_importance_{timestamp}.json`
- **Auto-Log:** Enabled if `log_feature_importance: true` in config
- **Configurable:** Yes (via config file)

### Prediction Integration
- **Location:** `test_signals.py` - Lines 892-908
- **Feature Order:** Must match training order exactly (momentum, volume, rsi, supply_chain, sentiment)
- **Fallback:** If ML prediction fails, uses weighted signal combination
- **Hardcoded:** Yes (feature extraction order)

---

## Portfolio Construction & Rebalancing

### Stock Selection
- **Location:** `test_signals.py` - `run_backtest_with_preloaded_data()`
- **Method:** Rank by combined score, select top N
- **Default Top N:** 10 stocks (`--top-n` parameter, default=10)
- **Single Stock Handling:** Uses `min(len(scores), top_n)` to ensure selection
- **Configurable:** Yes (via `--top-n` CLI argument)

### Position Weighting
- **Location:** `test_signals.py` - Lines 866-883
- **Methods:** 
  - **Proportional:** `weight = score / sum(all_scores)` (default)
  - **Equal:** `weight = 1.0 / N` for all selected stocks
- **Zero Score Handling:** Falls back to equal weights if all scores are 0
- **Configurable:** Yes (via `weighting_method` parameter)

### Rebalancing Frequency
- **Location:** `test_signals.py` - Line 570
- **Frequency:** Weekly (Mondays only)
- **Date Generation:** `pd.date_range(signal_start, signal_end, freq='W-MON')`
- **Hardcoded:** Yes (Monday-only rebalancing)

### Position Assignment
- **Location:** `test_signals.py` - Lines 964-1000
- **Timing:** Positions set on Monday, held until next Monday
- **Assignment:** `positions_df.iloc[start_idx:end_idx, ticker_col] = signal_value`
- **Next Monday Logic:** Holds until day before next Monday (or end of data)
- **Zero Signal Handling:** Only assigns positions if `signal_value > 0`
- **Hardcoded:** Yes (weekly holding period, zero threshold)

### Transaction Costs
- **Location:** `test_signals.py` - Line 1008
- **Cost:** 0.001 (10 basis points) per rebalance
- **Application:** Only on days when positions change (`rebalance_dates`)
- **Detection:** `positions_df.diff().abs().sum(axis=1) > 0.01`
- **Hardcoded:** Yes (0.001 cost, 0.01 threshold)

### Portfolio Returns Calculation
- **Location:** `test_signals.py` - Line 998
- **Formula:** `(positions_df.shift(1) * returns).sum(axis=1).fillna(0)`
- **Shift Logic:** Uses NEXT day's returns (avoids lookahead bias)
- **Hardcoded:** Yes (shift(1) logic)

---

## Performance Measurement

### Sharpe Ratio Calculation
- **Location:** `test_signals.py` - Line 1012
- **Formula:** `(mean * 252) / (std * sqrt(252))` (annualized)
- **Zero Handling:** Returns 0.0 if std == 0
- **Annualization:** 252 trading days per year
- **Hardcoded:** Yes (252 days, sqrt annualization)

### Maximum Drawdown
- **Location:** `test_signals.py` - Line 1035
- **Method:** `((cumulative - expanding_max) / expanding_max).min()`
- **Calculation:** Uses expanding window maximum
- **Hardcoded:** Yes (expanding window method)

### Return Calculation
- **Location:** `test_signals.py` - Line 1009
- **Method:** `prices_df.pct_change()` (daily returns)
- **Cumulative:** `(1 + returns).cumprod()`
- **Hardcoded:** Yes (pct_change method)

---

## Data Processing & Edge Cases

### Missing Volume Data
- **Location:** Multiple locations
- **Default:** 1.0 (neutral signal)
- **Detection:** Checks if 'volume' column exists
- **Hardcoded:** Yes (1.0 default)

### Insufficient Price History
- **Location:** `src/signals/technical_analyzer.py` - `calculate_signals()`
- **Minimum:** 5 rows required (`len(df_filtered) < 5` check)
- **Behavior:** Returns default values if insufficient
- **Hardcoded:** Yes (5-row minimum)

### Empty News Results
- **Location:** `src/signals/gemini_news_analyzer.py` - `analyze_news_for_ticker()`
- **Behavior:** Returns `None` (no fallback values)
- **News-Only Mode:** Skips ticker entirely if no news
- **Combined Mode:** Uses technical signals only (news = 0.0)
- **Hardcoded:** Yes (None return, no fallback)

### Date Alignment Edge Cases
- **Location:** `test_signals.py` - Lines 930-939
- **No Overlap:** Returns zero metrics if no date overlap
- **Overlap Detection:** `overlap_start >= overlap_end` triggers error
- **Hardcoded:** Yes (overlap validation)

### List Response from LLM
- **Location:** `src/signals/gemini_news_analyzer.py` - Lines 447-475
- **Handling:** Averages scores, takes most common relationship
- **Empty List:** Skips batch
- **Hardcoded:** Yes (list handling logic)

### Zero Weight Handling
- **Location:** `src/signals/signal_combiner.py` - `combine_signals_direct()`
- **Behavior:** Returns 0.5 (neutral) if all weights are zero
- **Hardcoded:** Yes (0.5 fallback)

---

## Supply Chain Database

### Database Structure
- **Location:** `data/supply_chain_relationships.json`
- **Format:** JSON with `metadata` and `relationships` sections
- **Metadata:** `last_updated`, `version`, `default_stale_months` (default: 6)
- **Relationships:** Per-ticker entries with `suppliers`, `customers`, `competitors` arrays
- **Configurable:** Yes (via database file)

### Data Freshness
- **Location:** `src/data/supply_chain_manager.py` - `is_stale()` method
- **Default Stale Period:** 6 months (`default_stale_months` in metadata)
- **Stale Check:** Compares `last_verified` date to current date
- **Date Format:** YYYY-MM-DD or YYYY-MM
- **Configurable:** Yes (via metadata field)

### Auto-Research
- **Location:** `src/data/supply_chain_manager.py` - `_research_and_add()` method
- **Methods:** Reverse lookup, 10-K parsing, manual research queue
- **Reverse Lookup:** If ticker is supplier to known company, adds customer relationship
- **10-K Parsing:** Downloads SEC filings and extracts customer concentrations
- **Manual Queue:** Adds to `docs/RESEARCH_QUEUE.txt` if auto-research fails
- **Configurable:** Yes (via `auto_research` parameter)

### Database Coverage Check
- **Location:** `test_signals.py` - Lines 113-125
- **Check:** Verifies all stocks in universe have supply chain data
- **Warning:** Prints warning if stocks missing or stale
- **Action:** Suggests running `scripts/expand_database_core_stocks.py`
- **Configurable:** Yes (check can be disabled)

---

## LLM Configuration

### Model Selection
- **Location:** `src/signals/gemini_analyzer.py` - `__init__()`
- **Model:** `gemini-2.5-flash-lite` (paid tier)
- **Configurable:** Yes (via `model` parameter)

### API Configuration
- **Location:** `src/signals/gemini_analyzer.py` - `generate_content()`
- **Temperature:** 0.3
- **Top P:** 0.8
- **Top K:** 40
- **Max Output Tokens:** 500 (news), 1000 (single article)
- **Response Format:** JSON mode (`response_mime_type="application/json"`)
- **Hardcoded:** Yes (generation config)

### Proxy Bypass
- **Location:** `src/signals/gemini_analyzer.py` - Top-level imports
- **Method:** Removes `HTTP_PROXY`, `HTTPS_PROXY`, `http_proxy`, `https_proxy` env vars
- **Purpose:** Fixes connection issues with misconfigured proxies
- **Hardcoded:** Yes (proxy removal)

### Retry Logic
- **Location:** `src/signals/gemini_analyzer.py` - `analyze_article()`
- **Max Retries:** 3 attempts
- **Hardcoded:** Yes (3 retries)

---

## Additional Implementation Details

### DEBUG Mode Settings
- **Location:** `test_signals.py` - Lines 24-29
- **Settings:** `DEBUG_MODE`, `DEBUG_STOCKS`, `DEBUG_START_DATE`, `DEBUG_END_DATE`, `MAX_WEEKLY_ITERATIONS`
- **Purpose:** Fast iteration and testing
- **Fast-Fail:** Stops on first None result or error in DEBUG_MODE
- **Hardcoded:** Yes (debug flags)

### Fast-Fail Logic
- **Location:** `test_signals.py` - Lines 698-730
- **Behavior:** In DEBUG_MODE, stops immediately on first None news result or error
- **Iteration Limit:** Stops after `MAX_WEEKLY_ITERATIONS` weeks
- **Hardcoded:** Yes (fast-fail logic)

### Date Range Intersection vs Union
- **Price Data:** Uses intersection (most restrictive: max of starts, min of ends)
- **News Data:** Uses union for detection (min of starts, max of ends across sample), then filters to best month
- **Final Range:** Uses intersection of price and news ranges
- **Location:** `test_signals.py` - Lines 275-280 (price), 500-515 (overlap)
- **Hardcoded:** Yes (intersection/union logic)

### Technical Indicator Warmup Period
- **Location:** `test_signals.py` - Lines 543-567
- **Requirement:** 30 days of history before first signal date
- **Adjustment:** If 30 days exceeds end date, uses start date directly (no warmup)
- **Warning:** Prints warning if warmup period skipped
- **Hardcoded:** Yes (30-day requirement)

### News Article Field Mapping
- **Location:** `scripts/process_fnspid.py` - `convert_to_our_format()`
- **Title Fields:** Maps `Article_title`, `article_title`, `headline`, `title`, `headline_text` → `title`
- **Description Fields:** Maps `Lsa_summary`, `Luhn_summary`, `Textrank_summary`, `Lexrank_summary`, `summary`, `description`, `abstract` → `description`
- **Content Fields:** Maps `Article`, `article`, `content`, `text`, `body` → `content`
- **Date Fields:** Maps `Date`, `date`, `publishedAt` → `publishedAt`
- **Hardcoded:** Yes (field mapping logic)

### News Cache Structure
- **Location:** `src/signals/gemini_news_analyzer.py` - `JSONCache` class
- **Format:** JSON files in `data/cache/` directory
- **Naming:** `gemini_{ticker}_{date}.json`
- **Content:** Stores full signal dict with scores, relationship, reasoning
- **Hardcoded:** Yes (cache directory and naming)

### Signal DataFrame Structure
- **Location:** `test_signals.py` - Line 782
- **Index:** Monday dates (rebalance dates)
- **Columns:** Ticker symbols
- **Values:** Position weights (0.0 to 1.0)
- **Initialization:** All zeros, filled with weights during signal generation
- **Hardcoded:** Yes (DataFrame structure)

### Returns Calculation Method
- **Location:** `test_signals.py` - Line 1009
- **Method:** `prices_df.pct_change()` (pandas built-in)
- **Formula:** `(price[t] - price[t-1]) / price[t-1]`
- **NaN Handling:** First row is NaN (no previous price), filled with 0.0 in portfolio returns
- **Hardcoded:** Yes (pct_change method)

### Rebalance Date Detection
- **Location:** `test_signals.py` - Line 1006
- **Method:** `positions_df.diff().abs().sum(axis=1) > 0.01`
- **Threshold:** 0.01 (1% change in total portfolio weight)
- **Purpose:** Detects when positions change to apply transaction costs
- **Hardcoded:** Yes (0.01 threshold)

---

## Maintenance

### Auto-Update Process

**This document MUST be updated whenever:**
1. New parameters are added to code
2. Default values change
3. New algorithms are implemented
4. Configuration options are added/removed
5. Hardcoded thresholds are modified

**Update Checklist:**
- [ ] Add new section if major feature added (e.g., ML Framework, Propagation)
- [ ] Update existing sections with new parameters
- [ ] Update "Summary of Undiscussed Choices" if needed
- [ ] Update "Last Updated" date
- [ ] Update Table of Contents
- [ ] Verify all locations and configurable flags are accurate

**Review Frequency:**
- After each major feature addition
- Before each release/deployment
- When user reports parameter confusion

### Auto-Update Strategy

**When to Update This Document:**
1. **Parameter Changes:** Any hardcoded number, threshold, or limit is changed
2. **Algorithm Changes:** Normalization methods, combination formulas, or selection logic
3. **New Features:** New filters, modes, or configuration options added
4. **Default Value Changes:** Any default parameter value is modified
5. **Edge Case Handling:** New error handling or fallback logic added
6. **New Modes:** New trading modes or signal combination methods
7. **Data Processing:** Changes to data loading, filtering, or transformation logic

**How to Update:**
1. Find the relevant section in this document
2. Update the "WHAT" description if behavior changed
3. Update "Location" if code moved
4. Change "Hardcoded" to "Configurable" (or vice versa) if applicable
5. Add new entries for new parameters/choices
6. Update "Last Updated" date at top
7. Add to "Summary of Undiscussed Choices" if it's a new hardcoded assumption

**What NOT to Document:**
- Implementation details (how code works internally)
- Variable names (unless they're user-facing config)
- Line numbers (use function names instead)
- Temporary debug code
- Comments in code (unless they explain a choice)

**Quick Reference:**
- **Hardcoded:** Value is in code, requires code change to modify
- **Configurable:** Value can be changed via config file, CLI argument, or parameter
- **Location:** File name + function/method name (not line numbers)

**Automation Note:**
This document should be reviewed and updated as part of the code review process. Consider adding a checklist item: "Update MODEL_SPECIFICATION.md if parameters changed."

---

## Summary of Undiscussed Choices

The following implementation choices were made without explicit user discussion:

1. **30-day technical indicator warmup period** (hardcoded)
2. **Monday-only rebalancing** (hardcoded)
3. **10 basis points transaction cost** (hardcoded)
4. **Tanh momentum normalization with scale factor 5** (hardcoded)
5. **Log base 3.0 for volume normalization** (hardcoded)
6. **0.001 sentiment threshold for zero detection** (hardcoded)
7. **100,000 character truncation limit for LLM prompts** (hardcoded)
8. **3 articles per batch for LLM** (configurable but default hardcoded)
9. **0.5 second rate limiting** (configurable but default hardcoded)
10. **Best coverage algorithm for date selection** (hardcoded flag)
11. **Intersection method for price data range** (hardcoded)
12. **5-row minimum for price data** (hardcoded)
13. **0.01 threshold for rebalance detection** (hardcoded)
14. **252 trading days for Sharpe annualization** (hardcoded)
15. **Expanding window for max drawdown** (hardcoded)
16. **0.01 threshold for rebalance detection** (hardcoded)
17. **Market cap range $500M-$5B** (configurable default)
18. **Minimum price $1.00 filter** (configurable default)
19. **5-day short momentum period** (hardcoded in calculation)
20. **Monday-only rebalancing** (hardcoded)
21. **JSON response format for LLM** (hardcoded)
22. **3 retry attempts for LLM API calls** (hardcoded)
23. **500 max output tokens for news analysis** (hardcoded)
24. **1000 max output tokens for single article** (hardcoded)
25. **Field mapping for news article processing** (hardcoded)
26. **Fast-fail on None results in DEBUG mode** (hardcoded)
27. **Intersection method for price data range** (hardcoded)
28. **Union method for news data detection** (hardcoded, then filtered)
29. **Proportional weighting as default** (configurable)
30. **Equal weight fallback for zero scores** (hardcoded)

---

**End of Document**
