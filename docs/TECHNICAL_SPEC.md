# TECHNICAL_SPEC — Indicator Math & Signal Logic

**Last Updated:** 2026-02-15

This document defines technical indicator mathematics, Master Score computation, and signal combination logic. Backtest execution details live in `BACKTEST_JOURNAL.md`. Architecture lives in `ARCHITECTURE.md`.

---

## 1. Master Score (Source of Truth for Technical Signals)

**Module:** `src.signals.technical_library`  
**Config:** `config/technical_master_score.yaml`

The **Master Score** is the single source of truth for technical signals. Legacy RSI/Volume/Momentum formulas used in older backtests are superseded by this library.

### 1.1 Normalization Rules (No Look-Ahead)

**Bounded indicators** (values naturally in fixed range):
- RSI (0-100)
- Stochastic Oscillator (0-100)
- Williams %R (-100 to 0)

**Normalization:** Static scaling only
```python
normalized = value / 100  # or similar fixed transform
```

**Unbounded indicators** (no natural bounds):
- ATR (Average True Range)
- Volume Ratio
- MACD (Moving Average Convergence Divergence)
- ROC (Rate of Change)
- CCI (Commodity Channel Index)
- Momentum (5-day, 20-day)
- OBV (On-Balance Volume)
- CMF (Chaikin Money Flow)
- ADX (Average Directional Index)
- Bollinger Band position

**Normalization:** Rolling min-max over **past 252 days only**
```python
rolling_min = series.rolling(252, min_periods=20).min()
rolling_max = series.rolling(252, min_periods=20).max()
normalized = (value - rolling_min) / (rolling_max - rolling_min + ε)
normalized = clip(normalized, 0, 1)  # Force 0-1 range
# NaN values → 0.5 (neutral)
```

**Critical rule:** No future data permitted in rolling windows.

### 1.2 Category-Weighted Score

**Category structure:**

| Category | Default Weight | Purpose |
|----------|---------------|---------|
| **Trend** | 40% | Directional momentum, moving average signals |
| **Momentum** | 30% | Rate of change, oscillators |
| **Volume** | 20% | Trading activity, accumulation/distribution |
| **Volatility** | 10% | Risk measures, price dispersion |

**Sub-score calculation:**
```python
for each category:
    indicators_in_category = get_indicators_for_category(category)
    normalized_values = [ind_norm for ind in indicators_in_category]
    # Missing values → 0.5 (neutral)
    category_score = mean(normalized_values)
```

**Master Score formula:**
```python
master_score = (
    0.40 × trend_score +
    0.30 × momentum_score +
    0.20 × volume_score +
    0.10 × volatility_score
)
```

**Configuration:** Weights defined in `config/technical_master_score.yaml`

**Future state:** Dynamic weighting via regime/rolling/ml modes (see Section 1.4)

### 1.3 Indicator Library (pandas_ta)

All indicators computed using `pandas_ta` library.

**Trend indicators:**
- MACD (12, 26, 9)
- ADX (14)
- PSAR (Parabolic SAR)
- Aroon (25)
- Moving averages (SMA 50/200, EMA 12/26)

**Volatility indicators:**
- Bollinger Bands (20, 2)
- ATR (14)
- Keltner Channels (20, 2)

**Momentum indicators:**
- Stochastic Oscillator (14, 3, 3)
- CCI (20)
- Williams %R (14)
- ROC (10)
- RSI (14)
- Momentum (5-day, 20-day)

**Volume indicators:**
- OBV (On-Balance Volume)
- CMF (Chaikin Money Flow, 20)
- VWAP (Volume Weighted Average Price)
- Volume ratio (current vs 20-day average)

**Derived signals:**
- Golden Cross (SMA 50 > SMA 200)
- Death Cross (SMA 50 < SMA 200)
- MACD crossover
- Bollinger Band position (% within bands)

### 1.4 Dynamic Weighting (Formal Engines)

**Mode selection:** Via `weight_mode` in config or `--weight-mode` CLI flag

**Available modes:**

#### Mode: Fixed
- **Engine:** Configuration file
- **Logic:** Use static weights from YAML
- **Example:** Trend=40%, Momentum=30%, Volume=20%, Volatility=10%
- **Use case:** Baseline, stable strategy

#### Mode: Regime
- **Engine:** hmmlearn (3-State Gaussian HMM)
- **Function:** `get_regime_hmm(close_series, as_of_date, n_components=3)`
- **Process:**
  1. Fit HMM on SPY returns up to signal date
  2. Map states by mean return: highest=BULL, lowest=BEAR, middle=SIDEWAYS
  3. Select category weights per regime state
