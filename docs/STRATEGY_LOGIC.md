# STRATEGY_LOGIC — Capital Decision Spine

**Last Updated:** 2026-02-15

This document defines how capital allocation decisions are made. All parameters below marked as **PLACEHOLDER** must be replaceable by future dynamic engines.

---

## Capital Decision Stack (Authoritative Order)

Decisions flow through these layers in strict order. No layer may bypass another.

1. **Technical Master Score** — Base signal from indicators
2. **News Overlay** — Mandatory sentiment/event input (with optional propagation)
3. **Regime Overlay** — Market state detection and adaptation
4. **Policy Gates** — Risk management and kill-switches
5. **Strategy Parameter Selection** — Memory-aware configuration
6. **Portfolio Construction** — Ranking and position sizing (weighted or ML-based)
7. **Execution Layer** — Trade timing and friction

---

## 1. Technical Base Signal

**Definition:** The Master Score is the foundation of all capital decisions.

**Computation:** See `TECHNICAL_SPEC.md` for complete indicator math.

**Category structure (PLACEHOLDER weights):**

| Category | Weight | Purpose |
|----------|--------|---------|
| Trend | 40% | Directional momentum and moving average signals |
| Momentum | 30% | Rate of change and oscillator signals |
| Volume | 20% | Trading activity and accumulation/distribution |
| Volatility | 10% | Risk and price dispersion measures |

**Current status:** Fixed percentages are temporary scaffolding.

**Future state:** Dynamic weighting engine only (no hard-coded weights).

**Normalization:**
- Bounded indicators (RSI, Stochastic): Static scaling
- Unbounded indicators (ATR, Volume Ratio): Rolling min-max over past 252 days
- No look-ahead permitted

---

## 2. News Overlay (Mandatory Input)

**Principle:** News is a first-class input, not an optional enhancement.

**News state classification:**

| State | Condition | Action |
|-------|-----------|--------|
| `PRESENT` | News files exist and readable | Compute news_score |
| `EMPTY` | News files exist but yield no signal | Set news_score = 0 (valid) |
| `ERROR` | News files missing/unreadable/malformed | **STOP execution** |

**Blending formula (PLACEHOLDER):**

```
Final_Score = (1 − news_weight) × Technical_Score + news_weight × News_Composite
```

Where:
- `news_weight` configured via `.env` or config file
- Current value (0.20) is placeholder only
- Future state: Adaptive blending model based on news quality/recency

**Prohibitions:**
- No silent fallback to "technical-only"
- No implicit defaults when news is missing
- No downgrade of news importance without explicit flag

**Rationale:**
- Absence of news is information
- Silent downgrade causes invisible regime drift
- Explicit state tracking enables better diagnostics

---

### 2.1 Sentiment Propagation (Network Effect)

**Purpose:** News about one company affects related companies through supply chain relationships

**Mechanism:** Sentiment automatically propagates to suppliers, customers, and competitors based on curated supply chain database

**Propagation depth:** Up to 2 degrees of separation

**Example:**
```
Direct: AAPL news (+0.8 sentiment) → Foxconn (+0.56 via Tier 1 weight of 0.7)
Indirect: AAPL news → Foxconn → Foxconn's supplier (+0.11 via Tier 2 weight of 0.2)
```

**Tier weighting:**

| Tier | Relationship | Weight Range | Basis |
|------|-------------|--------------|-------|
| **Tier 1** | Direct relationship | 0.5 - 0.8 | Revenue concentration or confidence level |
| **Tier 2** | Indirect (2 degrees) | 0.2 | Attenuated signal strength |

**Relationship types:**

1. **Supplier relationships:**
   - Positive supplier news → Positive for supplier, Neutral/Negative for customers (depends on pricing power)
   - Negative supplier news → Negative for customers (supply risk)
   
2. **Customer relationships:**
   - Positive customer news → Positive for suppliers (demand signal)
   - Negative customer news → Negative for suppliers (demand risk)
   
3. **Competitor relationships:**
   - Positive competitor news → Negative for company (relative underperformance)
   - Negative competitor news → Positive for company (competitive advantage)

