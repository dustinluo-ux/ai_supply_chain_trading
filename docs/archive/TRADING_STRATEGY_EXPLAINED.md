# Complete Trading Strategy Explained

## Overview

This document explains the complete numerical trading strategy from raw data → signals → portfolio → returns, with concrete formulas and examples.

---

## A. Signal Generation

### A1. Momentum Calculation

**Formula:**
```
momentum = (close[-5] - close[-20]) / close[-20]
```

**Where:**
- `close[-5]`: Closing price 5 days ago (short-term)
- `close[-20]`: Closing price 20 days ago (long-term)
- `momentum_period = 20` (configurable in `config/signal_weights.yaml`)

**Range:** Typically `[-0.3, +0.3]` (can be larger for volatile stocks)

**Example:**
```
Stock: NVDA
Date: 2023-06-15 (Monday)

Price data (filtered to <= 2023-06-15):
  - 2023-06-14 (Friday): close = $420.50
  - 2023-06-09 (5 days ago): close = $415.00
  - 2023-05-22 (20 days ago): close = $380.00

momentum = (415.00 - 380.00) / 380.00 = 0.0921 (9.21% gain)
```

**Normalization (for signal combination):**
```python
# From signal_combiner.py
if abs(momentum) > 1e-6:
    momentum_scaled = momentum * 5  # Scale factor
    momentum_norm = (np.tanh(momentum_scaled) + 1.0) / 2.0  # Map to [0, 1]
else:
    momentum_norm = 0.5  # Neutral
```

**Example Normalization:**
```
momentum = 0.0921
momentum_scaled = 0.0921 * 5 = 0.4605
momentum_norm = (tanh(0.4605) + 1.0) / 2.0 = (0.43 + 1.0) / 2.0 = 0.715
```

**Why tanh?**
- Preserves sign (positive momentum → higher score)
- Creates more differentiation than sigmoid
- Maps to [0, 1] range for combination

### A2. Volume Spike Calculation

**Formula:**
```
volume_ratio = volume_latest / volume_mean_30d
```

**Where:**
- `volume_latest`: Volume on most recent trading day
- `volume_mean_30d`: Rolling 30-day average volume
- `volume_period = 30` (configurable)

**Range:** Typically `[0.5, 3.0]` (can be larger for news events)

**Example:**
```
Stock: NVDA
Date: 2023-06-15

Volume data:
  - 2023-06-14: volume = 45,000,000 shares
  - 30-day average (2023-05-15 to 2023-06-14): 30,000,000 shares

volume_ratio = 45,000,000 / 30,000,000 = 1.5 (50% above average)
```

**Normalization:**
```python
# From signal_combiner.py
if volume > 0 and volume != 1.0:
    # Log scale: log(volume) / log(3.0)
    # Maps: 0.5→0.0, 1.0→0.5, 3.0→1.0
    volume_norm = np.log(volume) / np.log(3.0)
    volume_norm = max(0.0, min(1.0, volume_norm))
elif volume == 1.0:
    volume_norm = 0.5  # Neutral
else:
    volume_norm = 0.5
```

**Example Normalization:**
```
volume_ratio = 1.5
volume_norm = log(1.5) / log(3.0) = 0.405 / 1.099 = 0.369
```

**Why log scale?**
- Volume ratios are often close to 1.0
- Log scale creates more differentiation
- Prevents extreme values from dominating

### A3. RSI Calculation

**Formula:**
```
RSI = 100 - (100 / (1 + RS))

Where:
  RS = average_gain / average_loss
  
  average_gain = mean of positive price changes over 14 days
  average_loss = mean of negative price changes over 14 days
```

**Where:**
- `rsi_period = 14` (configurable)

**Range:** `[0, 100]`

**Interpretation:**
- `RSI < 30`: Oversold (potential buy signal)
- `RSI > 70`: Overbought (potential sell signal)
- `30 ≤ RSI ≤ 70`: Neutral