- **State → weights mapping:**
  - BULL → `BULL_WEIGHTS` (aggressive: higher momentum/trend)
  - BEAR → `DEFENSIVE_WEIGHTS` (conservative: higher volatility/volume)
  - SIDEWAYS → `SIDEWAYS_WEIGHTS` (balanced)
- **Transition matrix:** Fitted by Baum-Welch EM algorithm (no look-ahead)
- **Persistence check:** High diagonals (>0.80) indicate stable regime
- **Fallback:** SPY vs 200-SMA binary if HMM fails

#### Mode: Rolling
- **Engine:** PyPortfolioOpt
- **Methods:**
  - `max_sharpe`: EfficientFrontier optimization
  - `hrp`: Hierarchical Risk Parity
- **Process:**
  1. Build category strategy returns matrix
  2. Each column = one category sub-score
  3. Each row = sign(score − 0.5) × forward_return
  4. Optimize weights to maximize Sharpe or minimize risk
- **Safety:** `weight_bounds=(0.10, 0.50)` prevents extreme allocations
- **Function:** `get_optimized_weights(history_df, lookback_days=60, method='max_sharpe'|'hrp')`
- **No look-ahead:** Only data from T−1 or earlier used

#### Mode: ML
- **Engine:** Scikit-Learn Random Forest
- **Process:**
  1. Train RF regressor to predict next-day return from 4 category scores
  2. Cross-validation via TimeSeriesSplit (train always before test)
  3. Extract feature importances
  4. Normalize importances as category weights
- **Validation:** If CV R² < 0, fall back to fixed weights
- **Function:** `get_ml_weights(history_df, lookback_days=60, n_splits=5)`
- **No look-ahead:** CV folds strictly ordered by time

**Safety constraint (all modes):** Weight calculations for signal date T use only data from T−1 or earlier.

### 1.5 Position Sizing (Inverse Volatility)

**Formula:**
```python
weight_i = (1 / (ATR_norm_i + ε)) / sum_j(1 / (ATR_norm_j + ε))
```

Where:
- `ATR_norm_i` is normalized ATR for ticker i
- ATR from **Signal Day − 1** (strict no look-ahead)
- ε prevents division by zero (typically 1e-6)
- Weights normalized to sum = 1.0

**Implementation note:**
```python
# When computing weights for signal date T:
row_sizing = indicators_df.iloc[-2]  # T-1, when len >= 2
ATR_norm_value = row_sizing['ATR_norm']
```

### 1.6 API Reference

**Core functions:**

```python
def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all technical indicators and normalized columns.
    
    Input: OHLCV DataFrame
    Output: Original + raw indicators + *_norm columns
    """
    pass

def compute_signal_strength(
    row: pd.Series,
    weight_mode: str = 'fixed',
    spy_above_sma200: bool = None,
    regime_state: str = None,
    category_weights_override: dict = None,
    news_composite: float = None,
    news_weight: float = 0.0
) -> Tuple[float, dict]:
    """
    Compute Master Score for a single ticker at one point in time.
    
    Args:
        row: Single row from indicators DataFrame
        weight_mode: 'fixed', 'regime', 'rolling', 'ml'
        spy_above_sma200: SPY trend indicator (for regime fallback)
        regime_state: 'BULL', 'BEAR', 'SIDEWAYS' (for regime mode)
        category_weights_override: Custom weights (overrides mode)
        news_composite: News alpha score 0-1 (optional)
        news_weight: Blending weight for news (0-1)
    
    Returns:
        master_score: Final score 0-1
        result_dict: {
            'category_sub_scores': {...},
            'breakdown': {...},
            'news_composite': float or None,
            'regime_state': str or None
        }
    
    Formula with news:
        final_score = (1 - news_weight) × technical_score + news_weight × news_composite
    
    Example with 20% news:
        final_score = 0.8 × technical + 0.2 × news
    """
    pass

def get_optimized_weights(
    history_df: pd.DataFrame,
    lookback_days: int = 60,
    forward_days: int = 5,
    method: str = 'max_sharpe'  # or 'hrp'
) -> dict:
    """
    Compute category weights using PyPortfolioOpt.
    
    Args:
        history_df: Historical data with category scores
        lookback_days: Training window
        forward_days: Forward return period
        method: 'max_sharpe' (EfficientFrontier) or 'hrp' (HRP)
    
    Returns:
        weights_dict: {category: weight, ...}
        
    Constraints:
        - weight_bounds=(0.10, 0.50) per category
        - Uses only data from T-1 or earlier
    """
    pass

def get_regime_hmm(
    close_series: pd.Series,
    as_of_date: datetime,
    min_obs: int = 60,
    n_components: int = 3
) -> Tuple[str, dict]:
    """
    Detect market regime using 3-State Gaussian HMM.
    
    Args:
        close_series: SPY close prices
        as_of_date: Signal date (uses data <= as_of_date)
        min_obs: Minimum observations required (default 60)
        n_components: Number of HMM states (default 3)
        
    Returns:
        state_label: 'BULL', 'BEAR', or 'SIDEWAYS'
        info_dict: {
            'mean_return': float,
            'volatility': float,
            'transition_matrix': ndarray,
            'confidence': float (optional)
        }
        
    Fallback:
        If HMM fails or insufficient data:
        - SPY > 200-SMA → 'BULL'
        - SPY < 200-SMA → 'BEAR'
    """
    pass
```

