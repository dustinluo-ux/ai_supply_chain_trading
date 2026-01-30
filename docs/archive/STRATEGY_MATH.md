# Strategy Mathematics

**Last Updated:** 2026-01-25

---

## Signal Generation

### Momentum

**Formula:**
```
momentum = (close[-5] - close[-20]) / close[-20]
```

**Normalization:**
```python
momentum_scaled = momentum * 5
momentum_norm = (tanh(momentum_scaled) + 1.0) / 2.0  # [0, 1]
```

**Default:** `momentum_period = 20` (configurable)

---

### Volume Ratio

**Formula:**
```
volume_ratio = volume_latest / volume_mean_30d
```

**Normalization:**
```python
volume_norm = log(volume_ratio) / log(3.0)  # Maps 0.5→0.0, 1.0→0.5, 3.0→1.0
volume_norm = clip(volume_norm, 0.0, 1.0)
```

**Default:** `volume_period = 30` (configurable)

---

### RSI

**Formula:**
```
RSI = 100 - (100 / (1 + RS))
RS = average_gain / average_loss
```

**Normalization:**
```python
rsi_score = ((rsi - 30) / 40).clip(0, 1)  # Maps 30→0.0, 50→0.5, 70→1.0
```

**Default:** `rsi_period = 14` (configurable)

---

### News Scores

**Supply Chain Score:** `[0.0, 1.0]` from Gemini analysis

**Sentiment Score:** `[-1.0, +1.0]` from Gemini analysis

**Normalization:**
```python
sentiment_norm = (sentiment + 1.0) / 2.0  # Maps [-1, +1] → [0, 1]
```

---

## Signal Combination

### Weighted Combination

**Formula:**
```python
combined_score = (
    supply_chain_score * w_supply_chain +
    sentiment_norm * w_sentiment +
    momentum_norm * w_momentum +
    volume_norm * w_volume
)
```

**Default Weights:**
- `supply_chain: 0.40`
- `sentiment: 0.30`
- `momentum: 0.20`
- `volume: 0.10`

**Weight Normalization:**
If weights don't sum to 1.0, they are normalized:
```python
total = sum(weights.values())
weights = {k: v / total for k, v in weights.items()}
```

---

### ML Model (Optional)

If `config/model_config.yaml` has `use_ml: true`:
- Trains model on historical signals → returns
- Predicts forward return from current signals
- Falls back to weighted combination if ML fails

---

## Portfolio Construction

### Stock Selection

1. Calculate `combined_score` for all tickers
2. Rank by score (highest first)
3. Select top N stocks (`--top-n` parameter, default: 10)

---

### Position Weighting

**Proportional (default):**
```python
total_score = sum(scores.values())
weight = score / total_score
```

**Equal:**
```python
weight = 1.0 / N  # N = number of selected stocks
```

**No position limits:** Single stock can get 100% weight

---

## Trading Logic

### Rebalancing Schedule

- **Frequency:** Weekly (every Monday)
- **Signal calculation:** Uses data up to previous Friday
- **Trading:** Monday (same day as signal calculation)
- **Hold period:** Until next Monday (7 days)

### Position Holding

```python
# Positions set on Monday
# Hold until next Monday
for monday in mondays:
    next_monday = mondays[mondays > monday]
    end_date = next_monday[0] if len(next_monday) > 0 else prices_df.index[-1]
    positions_df.loc[monday:end_date, ticker] = weight
```

---

## Return Calculation

### Portfolio Returns

```python
returns = prices_df.pct_change()
portfolio_returns = (positions_df.shift(1) * returns).sum(axis=1).fillna(0)
```

**Why `shift(1)`?**
- Positions set on Monday
- Returns calculated from Tuesday's price change
- Avoids lookahead bias

### Transaction Costs

```python
rebalance_dates = positions_df.diff().abs().sum(axis=1) > 0.01
portfolio_returns[rebalance_dates] -= 0.001  # 10 bps
```