**Weight calculation example:**
```python
# AAPL has news with sentiment = +0.8
# Foxconn is AAPL supplier with Tier 1 weight = 0.7

foxconn_propagated_sentiment = 0.8 × 0.7 = +0.56

# Foxconn's supplier (Tier 2) gets:
tier2_propagated_sentiment = 0.56 × 0.2 = +0.11
```

**Database requirements:**
- Manual curation for top 50-100 stocks (LLM supplier accuracy only 32.7%)
- Validated relationships with confidence scores
- Source: 10-K filings, Bloomberg, Reuters, company websites

**Configuration:**
```python
enable_propagation = True  # Toggle in NewsAnalyzer
max_propagation_depth = 2   # Maximum degrees of separation
min_propagation_weight = 0.1  # Minimum threshold to propagate
```

**Limitations:**
- Requires supply chain database coverage
- Propagation strength decreases with distance
- May amplify noise if relationships are incorrect
- Works best for well-documented supply chains (semiconductors, automotive)

---

## 3. Regime Overlay (3-State Logic)

**Purpose:** Adapt strategy behavior to market conditions.

**Current implementation (PLACEHOLDER):**

**Primary method:** Gaussian HMM (Hidden Markov Model)
- 3-state classification
- Trained on SPY returns
- State mapping by mean return:
  - Highest mean → BULL
  - Lowest mean → BEAR
  - Middle mean → SIDEWAYS

**Fallback method:** SPY vs 200-day SMA
- SPY > 200-SMA → bullish regime
- SPY < 200-SMA → bearish regime
- Used when HMM fails or insufficient data

**State-dependent behavior:**

| Regime | Category Weights | Position Sizing | Kill-Switch |
|--------|------------------|-----------------|-------------|
| **BULL** | BULL_WEIGHTS | Standard | None |
| **BEAR** | DEFENSIVE_WEIGHTS | Reduced | CASH_OUT if SPY < 200-SMA |
| **SIDEWAYS** | SIDEWAYS_WEIGHTS | Position × 0.5 | None |

**Dual-confirmation rule:** CASH_OUT triggered only when:
- Regime = BEAR (from HMM), AND
- SPY < 200-SMA (trend confirmation)

**Future state:**
- Dedicated regime engine module
- Replace binary SMA rule with regime confidence scoring
- Multi-asset regime detection
- Macro indicator integration (deferred, see DECISIONS.md)

---

## 4. Weight Engine Modes

**Available modes:**

| Mode | Engine | Description | Status |
|------|--------|-------------|--------|
| `fixed` | Config | Static weights from YAML | Temporary baseline |
| `regime` | hmmlearn | HMM-based adaptive weights | Placeholder implementation |
| `rolling` | PyPortfolioOpt | Optimizer-based weights | Placeholder bounds |
| `ml` | Scikit-Learn | Feature-importance weights | Placeholder model |

**Rolling weight bounds (PLACEHOLDER):** 10%–50% per category

**Configuration:** Via `.env` or config file

**Future state:**
- Risk-budgeting allocator
- Cross-asset covariance tracking
- Regime-aware optimizer
- Dynamic bound adjustment

---

## 5. Portfolio Construction — Two Alternative Methods

### 5.1 Method A: Weighted Signal Combination (Default)

**Approach:** Combine signals using fixed or dynamic weights, rank stocks by composite score

**Process:**
1. Calculate Master Score (technical)
2. Calculate News Composite (with optional propagation)
3. Blend: `Final_Score = (1 - α) × Master + α × News` where α = news_weight
4. Rank all stocks by Final_Score (descending)
5. Select top N stocks
6. Apply inverse-volatility sizing

**Strengths:**
- Simple, interpretable
- No training data required
- Transparent weighting

**Weaknesses:**
- Assumes fixed relationships
- Cannot capture non-linearities
- Weights may not be optimal

---

### 5.2 Method B: ML Regression Prediction (Alternative)

**Approach:** Train ML model to predict forward returns, rank stocks by predicted return

**Process:**
1. **Training phase:**
   - Extract features: momentum, volume, RSI, supply_chain_score, sentiment_score
   - Calculate targets: forward 1-week return (T to T+7 days)
   - Train model on historical data (before backtest period)
   - Validate on 20% holdout set
   