---

## 2. News Alpha Strategies

**Module:** `src.signals.news_engine`  
**Input:** `data/news/{ticker}_news.json`

News Alpha provides orthogonal signal to technical indicators by analyzing financial news sentiment and supply chain relationships.

### 2.1 Four Sub-Strategies

#### Strategy A: Buzz (Volume-Based)
- **Metric:** Z-score of article count relative to baseline
- **Formula:** `z = (current_count - μ) / σ`
- **Baseline:** 30-day rolling average article count
- **Interpretation:** Rising media attention often precedes price moves
- **Output:** 0-1 normalized score

#### Strategy B: Surprise (Sentiment Delta)
- **Metric:** Current sentiment minus historical baseline
- **Formula:** `surprise = sent_current - sent_baseline`
- **Baseline:** 30-day historical sentiment average
- **Lag:** Uses T-1 baseline (no look-ahead)
- **Interpretation:** Sudden sentiment shifts predict returns
- **Output:** -1 to +1 (normalized to 0-1)

#### Strategy C: Sector Relative (Cross-Sectional)
- **Metric:** Ticker sentiment rank within sector/industry
- **Formula:** `percentile_rank(sentiment, peers)`
- **Universe:** All tickers in same sector with news
- **Interpretation:** Outperformers vs peers
- **Output:** 0-1 percentile rank

#### Strategy D: Event-Driven (Catalyst Detection)
- **Catalysts:** Earnings, M&A, FDA approvals, partnerships, product launches
- **Method:** spacy NER + EventDetector phrase matching
- **Weighting:** Event type importance (M&A > partnership > product)
- **Interpretation:** Identified catalysts boost attention
- **Output:** 0-1 event presence score

### 2.2 News Composite Formula

**Combination:**
```python
news_composite = (
    0.25 × buzz_score +
    0.35 × surprise_score +
    0.25 × sector_relative_score +
    0.15 × event_score
)
```

**Normalization:** All sub-scores normalized to [0, 1] before combination

**Safety:** If no news found, `news_composite = 0.0` (neutral)

### 2.3 Blending with Technical Score

**Master Score with News:**
```python
final_score = (1 - news_weight) × technical_score + news_weight × news_composite
```

**Default:** `news_weight = 0.20` (80% technical, 20% news)

**Configurable:** Via `.env` or config file

### 2.4 Sentiment Analysis Engine

**Primary model:** FinBERT (ProsusAI/finbert)
- Financial sentiment classification
- Output: positive/negative/neutral + confidence
- Runs locally (no API costs)

**Alternative model:** Gemini 2.5 Flash (for deep dives)
- Supply chain relationship extraction
- More nuanced analysis
- Requires API key

**Deduplication:**
- Levenshtein ratio > 0.85 → duplicate
- Prevents double-counting from multiple sources

### 2.5 Supply Chain Relationship Extraction

**Purpose:** Extract supplier/customer/product relationships from news

**LLM Accuracy (Empirical Testing):**

Based on testing with 5 stocks (AAPL, NVDA, AMD, TSLA, MSFT):

| Relationship Type | LLM Accuracy | Reliability |
|-------------------|--------------|-------------|
| **Suppliers** | 32.7% | ⚠️ **POOR** - Cannot rely on LLM alone |
| **Customers** | ~40% | ⚠️ **PARTIAL** - B2B relationships often missed |
| **Competitors** | 80.0% | ✅ **GOOD** - LLM reliable with ticker normalization |