**Example:**
```
Stock: NVDA
Date: 2023-06-15

Price changes (last 14 days):
  Gains: +2.5, +1.8, +3.2, +0.5, +1.1 (sum = 9.1)
  Losses: -1.2, -0.8, -0.3 (sum = 2.3)

average_gain = 9.1 / 14 = 0.65
average_loss = 2.3 / 14 = 0.164

RS = 0.65 / 0.164 = 3.96
RSI = 100 - (100 / (1 + 3.96)) = 100 - 20.16 = 79.84
```

**Normalization to [0, 1]:**
```python
# From technical_analyzer.py
rsi_score = ((rsi - 30) / 40).clip(0, 1)
```

**Example Normalization:**
```
RSI = 79.84
rsi_score = ((79.84 - 30) / 40).clip(0, 1) = (49.84 / 40) = 1.0 (clipped)
```

**Mapping:**
- `RSI = 30` → `rsi_score = 0.0`
- `RSI = 50` → `rsi_score = 0.5`
- `RSI = 70` → `rsi_score = 1.0`
- `RSI > 70` → `rsi_score = 1.0` (clipped)
- `RSI < 30` → `rsi_score = 0.0` (clipped)

### A4. News Scores

**Supply Chain Score:**
- Range: `[0.0, 1.0]`
- Source: Gemini AI analysis of news articles
- See `docs/NEWS_ANALYSIS_EXPLAINED.md` for details

**Sentiment Score:**
- Range: `[-1.0, +1.0]`
- Source: Gemini AI analysis of news articles
- Normalized to `[0.0, 1.0]` for combination:
  ```python
  if abs(sentiment) < 0.001:
      sentiment_norm = 0.0  # No news
  else:
      sentiment_norm = (sentiment + 1.0) / 2.0
  ```

**Example:**
```
sentiment = 0.8 (very positive)
sentiment_norm = (0.8 + 1.0) / 2.0 = 0.9
```

---

## B. Signal Combination

### B1. Exact Formula

**Combined Score:**
```python
combined_score = (
    supply_chain_score * w_supply_chain +
    sentiment_norm * w_sentiment +
    momentum_norm * w_momentum +
    volume_norm * w_volume
)
```

**Current Weights (from `config/signal_weights.yaml`):**
```yaml
signal_weights:
  supply_chain: 0.40
  sentiment: 0.30
  momentum: 0.20
  volume: 0.10
```

**Weight Normalization:**
If weights don't sum to 1.0, they are normalized:
```python
total_weight = w_supply_chain + w_sentiment + w_momentum + w_volume
w_supply_chain = w_supply_chain / total_weight
w_sentiment = w_sentiment / total_weight
w_momentum = w_momentum / total_weight
w_volume = w_volume / total_weight
```

### B2. Example Calculation

**Input Signals:**
```python
# Technical signals
momentum = 0.0921  # Raw momentum (9.21% gain)
momentum_norm = 0.715  # After tanh normalization

volume_ratio = 1.5
volume_norm = 0.369  # After log normalization

rsi = 79.84
rsi_score = 1.0  # After normalization

# News signals
supply_chain_score = 0.95  # From Gemini
sentiment = 0.8
sentiment_norm = 0.9  # After [-1,1] → [0,1] normalization
```

**Combined Score:**
```python
combined_score = (
    0.95 * 0.40 +  # supply_chain
    0.9 * 0.30 +   # sentiment
    0.715 * 0.20 + # momentum
    0.369 * 0.10   # volume
)
= 0.38 + 0.27 + 0.143 + 0.037
= 0.83
```

**Note:** RSI is not directly included in `combine_signals_direct()`. In technical-only mode, momentum and RSI are combined first:
```python
# Technical-only mode
combined_momentum = (momentum * 0.7 + rsi * 0.3) / 1.0
# Then combined_momentum is used in signal combination
```

### B3. Mode-Specific Weights

**Technical-Only Mode:**
```python
weights = {
    'supply_chain': 0.0,
    'sentiment': 0.0,
    'momentum': 0.5,
    'volume': 0.3,
    'rsi': 0.2
}
```

**News-Only Mode:**
```python
weights = {
    'supply_chain': 0.5,
    'sentiment': 0.5,
    'momentum': 0.0,
    'volume': 0.0,
    'rsi': 0.0
}
```

