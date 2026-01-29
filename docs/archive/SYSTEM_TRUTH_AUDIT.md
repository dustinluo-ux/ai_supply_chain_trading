# System Truth Audit

**Date:** 2026-01-25  
**Purpose:** Truthful assessment of what actually runs vs. what exists in codebase  
**Methodology:** Code is source of truth. Only runnable paths count.

---

## SYSTEM TRUTH TABLE

### 1. Universe Selection
**Status:** ✅ **IMPLEMENTED & USED**  
**File:** `src/data/universe_loader.py`  
**Usage:** `test_signals.py` line 89-99  
**What Actually Runs:**
- Loads tickers from CSV files in `data/prices/` subdirectories
- Filters by date range, min data points, price thresholds
- **Supply chain ranking:** If `rank_by_supply_chain=True`, calls `_rank_by_supply_chain()` which:
  - Instantiates `SupplyChainScanner` with Gemini (`llm_provider="gemini"`)
  - Scans all tickers for supply chain scores
  - Ranks by `supply_chain_score` (descending)
  - Returns top N tickers
- Falls back to alphabetical if ranking fails
**Truth:** ✅ Works, uses Gemini for ranking when enabled

---

### 2. Supply Chain Scoring
**Status:** ✅ **IMPLEMENTED & USED**  
**File:** `src/signals/supply_chain_scanner.py`  
**Usage:** 
- Called by `UniverseLoader._rank_by_supply_chain()` (line 478)
- Called by `NewsAnalyzer` via `GeminiNewsAnalyzer` (indirectly)
**What Actually Runs:**
- `SupplyChainScanner` processes news articles through LLM
- Uses Gemini 2.5 Flash Lite by default (when `llm_provider="gemini"`)
- Extracts supplier/customer relationships
- Calculates `supply_chain_score` from:
  - AI relevance (40% weight if relationships exist, 20% if not)
  - Supplier/customer mentions (30% if relationships exist, 0% if not)
  - Relevance score (20%)
  - Sentiment ratio (10%)
- Caches results in `data/{ticker}_extractions.json`
- Post-processing filter: Sets `ai_related=False` if no relationships extracted
**Truth:** ✅ Works, uses Gemini, has false-positive filters

---

### 3. News Analysis (Gemini)
**Status:** ✅ **IMPLEMENTED & USED**  
**File:** `src/signals/news_analyzer.py`, `src/signals/gemini_news_analyzer.py`  
**Usage:** `test_signals.py` line 706-714, 735  
**What Actually Runs:**
- `NewsAnalyzer` wraps `GeminiNewsAnalyzer`
- Reads from `data/news/{ticker}_news.json`
- Analyzes articles in lookback window (default 7 days)
- Returns `supply_chain_score`, `sentiment_score`, `confidence`
- **Returns `None` if no news found** (no fallback values)
- Optional sentiment propagation via `SentimentPropagator`
- Caches Gemini responses in `data/cache/gemini_*.json`
**Truth:** ✅ Works, uses Gemini API, returns None if no news

---

### 4. Sentiment vs Supply-Chain Separation
**Status:** ✅ **IMPLEMENTED & USED**  
**File:** `src/signals/gemini_news_analyzer.py`  
**Usage:** Via `NewsAnalyzer.analyze_news_for_ticker()`  
**What Actually Runs:**
- Gemini extracts separate fields:
  - `supply_chain_score`: AI supply chain relevance (0-1)
  - `sentiment_score`: News sentiment (-1 to +1)
  - `confidence`: Analysis confidence (0-1)
- These are separate signals combined later
- Sentiment propagation can spread sentiment to related companies
**Truth:** ✅ Separate signals, combined in `SignalCombiner`

---