**Key Findings:**

1. **Supplier Detection Issues:**
   - TSLA battery suppliers completely missed (0% accuracy)
   - Often confuses adjacent companies (semiconductor foundries for all tech stocks)
   - Random errors (e.g., listing consulting firms as MSFT customers)

2. **Systematic Errors:**
   - Ticker format issues (GOOG vs GOOGL, INTEL vs INTC)
   - Uses company names instead of tickers
   - Lists indirect relationships instead of direct ones

3. **Competitor Detection Success:**
   - Main issue is ticker normalization, not knowledge
   - Can achieve ~90% accuracy with proper mapping
   - Sometimes includes adjacent competitors (not direct)

**Recommended Approach:**

1. **For top 50-100 stocks:** Build manual database
   - Source: 10-K filings, Bloomberg, Reuters, company websites
   - Focus on supplier relationships (LLM weakest here)
   - Validate competitor lists (LLM strongest here)

2. **Use LLM as supplement:**
   - High confidence: Competitor relationships (with normalization)
   - Medium confidence: Customer relationships (B2B known relationships)
   - Low confidence: Supplier relationships (require validation)

3. **Confidence scoring:**
   - Manual database: confidence = 0.9-1.0
   - LLM competitors (normalized): confidence = 0.7-0.8
   - LLM suppliers/customers: confidence = 0.3-0.5

**Implementation:** `src/signals/news_engine.py` contains relationship extraction logic

---

## 3. Regime Detection (3-State HMM)

**Module:** `src.signals.weight_model`

### 3.1 Hidden Markov Model Setup

**States:** 3 (BULL, BEAR, SIDEWAYS)

**Observable:** SPY daily returns

**Training:** Baum-Welch EM algorithm on historical SPY data up to signal date

**State mapping:**
```python
# After fitting HMM, states have different mean returns
state_means = [mean(returns | state=i) for i in [0,1,2]]

# Map to labels by sorting means
highest_mean_state → 'BULL'
lowest_mean_state  → 'BEAR'
middle_mean_state  → 'SIDEWAYS'
```

### 3.2 State Characteristics

**Typical state statistics:**

| State | Mean Return | Volatility | Interpretation |
|-------|-------------|------------|----------------|
| BULL | +0.15% daily | Low | Uptrend, low vol |
| BEAR | -0.20% daily | High | Downtrend, high vol |
| SIDEWAYS | ~0% daily | Medium | Range-bound, choppy |

**Transition matrix example:**
```
       BULL   BEAR   SIDEWAYS
BULL   [0.85, 0.05,  0.10    ]  # Tends to persist
BEAR   [0.10, 0.80,  0.10    ]  # Sticky bear
SIDEWAYS [0.40, 0.10,  0.50    ]  # Can transition to bull
```

**Persistence:** High diagonal values (>0.80) indicate stable regimes

### 3.3 Fallback Rule

**When HMM fails:**
- Insufficient data (< 60 observations)
- Fitting errors
- Unstable transition matrix

**Binary fallback:**
```python
if SPY > SMA(SPY, 200):
    regime = 'BULL'
else:
    regime = 'BEAR'
```

### 3.4 No Look-Ahead Guarantee

**Training data:** Only SPY returns from dates ≤ signal_date

**Example:**
```python
# For Monday 2022-11-07 signal:
spy_data = spy_prices[spy_prices.index <= '2022-11-07']
regime = get_regime_hmm(spy_data['close'], as_of_date='2022-11-07')
```

---

## 4. Signal Combination (Formal Blending)

### 4.1 Technical + News Blend

**When news available:**
```python
final_score = (1 - α) × master_score + α × news_composite

where α = news_weight (typically 0.2)
```

**When news unavailable:**
```python
final_score = master_score  # Pure technical
```

### 4.2 Regime-Aware Weighting

**When regime mode enabled:**

1. Detect regime → ['BULL', 'BEAR', 'SIDEWAYS']
2. Load regime-specific category weights
3. Recompute master_score with regime weights
4. Blend with news (if available)

**Example regime weights:**
```python
BULL_WEIGHTS = {
    'trend': 0.50,      # Emphasize momentum
    'momentum': 0.35,
    'volume': 0.10,
    'volatility': 0.05  # De-emphasize risk
}

DEFENSIVE_WEIGHTS = {
    'trend': 0.20,
    'momentum': 0.20,
    'volume': 0.25,
    'volatility': 0.35  # Emphasize risk metrics
}
```