2. **Prediction phase (during backtest):**
   - Extract same 5 features for current date
   - Predict forward return for each ticker
   - Rank by predicted return (higher = better)
   - Select top N stocks
   - Apply inverse-volatility sizing

**Available models** (via `config/model_config.yaml`):

| Model | Type | Strengths | When to use |
|-------|------|-----------|-------------|
| `linear` | Linear regression | Simple, interpretable, fast | Baseline |
| `ridge` | Ridge regression (L2) | Handles correlated features | Features are correlated |
| `lasso` | Lasso regression (L1) | Automatic feature selection | Unsure which features matter |
| `xgboost` | Gradient boosting | Non-linear relationships | After linear models plateau |

**Configuration:**
```yaml
# config/model_config.yaml
use_ml: true  # Enable ML mode
active_model: 'linear'  # Model to use

training:
  train_start: '2022-09-01'  # Must be before backtest period
  train_end: '2022-10-31'
  validation_split: 0.2
```

**Switching between methods:**
```yaml
# Use weighted signals (Method A)
use_ml: false

# Use ML predictions (Method B)
use_ml: true
active_model: 'xgboost'
```

**Model validation:**
- Cross-validation via TimeSeriesSplit (train always before test)
- Validation R² logged to ensure model quality
- If validation R² < 0, system falls back to weighted signals

**Strengths:**
- Learns optimal feature weights from data
- Can capture non-linear relationships (XGBoost)
- Adapts to changing market conditions

**Weaknesses:**
- Requires training data
- May overfit if not validated properly
- Less interpretable than weighted signals
- Training period must not overlap with backtest

**A/B Testing:**
Both methods use the same:
- Input features (technical + news signals)
- Position sizing (inverse-volatility)
- Risk management (policy gates)
- Execution timing (next-day open)

Only difference: How stocks are ranked (weighted score vs ML-predicted return)

---

## 6. Position Sizing

**Current method:** Inverse-volatility weighting

**Formula:**
```
weight_i ∝ 1 / (ATR_norm_i + ε)
```

Where:
- ATR_norm from T−1 (Signal Day minus 1)
- Higher risk → smaller allocation
- Epsilon prevents division by zero

**Normalization:** Active positions sum to 100%

**Future state:**
- Risk contribution equalization
- Liquidity-aware sizing
- Portfolio-level volatility targeting
- Cross-sectional volatility adjustment

---

## 7. Execution Timing & Friction

**Current implementation:**

| Parameter | Value | Status |
|-----------|-------|--------|
| **Rebalance frequency** | Weekly (Mondays) | Fixed |
| **Execution timing** | Next-Day Open | No look-ahead |
| **Friction** | 15 bps per trade | PLACEHOLDER CONSTANT |

**Friction model:**
```
Current: Fixed 0.15% per trade
Future: Spread + Market Impact + Slippage
```

**Future state:**
- Dynamic friction model
- Spread estimation from market data
- Impact estimator based on order size vs volume
- Liquidity-adjusted slippage model
- Time-of-day execution optimization

**Critical requirement:** Friction must be computed via algorithm, not hard-coded.

---

## 8. Policy Gates

**Gate hierarchy (applied in order):**

### 8.1 Kill-Switch (Regime + Trend Filter)

**Trigger:** Regime = BEAR AND SPY < 200-SMA

**Action:** CASH_OUT (100% cash) or half position (50% reduction)

**Rationale:** Dual-confirmation prevents false signals from volatile bull markets

### 8.2 Sideways Scaling

**Trigger:** Regime = SIDEWAYS

**Action:** Multiply all position sizes by 0.5

**Rationale:** Reduce exposure during range-bound/choppy markets

### 8.3 Daily Risk Exit

**Trigger:** Single-day return ≤ threshold (e.g. −5%)

**Action:** Exit position immediately, no reallocation to other holdings

**Rationale:** Cut losses quickly without increasing concentration risk

### 8.4 Post-Run Memory Update

**Timing:** After all trades executed and settled

**Action:** Update performance ledger, regime history

**Rationale:** Prevent partial-run corruption