### 5. Technical Indicators
**Status:** ✅ **IMPLEMENTED & USED**  
**File:** `test_signals.py` lines 547-692 (inline calculation)  
**Usage:** Pre-calculated in `tech_signals_cache`  
**What Actually Runs:**
- **Momentum:** `(close[-5] - close[-20]) / close[-20]`
- **Volume ratio:** `volume[-1] / rolling_mean(volume, 30)`
- **RSI:** Standard RSI(14), normalized to 0-1
- Calculated for all Mondays, cached before backtest
- Falls back to defaults if insufficient data:
  - `momentum_score: 0.0`
  - `volume_score: 1.0` (neutral)
  - `rsi_score: 0.5` (neutral)
**Truth:** ✅ Simple inline calculation, no external library

---

### 6. Signal Combination
**Status:** ✅ **IMPLEMENTED & USED**  
**File:** `src/signals/signal_combiner.py`, `test_signals.py` lines 838-948  
**Usage:** `SignalCombiner.combine_signals_direct()`  
**What Actually Runs:**
- Combines 5 signals with configurable weights:
  - `supply_chain_score` (default 0.4)
  - `sentiment_score` (default 0.3)
  - `momentum_score` (default 0.2)
  - `volume_score` (default 0.1)
  - `rsi_score` (default 0.2, combined with momentum in tech-only mode)
- Weights from `config/signal_weights.yaml`
- Optional ML model prediction (if `use_ml=True` in `config/model_config.yaml`)
- Falls back to weighted combination if ML fails
**Truth:** ✅ Works, supports ML or weighted combination

---

### 7. Portfolio Construction
**Status:** ✅ **IMPLEMENTED & USED**  
**File:** `test_signals.py` lines 955-1092  
**Usage:** Inline in `run_backtest_with_preloaded_data()`  
**What Actually Runs:**
- **Stock selection:** Top N stocks by combined signal score
- **Weighting:** Two methods (from config):
  - `proportional`: `weight = score / sum(all_scores)`
  - `equal`: `weight = 1/N` for all selected
- **Position assignment:** Weights assigned to positions DataFrame
- **Rebalancing:** Weekly on Mondays
- **No position limits:** No max 15% cap, no volatility targeting
- **No risk scaling:** Weights not adjusted for volatility
**Truth:** ✅ Simple proportional/equal weighting, no constraints

---

### 8. Portfolio Optimization
**Status:** ❌ **NOT IMPLEMENTED**  
**File:** `src/portfolio/optimizer.py` - **DOES NOT EXIST**  
**Usage:** **NOT USED**  
**What Actually Runs:**
- Nothing. Portfolio optimizer was never ported.
- Current system uses simple proportional/equal weighting
- No risk-scaled weighting, no position limits, no volatility targeting
**Truth:** ❌ Documentation claims it exists, but it doesn't

---

### 9. Backtest Engine
**Status:** ⚠️ **IMPLEMENTED BUT UNUSED**  
**File:** `src/backtest/backtest_engine.py`  
**Usage:** **NOT IMPORTED IN test_signals.py**  
**What Actually Runs:**
- `test_signals.py` does **inline backtesting** (lines 1012-1138)
- Calculates returns: `portfolio_returns = (positions_df.shift(1) * returns).sum(axis=1)`
- Applies transaction costs: `-0.001` (10 bps) on rebalance dates
- Calculates metrics: Sharpe, total return, max drawdown
- `BacktestEngine` class exists but is **never instantiated**
**Truth:** ⚠️ Backtest engine exists but unused. Inline backtest is what runs.

---

### 10. Multi-Month Backtest Support
**Status:** ✅ **IMPLEMENTED & USED**  
**File:** `test_signals.py` lines 327-544  
**Usage:** Date range detection and filtering  
**What Actually Runs:**
- **Best-coverage approach:** Finds month with most tickers having news
- Filters to tickers with BOTH price data AND news in that period
- Falls back to union approach if best-coverage fails
- Validates date overlap between signals and prices
- **Limitation:** Uses single month for news (compromise approach)
**Truth:** ✅ Works but uses single best-coverage month, not full multi-month

---