### 4.3 No Look-Ahead in Blending

**All signal inputs at date T use data from T-1 or earlier:**

```python
# Example for Monday 2022-11-07:
technical_indicators = calculate_all_indicators(price_data[:'2022-11-06'])
news_composite = compute_news_composite(news_data[:'2022-11-06'])
regime_state = get_regime_hmm(spy_data[:'2022-11-06'])
```

---

## 5. Dependencies & External Libraries

### 5.1 Core Libraries

**pandas_ta:**
- All technical indicators
- Version: Latest stable
- No custom TA from scratch

**numpy/pandas:**
- Data manipulation
- Array operations
- No custom statistical formulas

### 5.2 Dynamic Weighting Engines

**PyPortfolioOpt:**
- EfficientFrontier (max_sharpe method)
- HRPOpt (Hierarchical Risk Parity)
- Used in rolling mode for category weights

**hmmlearn:**
- Gaussian HMM (3 states)
- Baum-Welch EM algorithm
- Used in regime mode

**Scikit-Learn:**
- Random Forest Regressor
- TimeSeriesSplit (time-series cross-validation)
- Used in ML mode

### 5.3 News Alpha Engines

**transformers + ProsusAI/finbert:**
- Sentiment analysis on headlines/bodies
- Input: `data/news/{ticker}_news.json`

**spacy (en_core_web_md):**
- Named Entity Recognition
- EventDetector for catalysts
- Phrase matching
- Installation: `python -m spacy download en_core_web_md`

**Levenshtein:**
- Fuzzy string matching
- Headline deduplication
- Threshold: ratio > 0.85

### 5.4 Execution

**ib_insync:**
- IBKR TWS integration
- Order submission
- Position tracking

---

## 6. Implementation Notes

### 6.1 No Custom Math from Scratch

**Principle:** Use established quantitative libraries for all complex calculations.

**Forbidden:**
- Custom optimization algorithms (use PyPortfolioOpt)
- Custom ML implementations (use Scikit-Learn)
- Custom statistical models (use hmmlearn, statsmodels)

**Allowed:**
- Simple arithmetic operations
- Data transformations
- Wrapper functions around library calls

### 6.2 Normalization Standards

**Bounded indicators:**
- Static formulas only (division by fixed value)
- No machine learning for normalization

**Unbounded indicators:**
- Rolling min-max only
- No sklearn StandardScaler or other ML-based normalizers

**Rationale:**
- Simpler logic
- More transparent
- Easier to debug
- No look-ahead from fitted transformers

### 6.3 Safety Constraints

**All computations must:**
1. Use only T−1 or earlier data
2. Be deterministic (same inputs → same outputs)
3. Handle missing data explicitly (NaN → 0.5 neutral)
4. Clip outputs to expected ranges
5. Log warnings for edge cases

---

## 7. Strategy Selector and Memory System

### 7.1 Strategy Selector Logic

**Purpose:** Connect HMM regime detection to strategy execution via regime_ledger.csv lookup

**Status:** Documented but not yet integrated into canonical workflow (see PROJECT_STATUS.md)

#### Strategy ID Format

```
Full format:  nw{news_weight}_h{horizon}_r{risk}
Short format: nw{news_weight}_r{risk}

Examples:
- nw0.3_h5_r1.0 → news_weight=0.3, horizon=5 days, risk_scale=1.0
- nw0.2_r0.5    → news_weight=0.2, horizon=5 (default), risk_scale=0.5
```

Parsed by `parse_strategy_id()` in `src/signals/weight_model.py`

#### Winning Profile Selection Algorithm

**Input:** Current regime (BULL/BEAR/SIDEWAYS)

**Steps:**
1. Load `data/logs/regime_ledger.csv`
2. Filter rows where `Regime == current_regime`
3. Keep **last 4 occurrences** of this regime
4. For each unique `Strategy_ID` in those rows:
   - Compute **Win Rate** = fraction of weeks with Return > 0
   - Compute **Profit Factor** = gross_profits / gross_losses
5. Select `Strategy_ID` with **highest Win Rate**
6. If tied: choose **lowest Max_Drawdown** (least negative)

**Safety rules:**
- If ledger has < 2 occurrences of regime → no override, use config defaults
- If winning profile has negative Sharpe → no override, use config defaults
- If ledger file missing/unreadable → no override, use config defaults