---

## Performance Metrics

### Sharpe Ratio

```python
sharpe = (portfolio_returns.mean() * 252) / (portfolio_returns.std() * sqrt(252))
```

**Interpretation:**
- `> 1.0`: Good risk-adjusted return
- `> 2.0`: Excellent
- `< 0.5`: Poor

### Total Return

```python
cumulative = (1 + portfolio_returns).cumprod()
total_return = cumulative.iloc[-1] - 1
```

### Maximum Drawdown

```python
running_max = cumulative.expanding().max()
drawdown = (cumulative - running_max) / running_max
max_dd = drawdown.min()
```

---

## Time Alignment (Critical)

### No Lookahead Bias

**Rule:** All calculations use only data available **on or before** the signal date.

**Price Data:**
```python
date_dt = pd.to_datetime(date_str)  # Monday
df_filtered = prices_df[prices_df.index <= date_dt]  # Up to Friday
```

**News Data:**
```python
lookback_start = (monday - timedelta(days=7)).strftime("%Y-%m-%d")
date_str = monday.strftime("%Y-%m-%d")
# Load articles from lookback_start to date_str (inclusive)
```

**Trading:**
```python
# Positions set on Monday
# Returns calculated from Tuesday (shift(1))
portfolio_returns = (positions_df.shift(1) * returns).sum(axis=1)
```

---

## Mode-Specific Weights

### Technical-Only Mode

```python
weights = {
    'supply_chain': 0.0,
    'sentiment': 0.0,
    'momentum': 0.5,
    'volume': 0.3,
    'rsi': 0.2
}
```

### News-Only Mode

```python
weights = {
    'supply_chain': 0.5,
    'sentiment': 0.5,
    'momentum': 0.0,
    'volume': 0.0,
    'rsi': 0.0
}
```

### Combined Mode

```python
weights = {
    'supply_chain': 0.40,
    'sentiment': 0.30,
    'momentum': 0.20,
    'volume': 0.10
}
```

---

## Supply Chain Scoring

**Formula (when relationships exist):**
```python
score = (
    ai_score * 0.4 +           # AI relevance (40%)
    mention_score * 0.3 +       # Supplier/customer mentions (30%)
    relevance_weight * 0.2 +     # Relevance score (20%)
    sentiment_ratio * 0.1        # Sentiment ratio (10%)
)
```

**Formula (when NO relationships):**
```python
score = (
    ai_score * 0.2 +            # Reduced AI weight (20%)
    mention_score * 0.0 +       # No relationships = 0
    relevance_weight * 0.2 +     # Relevance (20%)
    sentiment_ratio * 0.1        # Sentiment (10%)
)
score = min(score, 0.5)  # Cap at 0.5
```

**Components:**
- `ai_score = min(ai_related_count / 10.0, 1.0)`
- `mention_score = (supplier_mentions * 0.4 + customer_mentions * 0.3 + product_mentions * 0.3) / total_articles`
- `relevance_weight = avg_relevance_score`
- `sentiment_ratio = positive_count / total_sentiment_count`

---

## Example Calculation

**Input:**
- `supply_chain_score: 0.95`
- `sentiment: 0.8` → `sentiment_norm: 0.9`
- `momentum: 0.0921` → `momentum_norm: 0.715`
- `volume_ratio: 1.5` → `volume_norm: 0.369`

**Combined Score:**
```python
combined = (
    0.95 * 0.40 +  # supply_chain
    0.9 * 0.30 +   # sentiment
    0.715 * 0.20 + # momentum
    0.369 * 0.10   # volume
) = 0.83
```

**Portfolio Weight (proportional, top 10):**
```python
# If total of top 10 scores = 6.41
weight = 0.83 / 6.41 = 0.129 (12.9%)
```

---

See `docs/SYSTEM_SPEC.md` for system overview and `docs/DATA.md` for data sources.