### 11. Statistical Validation
**Status:** ⚠️ **PARTIAL**  
**File:** `test_signals.py` lines 1124-1132  
**Usage:** Calculates Sharpe, return, drawdown  
**What Actually Runs:**
- **Sharpe ratio:** `(mean * 252) / (std * sqrt(252))`
- **Total return:** `cumprod(1 + returns)[-1] - 1`
- **Max drawdown:** `(cumulative - expanding_max) / expanding_max).min()`
- **No:** Walk-forward analysis, Monte Carlo, significance tests
**Truth:** ⚠️ Basic metrics only, no advanced validation

---

### 12. Interactive Brokers Integration
**Status:** ⚠️ **IMPLEMENTED BUT UNUSED**  
**Files:**
- `src/data/ib_provider.py`
- `src/execution/ib_executor.py`
- `src/data/provider_factory.py`
- `src/execution/executor_factory.py`
- `config/trading_config.yaml`
**Usage:** **NOT IMPORTED IN test_signals.py**  
**What Actually Runs:**
- **Nothing.** `test_signals.py` reads CSV files directly (lines 247-248)
- IB components exist but are **never instantiated**
- `trading_config.yaml` exists but is **never read**
- No mode switching logic in `test_signals.py`
**Truth:** ⚠️ IB integration code exists but is completely unused. System only does CSV backtesting.

---

### 13. Mode Switching (backtest / paper / live)
**Status:** ❌ **NOT IMPLEMENTED**  
**File:** `test_signals.py`  
**Usage:** **DOES NOT EXIST**  
**What Actually Runs:**
- **Nothing.** `test_signals.py` only does CSV backtesting
- No `DataProviderFactory` or `ExecutorFactory` imports
- No config reading from `trading_config.yaml`
- No mode switching logic
**Truth:** ❌ Documentation claims mode switching exists, but it's not in the main script

---

### 14. Risk Management
**Status:** ⚠️ **IMPLEMENTED BUT UNUSED**  
**File:** `src/risk/risk_calculator.py`  
**Usage:** **NOT IMPORTED IN test_signals.py**  
**What Actually Runs:**
- **Nothing.** Risk calculator exists but is never called
- No VaR calculations in backtest
- No position limits enforced
- No volatility targeting
- Transaction costs are hardcoded: `-0.001` (10 bps)
**Truth:** ⚠️ Risk components exist but unused. No risk management in actual backtest.

---

## CANONICAL ARCHITECTURE SUMMARY

### What The System Does

**Entry Point:** `test_signals.py`

**Execution Flow:**
1. **Universe Selection** (`UniverseLoader`)
   - Loads tickers from CSV files
   - Optionally ranks by supply chain relevance (Gemini)
   - Filters by date range, data quality

2. **Data Loading**
   - Price data: Reads CSV files directly (`pd.read_csv`)
   - News data: Reads JSON files from `data/news/`
   - No data provider abstraction used

3. **Signal Generation** (pre-calculated)
   - **Technical signals:** Inline calculation (momentum, volume, RSI)
   - **News signals:** `NewsAnalyzer` → `GeminiNewsAnalyzer` → Gemini API
   - Cached in dictionaries before backtest

4. **Signal Combination**
   - `SignalCombiner.combine_signals_direct()`
   - Weighted combination or ML prediction
   - Ranks stocks by combined score

5. **Portfolio Construction**
   - Selects top N stocks
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

### What Assumptions It Makes

1. **Data Format:**
   - Price data: CSV with `close` column, date index
   - News data: JSON array in `data/news/{ticker}_news.json`
   - News articles have `publishedAt` field

2. **Date Alignment:**
   - Uses "best coverage" month (most tickers with news)
   - Requires overlap between price and news data
   - Falls back to price-only if no overlap

3. **Signal Quality:**
   - News signals can be `None` (no fallback)
   - Technical signals have defaults if insufficient data
   - ML model is optional (falls back to weighted)

4. **Trading:**
   - Weekly rebalancing on Mondays
   - No slippage modeling (only 10 bps transaction cost)
   - No position limits or risk constraints

---

### What Data It Uses

1. **Price Data:**
   - Source: CSV files in `data/prices/` subdirectories
   - Required columns: `close` (optionally `volume`)
   - Date range: Configurable, defaults to 2023