**Combined Mode:**
```python
weights = {
    'supply_chain': 0.40,
    'sentiment': 0.30,
    'momentum': 0.20,
    'volume': 0.10
}
```

---

## C. Portfolio Construction

### C1. Stock Selection

**Process:**
1. Calculate `combined_score` for all tickers in universe
2. Rank by score (highest first)
3. Select top N stocks

**Formula:**
```python
# Sort by combined_score descending
sorted_tickers = sorted(scores.items(), key=lambda x: x[1], reverse=True)
top_tickers = sorted_tickers[:TOP_N]  # TOP_N = 10 (default)
```

**Example:**
```
Universe: 50 stocks
TOP_N: 10

Scores:
  NVDA: 0.83
  AMD:  0.78
  QLYS: 0.72
  ...
  ABC:  0.45

Selected: Top 10 by score
```

### C2. Position Weighting

**Method: Proportional (default)**

**Formula:**
```python
# Extract scores for selected stocks
ticker_scores = {t: s for t, s in top_tickers}
total_score = sum(ticker_scores.values())

# Proportional weighting
weights_dict = {t: s / total_score for t, s in ticker_scores.items()}
```

**Example:**
```
Top 10 stocks with scores:
  NVDA: 0.83
  AMD:  0.78
  QLYS: 0.72
  SLAB: 0.68
  SYNA: 0.65
  ABC:  0.62
  DEF:  0.58
  GHI:  0.55
  JKL:  0.52
  MNO:  0.48

Total score = 6.41

Weights:
  NVDA: 0.83 / 6.41 = 0.129 (12.9%)
  AMD:  0.78 / 6.41 = 0.122 (12.2%)
  QLYS: 0.72 / 6.41 = 0.112 (11.2%)
  ...
  MNO: 0.48 / 6.41 = 0.075 (7.5%)
```

**Alternative: Equal Weighting**

If `weighting_method = "equal"`:
```python
equal_weight = 1.0 / len(top_tickers)
weights_dict = {t: equal_weight for t, _ in top_tickers}
```

**Example (Equal Weighting):**
```
Top 10 stocks → Each gets 10% (0.10) weight
```

**Current Setting:**
- `weighting_method: "proportional"` (from `config/signal_weights.yaml`)

---

## D. Trading Logic

### D1. Rebalancing Schedule

**Frequency:** Weekly (every Monday)

**Process:**
1. **Monday morning:** Calculate signals using data up to previous Friday
2. **Monday:** Execute trades (buy/sell to match new positions)
3. **Hold until:** Next Monday (7 days)

**Example Timeline:**
```
Week N:
  Monday 2023-06-15:
    ├─ Calculate signals (using data up to Friday 2023-06-14)
    ├─ Execute trades (buy/sell)
    └─ Hold positions

  Tuesday-Friday 2023-06-16-19:
    └─ Hold positions (no trading)

Week N+1:
  Monday 2023-06-22:
    ├─ Calculate new signals (using data up to Friday 2023-06-21)
    ├─ Rebalance (adjust positions)
    └─ Hold new positions
```

**Code Implementation:**
```python
# Generate signals for each Monday
mondays = pd.date_range('2023-02-01', '2023-12-31', freq='W-MON')

for monday in mondays:
    date_str = monday.strftime("%Y-%m-%d")
    
    # Calculate signals using data <= monday
    for ticker in tickers:
        # Filter price data to <= monday
        df_filtered = prices_dict[ticker][prices_dict[ticker].index <= monday]
        
        # Calculate signals
        signals = calculate_signals(df_filtered, date_str)
        
    # Select top N and assign weights
    top_tickers = select_top_n(signals, TOP_N)
    weights = calculate_weights(top_tickers)
    
    # Assign to signals DataFrame
    signals_df.loc[monday, ticker] = weight
```

### D2. Position Holding Period

**Duration:** 1 week (until next rebalance)

**Implementation:**
```python
# Forward-fill positions until next Monday
for monday in mondays:
    next_monday = mondays[mondays > monday]
    end_date = next_monday[0] if len(next_monday) > 0 else prices_df.index[-1]
    
    # Set positions from monday to end_date
    positions_df.loc[monday:end_date, ticker] = weight
```