**Output:** Override parameters (news_weight, signal_horizon_days, sideways_risk_scale) for upcoming week

#### CLI Usage

```bash
python scripts/backtest_technical_library.py --dynamic-selector
```

When enabled: after regime detection on each Monday, calls `StrategySelector.get_winning_profile(regime)` and overrides weights from winning profile (if available)

---

### 7.2 Regime Ledger Schema

**File:** `data/logs/regime_ledger.csv`

**Purpose:** Persistent memory by market state

**Columns:**
```
Timestamp, Regime, Strategy_ID, Return, Max_Drawdown
```

**Example:**
```csv
Timestamp,Regime,Strategy_ID,Return,Max_Drawdown
2022-11-07,BEAR,nw0.3_r0.5,0.0234,-0.0156
2022-11-14,BEAR,nw0.2_r0.5,0.0189,-0.0201
2022-11-21,SIDEWAYS,nw0.3_r1.0,0.0156,-0.0089
```

**Update function:**
```python
update_regime_ledger(
    regime: str,           # 'BULL', 'BEAR', or 'SIDEWAYS'
    combination_id: str,   # Strategy ID (e.g., 'nw0.3_r0.5')
    weekly_return: float,  # That week's return
    weekly_drawdown: float # That week's max drawdown
)
```

**Default path:** `data/logs/regime_ledger.csv` (overridable via `ledger_path` parameter)

**Known gap:** Not updated by canonical backtest code (see DECISIONS.md D005)

---

### 7.3 Regime-Specific Sortino Ratio

**Formula:**
```
Sortino = (R_p - R_f) / σ_d

where:
- R_p = portfolio return
- R_f = risk-free rate (default 0)
- σ_d = downside deviation (only returns below R_f)
```

**Implementation:**
```python
def calculate_regime_sortino(returns, risk_free_rate=0):
    """
    Calculate Sortino ratio using only downside deviations.
    
    Args:
        returns: Series or array of returns
        risk_free_rate: Threshold return (default 0)
        
    Returns:
        float: Sortino ratio
    """
    excess_returns = returns - risk_free_rate
    downside_returns = excess_returns[excess_returns < 0]
    
    if len(downside_returns) == 0:
        return np.inf if excess_returns.mean() > 0 else 0
    
    downside_std = np.std(downside_returns)
    if downside_std == 0:
        return np.inf if excess_returns.mean() > 0 else 0
        
    return excess_returns.mean() / downside_std
```

**BULL Regime Constraint:**

For BULL regimes, **strictly ignore upside volatility**:
- Only downside deviations (returns < 0) enter σ_d
- Avoids mistakenly throttling high-performing bull strategies
- Strategy Selector should not punish upside in bull markets

**Usage:**

```python
# In Strategy Selector audit
from src.signals.metrics import calculate_regime_sortino

# Filter ledger for current regime
regime_returns = ledger_df[ledger_df['Regime'] == 'BULL']['Return']

# Calculate Sortino for this regime
sortino = calculate_regime_sortino(regime_returns, risk_free_rate=0)

# Compare to current strategy
if sortino > current_strategy_sortino:
    log_memory_alert(f"Last time in BULL, better Sortino: {sortino}")
```

---

### 7.4 Memory Audit Function

**Purpose:** Prevents "historical amnesia" by checking past regime performance

**Function:**
```python
def audit_past_performance(
    current_regime: str,
    current_strategy_id: str = None,
    current_sortino: float = None
) → None:
    """
    Audit past performance in current regime and log alerts.
    
    Args:
        current_regime: 'BULL', 'BEAR', or 'SIDEWAYS'
        current_strategy_id: Currently active strategy
        current_sortino: Current strategy's Sortino ratio
        
    Logs:
        [MEMORY] alerts when past strategies had better performance
    """
    # 1. Read regime_ledger.csv
    # 2. Filter by current_regime
    # 3. Calculate average Sortino per Strategy_ID
    # 4. Log alert if better strategy exists
```

**Example log output:**
```
[MEMORY] Last time in BEAR, Strategy_X had Sortino of 1.4. 
         Current Strategy Sortino: 0.8. Suggesting switch...
```

**When to call:**
- On each rebalance (e.g. every Monday)
- After determining current regime
- Before final portfolio construction

---

This specification is the authoritative reference for all technical signal computation. Any conflicts between this document and code should be resolved in favor of this document.