2. **News Data:**
   - Source: JSON files in `data/news/`
   - Format: Array of articles with `publishedAt`, `title`, `content`
   - Analyzed by Gemini API (cached)

3. **Supply Chain Data:**
   - Generated on-the-fly by `SupplyChainScanner`
   - Cached in `data/{ticker}_extractions.json`
   - Used for universe ranking

---

### How Weekly Trading Works End-to-End

**Monday (Signal Generation):**
1. Load price data up to Monday
2. Calculate technical signals (momentum, volume, RSI)
3. Load news articles from last 7 days
4. Analyze news with Gemini (supply chain + sentiment)
5. Combine signals (weighted or ML)
6. Rank stocks by combined score
7. Select top N stocks
8. Assign weights (proportional or equal)

**Monday-Friday (Position Holding):**
1. Hold positions at assigned weights
2. Calculate daily returns: `(positions * returns).sum()`
3. No rebalancing until next Monday

**Next Monday (Rebalancing):**
1. Calculate new signals
2. Compare new weights to current positions
3. Rebalance if weights changed (apply 10 bps cost)
4. Repeat

---

### What Is Explicitly Out of Scope Today

1. **Live Trading:**
   - No IB integration in main script
   - No order execution
   - No position management

2. **Advanced Portfolio Management:**
   - No position limits (max 15% per stock)
   - No volatility targeting
   - No risk-scaled weighting
   - No covariance matrix calculations

3. **Advanced Risk Management:**
   - No VaR calculations
   - No margin monitoring
   - No stop-loss enforcement

4. **Multi-Model Blending:**
   - Single signal source (combined signals)
   - No separate model weights
   - No ensemble optimization

5. **Advanced Backtesting:**
   - No walk-forward analysis
   - No Monte Carlo simulation
   - No statistical significance tests
   - No regime-based analysis

---

## DOCUMENTATION CLEANUP PLAN

| Document | Action | Reason |
|----------|--------|--------|
| `docs/INTEGRATION_FINAL_SUMMARY.md` | ⚠️ **UPDATE** | Claims 21 components ported, but many unused |
| `docs/IB_INTEGRATION_SUMMARY.md` | ⚠️ **UPDATE** | Claims "IMPLEMENTATION COMPLETE" but IB not used |
| `docs/INTEGRATION_ARCHITECTURE.md` | ⚠️ **UPDATE** | Describes mode switching that doesn't exist |
| `docs/IB_INTEGRATION_GUIDE.md` | ⚠️ **UPDATE** | Guide for integration that's not used |
| `docs/NOT_PORTED_COMPONENTS.md` | ✅ **KEEP** | Accurate list of what's not ported |
| `docs/PORTFOLIO_OPTIMIZER_EXPLAINED.md` | ✅ **KEEP** | Explains what optimizer would do |
| `docs/ALL_COMPONENTS_INVENTORY.md` | ⚠️ **UPDATE** | Needs "USED" vs "UNUSED" status |
| `docs/INTEGRATION_STATUS.md` | ⚠️ **UPDATE** | Claims components are used |
| `docs/INTEGRATION_PROGRESS.md` | ⚠️ **UPDATE** | Progress tracking but doesn't show usage |
| `docs/MISSING_COMPONENTS.md` | ✅ **KEEP** | Lists what's missing |
| `docs/IB_PROJECT_INVENTORY.md` | ✅ **KEEP** | Historical reference |
| `docs/BEYOND_IB_INVENTORY.md` | ✅ **KEEP** | Historical reference |
| `docs/MEDIUM_PRIORITY_COMPONENTS_COMPLETE.md` | ⚠️ **UPDATE** | Claims completion but not used |
| `docs/COMPREHENSIVE_COMPONENT_INVENTORY.md` | ⚠️ **UPDATE** | Needs usage status |

**Recommended Actions:**
1. Add "USED" vs "UNUSED" column to all inventory docs
2. Update integration summaries to clarify: "Code exists but not used in main script"
3. Create `docs/ACTUAL_SYSTEM_ARCHITECTURE.md` (this document)
4. Archive planning docs to `docs/archive/` (INTEGRATION_ARCHITECTURE, IB_INTEGRATION_GUIDE)