**Example:**
```
Monday 2023-06-15: Set NVDA weight = 0.129
  → Positions hold from 2023-06-15 to 2023-06-21 (inclusive)

Monday 2023-06-22: Recalculate, new NVDA weight = 0.115
  → Positions hold from 2023-06-22 to 2023-06-28 (inclusive)
```

### D3. Stop-Losses and Position Limits

**Current Implementation:**
- **No stop-losses:** Positions are held until next rebalance
- **No position limits:** Weights can be any value (sum to 1.0)
- **No leverage:** Total portfolio weight = 1.0 (100% invested)

**Future Enhancements:**
- Stop-loss: Exit position if drawdown exceeds threshold
- Position limits: Max weight per stock (e.g., 20%)
- Cash buffer: Keep X% in cash

### D4. Transaction Costs

**Current Implementation:**
```python
# Apply 0.1% transaction cost on rebalancing days
rebalance_dates = positions_df.diff().abs().sum(axis=1) > 0.01
portfolio_returns[rebalance_dates] -= 0.001  # 0.1% = 10 bps
```

**Formula:**
```
portfolio_return[t] = portfolio_return[t] - 0.001  # If rebalancing
```

**Example:**
```
Monday 2023-06-15: Rebalance
  Portfolio return = 0.5% (0.005)
  After transaction cost = 0.5% - 0.1% = 0.4% (0.004)

Tuesday 2023-06-16: No rebalance
  Portfolio return = 0.3% (0.003)
  No transaction cost applied
```

**Assumptions:**
- 0.1% (10 basis points) per rebalance
- Applied only on days when positions change
- No bid-ask spread modeling
- No slippage modeling

---

## E. Time Alignment

### E1. Critical: Avoiding Lookahead Bias

**Rule:** All calculations use only data available **on or before** the signal date.

**Price Data:**
```python
# Filter to data available on Monday
date_dt = pd.to_datetime(date_str)  # Monday 2023-06-15
df_filtered = prices_dict[ticker][prices_dict[ticker].index <= date_dt]
# Uses data up to Friday 2023-06-14 (last trading day before Monday)
```

**News Data:**
```python
# Lookback window ending on signal date
lookback_start = (monday - timedelta(days=7)).strftime("%Y-%m-%d")  # 2023-06-08
date_str = monday.strftime("%Y-%m-%d")  # 2023-06-15

# Load articles from lookback_start to date_str (inclusive)
news_signals = news_analyzer.analyze_news_for_ticker(
    ticker,
    lookback_start,  # 2023-06-08
    date_str         # 2023-06-15
)
```

**Trading:**
```python
# Positions are set on Monday (same day as signal calculation)
# But returns are calculated using NEXT day's prices
portfolio_returns = (positions_df.shift(1) * returns).sum(axis=1)
```

**Why `shift(1)`?**
- Positions set on Monday
- Returns calculated from Tuesday's price change
- Avoids using Monday's closing price (which we "saw" when calculating signals)

### E2. Example Timeline

```
Monday 2023-06-15 (Week N):
  ├─ 9:00 AM: Calculate signals
  │   ├─ Price data: Up to Friday 2023-06-14 (inclusive)
  │   ├─ News data: 2023-06-08 to 2023-06-15 (7-day lookback)
  │   └─ Combined score: 0.83
  │
  ├─ 9:30 AM: Market opens
  │   └─ Execute trades (buy/sell to match target weights)
  │
  └─ 4:00 PM: Market closes
      └─ Hold positions

Tuesday 2023-06-16:
  ├─ Calculate portfolio return:
  │   └─ (Monday's positions) * (Tuesday's price change)
  │
  └─ Hold positions (no trading)

Wednesday-Sunday 2023-06-17-21:
  └─ Hold positions (no trading)

Monday 2023-06-22 (Week N+1):
  ├─ 9:00 AM: Recalculate signals
  │   ├─ Price data: Up to Friday 2023-06-21 (inclusive)
  │   └─ New combined score: 0.79
  │
  └─ 9:30 AM: Rebalance (adjust positions)
```

### E3. Verification