**Future state:**
- Drawdown-based exposure scaling
- Adaptive kill-switch confidence threshold
- Multi-factor gate combinations
- Time-decay on exit signals

---

## 9. Environment Configuration (Required Parameters)

The following parameters **must be externalized** via `.env` or config files:

### 9.1 News Integration
- `NEWS_WEIGHT` — Blending ratio (0.0 to 1.0)
- `NEWS_ERROR_MODE` — Action on error: 'halt' or 'skip'
- `ENABLE_PROPAGATION` — Enable sentiment propagation (true/false)
- `MAX_PROPAGATION_DEPTH` — Maximum degrees of separation (default: 2)

### 9.2 ML Model Selection
- `USE_ML` — Use ML regression instead of weighted signals (true/false)
- `ACTIVE_MODEL` — Model type: 'linear', 'ridge', 'lasso', 'xgboost'
- `TRAIN_START` — Training period start date
- `TRAIN_END` — Training period end date

### 9.3 Weighting System
- `WEIGHT_MODE` — 'fixed', 'regime', 'rolling', or 'ml'
- `ROLLING_WEIGHT_MIN` — Lower bound per category
- `ROLLING_WEIGHT_MAX` — Upper bound per category

### 9.4 Friction Modeling
- `FRICTION_MODEL_MODE` — 'fixed' or 'dynamic'
- `FIXED_FRICTION_BPS` — Basis points per trade (if fixed)

### 9.5 Regime Detection
- `REGIME_CONFIRMATION_MODE` — 'hmm', 'sma', or 'dual'
- `HMM_N_COMPONENTS` — Number of HMM states
- `SMA_PERIOD` — Days for moving average (e.g. 200)

### 9.6 Risk Management
- `DAILY_EXIT_THRESHOLD` — Maximum acceptable daily loss
- `KILL_SWITCH_MODE` — 'cash' or 'half'
- `SIDEWAYS_SCALE_FACTOR` — Reduction multiplier

**Critical principle:** No strategic constant may remain hard-coded in production code.

---

## 10. Invariants (Non-Negotiable Rules)

### 10.1 No Look-Ahead
- All computations use only T−1 or earlier data
- Execution at Next-Day Open prevents same-day information usage
- Indicator normalization uses past rolling windows only
- ML training period must not overlap with backtest period

### 10.2 No Silent Downgrade
- Missing news → error state → halt (no fallback to technical-only)
- Missing data → explicit error → terminate
- Invalid configuration → fail fast

### 10.3 No Implicit Defaults
- All parameters must be explicitly configured
- No hidden assumptions in code
- Configuration validates on load

### 10.4 All Declared Outputs Must Exist
- Signal scores for all selected tickers
- Portfolio weights that sum to 1.0
- Performance metrics for all periods
- Log files for all runs

### 10.5 Failure → Terminate
- Invalid data → stop immediately
- Missing dependencies → halt before execution
- Constraint violations → terminate with clear error
- No partial execution with degraded functionality

---

## 11. Future Enhancements (Roadmap)

### Phase 2: Dynamic Systems
- Replace fixed category weights with adaptive engine
- Implement dynamic friction model
- Add regime confidence scoring
- Deploy risk-budgeting allocator

### Phase 3: Advanced Features
- Multi-asset regime detection
- Liquidity-aware position sizing
- Adaptive news blending weights
- Cross-sectional volatility adjustment
- Expand supply chain database to 200+ stocks
- Add relationship strength scoring

### Phase 4: Optimization
- Portfolio-level volatility targeting
- Transaction cost optimization
- Execution timing optimization
- Fill quality monitoring
- ML ensemble models (combine multiple models)
- Deep learning alternatives (LSTM, GRU for time series)

---

## 12. Governance

**Change control:**
- Modifications to decision stack order require architecture review
- New policy gates require backtesting validation
- Parameter ranges must be documented with rationale
- All changes tracked in DECISIONS.md

**Testing requirements:**
- Unit tests for each decision layer
- Integration tests for full stack
- Backtest validation before production
- Parameter sensitivity analysis
- ML model validation (if using ML method)

---

This document is the canonical reference for strategic logic. All implementation must conform to these principles, with deviations explicitly documented and justified.