---

## "IF I WERE LYING" SECTION

### Claims That Look True But Are False/Misleading

1. **"IB Integration Complete"**
   - **Reality:** Code exists but is **never imported or used** in `test_signals.py`
   - **Impact:** User might think they can switch to paper trading, but it won't work

2. **"Mode Switching (backtest/paper/live)"**
   - **Reality:** No mode switching logic exists in main script
   - **Impact:** `trading_config.yaml` is ignored

3. **"Portfolio Optimizer"**
   - **Reality:** Never ported, doesn't exist
   - **Impact:** Documentation discusses it as if it exists

4. **"21 Components Ported"**
   - **Reality:** 21 components exist in codebase, but many are **unused**
   - **Impact:** Misleading completion percentage

5. **"Risk Management"**
   - **Reality:** `risk_calculator.py` exists but is never called
   - **Impact:** No actual risk management in backtest

6. **"Backtest Engine"**
   - **Reality:** `BacktestEngine` class exists but is unused. Inline backtest runs instead.
   - **Impact:** Confusion about which backtest logic is active

---

### Parts That Might Fail Silently at Runtime

1. **News Analysis Returns None**
   - If no news found, `news_signals_cache[ticker][date_str] = None`
   - Code handles this with defaults: `news_signals.get('supply_chain_score', 0.0)`
   - **Risk:** Silent fallback to zeros might hide data quality issues

2. **Supply Chain Ranking Falls Back to Alphabetical**
   - If `SupplyChainScanner` fails, returns `sorted(tickers)`
   - **Risk:** User might not notice ranking didn't work

3. **Date Range Mismatch**
   - If price/news dates don't overlap, uses price-only
   - **Risk:** News analysis runs but finds no articles, silently uses zeros

4. **ML Model Failure**
   - If ML prediction fails, falls back to weighted combination
   - **Risk:** User might think ML is working when it's not

5. **Volume Data Missing**
   - If CSV has no `volume` column, uses default `1.0`
   - **Risk:** Volume signal is neutral, but user might not know

---

### Fallback / Mock Behavior That Could Invalidate Backtests

1. **Default Signal Values**
   - Technical signals: `momentum=0.0`, `volume=1.0`, `rsi=0.5` if insufficient data
   - News signals: `supply_chain=0.0`, `sentiment=0.0` if no news
   - **Impact:** Stocks with missing data get neutral scores, might still be selected

2. **Alphabetical Fallback for Ranking**
   - If supply chain ranking fails, uses alphabetical order
   - **Impact:** Universe selection might not reflect AI relevance

3. **Equal Weighting Fallback**
   - If all scores are zero, uses equal weights
   - **Impact:** Portfolio might be equally weighted when it shouldn't be

4. **Transaction Cost Simplification**
   - Hardcoded 10 bps on rebalance dates only
   - **Impact:** Underestimates trading costs (no slippage, no market impact)

5. **No Position Limits**
   - Single stock can get 100% weight if it has highest score
   - **Impact:** Unrealistic concentration risk

---

## SUMMARY

**What Actually Runs:**
- CSV-based backtesting with inline signal calculation
- Gemini-based news analysis (supply chain + sentiment)
- Simple proportional/equal weighting
- Weekly rebalancing with basic transaction costs

**What Exists But Is Unused:**
- IB data provider and executor
- Risk calculator
- Portfolio optimizer (doesn't exist)
- Backtest engine class
- Mode switching logic

**Critical Gaps:**
- No live trading capability (despite IB code existing)
- No risk management (despite risk code existing)
- No position limits or volatility targeting
- No advanced backtesting features

**Documentation Issues:**
- Many docs claim features are "complete" when code is unused
- Integration summaries don't distinguish "exists" from "used"
- Architecture docs describe planned features, not actual system

---

**Status:** ✅ **AUDIT COMPLETE**  
**Next Steps:** Update documentation to reflect actual system state