**Check for lookahead bias:**
```python
# In simple_backtest_v2.py
date_dt = pd.to_datetime(date_str)
df_filtered = ticker_df[ticker_df.index <= date_dt]  # ✅ Correct: <= date_dt

# Verify no future data
assert df_filtered.index.max() <= date_dt, "Lookahead bias detected!"
```

---

## F. Return Calculation

### F1. Portfolio Returns

**Formula:**
```python
# Daily returns for each stock
returns = prices_df.pct_change()

# Portfolio return = weighted sum of stock returns
portfolio_returns = (positions_df.shift(1) * returns).sum(axis=1).fillna(0)
```

**Step-by-Step:**
1. **Stock returns:** `returns[ticker][date] = (price[date] - price[date-1]) / price[date-1]`
2. **Shift positions:** `positions_df.shift(1)` (use previous day's positions)
3. **Weighted sum:** `(positions * returns).sum(axis=1)`

**Example:**
```
Monday 2023-06-15:
  Positions: NVDA=0.129, AMD=0.122, QLYS=0.112, ...

Tuesday 2023-06-16:
  Returns:
    NVDA: +2.5% (0.025)
    AMD:  +1.8% (0.018)
    QLYS: -0.5% (-0.005)
    ...

  Portfolio return = 
    0.129 * 0.025 +  # NVDA
    0.122 * 0.018 +  # AMD
    0.112 * (-0.005) +  # QLYS
    ...
  = 0.003225 + 0.002196 - 0.00056 + ...
  = 0.012 (1.2%)
```

### F2. Cumulative Returns

**Formula:**
```python
cumulative = (1 + portfolio_returns).cumprod()
```

**Example:**
```
Day 1: portfolio_return = 0.01 (1%)
  cumulative = 1.0 * (1 + 0.01) = 1.01

Day 2: portfolio_return = 0.02 (2%)
  cumulative = 1.01 * (1 + 0.02) = 1.0302

Day 3: portfolio_return = -0.01 (-1%)
  cumulative = 1.0302 * (1 - 0.01) = 1.0199
```

**Total Return:**
```python
total_return = cumulative.iloc[-1] - 1
```

**Example:**
```
Final cumulative = 1.25
Total return = 1.25 - 1 = 0.25 (25%)
```

### F3. Sharpe Ratio

**Formula:**
```python
sharpe = (portfolio_returns.mean() * 252) / (portfolio_returns.std() * np.sqrt(252))
```

**Where:**
- `252`: Trading days per year
- Annualized mean: `portfolio_returns.mean() * 252`
- Annualized std: `portfolio_returns.std() * np.sqrt(252)`

**Example:**
```
Daily returns (sample):
  Mean: 0.001 (0.1% per day)
  Std: 0.015 (1.5% per day)

Annualized:
  Mean: 0.001 * 252 = 0.252 (25.2% per year)
  Std: 0.015 * sqrt(252) = 0.238 (23.8% per year)

Sharpe = 0.252 / 0.238 = 1.06
```

**Interpretation:**
- `Sharpe > 1.0`: Good risk-adjusted return
- `Sharpe > 2.0`: Excellent risk-adjusted return
- `Sharpe < 0.5`: Poor risk-adjusted return

### F4. Maximum Drawdown

**Formula:**
```python
# Running maximum
running_max = cumulative.expanding().max()

# Drawdown
drawdown = (cumulative - running_max) / running_max

# Maximum drawdown (most negative)
max_dd = drawdown.min()
```

**Example:**
```
Day 1: cumulative = 1.00, running_max = 1.00, drawdown = 0.00
Day 2: cumulative = 1.05, running_max = 1.05, drawdown = 0.00
Day 3: cumulative = 1.10, running_max = 1.10, drawdown = 0.00
Day 4: cumulative = 1.08, running_max = 1.10, drawdown = -0.018 (-1.8%)
Day 5: cumulative = 1.02, running_max = 1.10, drawdown = -0.073 (-7.3%)
Day 6: cumulative = 1.06, running_max = 1.10, drawdown = -0.036 (-3.6%)

Max drawdown = -0.073 (-7.3%)
```

---

## G. Current Weights and Rationale

### G1. Current Configuration

**From `config/signal_weights.yaml`:**
```yaml
signal_weights:
  supply_chain: 0.40  # 40%
  sentiment: 0.30     # 30%
  momentum: 0.20       # 20%
  volume: 0.10        # 10%
```

**Total:** 1.00 (100%)

### G2. Why These Weights?

**Rationale (likely):**
1. **Supply chain (40%):** Highest weight because it's the core theme (AI supply chain stocks)
2. **Sentiment (30%):** Second highest because news sentiment is a strong predictor
3. **Momentum (20%):** Technical momentum is important but secondary to news
4. **Volume (10%):** Lowest weight because volume is more of a confirmation signal

**Note:** These weights appear to be **arbitrary** (not optimized). They can be:
- Changed manually in `config/signal_weights.yaml`
- Optimized using backtesting (grid search, genetic algorithms, etc.)
- Learned using machine learning (reinforcement learning, etc.)

### G3. What Happens if We Change Them?

**Example 1: Increase Momentum Weight**
```yaml
signal_weights:
  supply_chain: 0.30  # Reduced from 0.40
  sentiment: 0.30     # Same
  momentum: 0.30      # Increased from 0.20
  volume: 0.10        # Same
```

**Expected Impact:**
- More weight on technical signals
- Less weight on news signals
- May perform better in trending markets
- May perform worse when news is predictive

**Example 2: Equal Weights**
```yaml
signal_weights:
  supply_chain: 0.25
  sentiment: 0.25
  momentum: 0.25
  volume: 0.25
```

**Expected Impact:**
- Balanced approach
- No single signal dominates
- May reduce volatility
- May reduce returns (dilutes strongest signals)

**Example 3: News-Only**
```yaml
signal_weights:
  supply_chain: 0.50
  sentiment: 0.50
  momentum: 0.00
  volume: 0.00
```

**Expected Impact:**
- Ignores technical signals
- Pure news-driven strategy
- May miss technical trends
- May be more volatile (news can be noisy)

### G4. Optimization Approach

**Grid Search:**
```python
# Test different weight combinations
for w_supply in [0.3, 0.4, 0.5]:
    for w_sentiment in [0.2, 0.3, 0.4]:
        for w_momentum in [0.1, 0.2, 0.3]:
            w_volume = 1.0 - w_supply - w_sentiment - w_momentum
            if w_volume >= 0:
                weights = {
                    'supply_chain': w_supply,
                    'sentiment': w_sentiment,
                    'momentum': w_momentum,
                    'volume': w_volume
                }
                # Run backtest
                sharpe = run_backtest(weights)
                # Track best weights
```

**Genetic Algorithm:**
- Evolve weight combinations
- Select best performers
- Mutate and crossover
- Iterate until convergence

**Reinforcement Learning:**
- Learn optimal weights from market feedback
- Adapt weights over time
- Consider market regime (bull/bear/sideways)

---

## Summary

1. **Signals:**
   - Momentum: `(close[-5] - close[-20]) / close[-20]` → normalized with tanh
   - Volume: `volume_latest / volume_mean_30d` → normalized with log
   - RSI: `100 - (100 / (1 + RS))` → normalized to [0, 1]
   - News: Supply chain [0, 1], Sentiment [-1, 1] → normalized to [0, 1]

2. **Combination:**
   - Weighted average: `sum(signal_norm * weight)`
   - Current weights: supply_chain=0.40, sentiment=0.30, momentum=0.20, volume=0.10

3. **Portfolio:**
   - Select top N stocks by combined score
   - Weight positions proportionally to scores (or equally)
   - Rebalance weekly (every Monday)

4. **Trading:**
   - Hold positions for 1 week
   - Transaction cost: 0.1% per rebalance
   - No stop-losses or position limits

5. **Returns:**
   - Portfolio return = weighted sum of stock returns
   - Cumulative = compound returns
   - Sharpe = annualized return / annualized volatility
   - Max drawdown = largest peak-to-trough decline

6. **Time Alignment:**
   - No lookahead bias: All calculations use data ≤ signal date
   - Positions set on Monday, returns calculated from Tuesday
   - News lookback: 7 days ending on signal date
