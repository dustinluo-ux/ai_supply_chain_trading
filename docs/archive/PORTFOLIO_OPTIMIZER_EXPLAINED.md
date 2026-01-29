# Portfolio Optimizer - What It Does

**Date:** 2026-01-25  
**Purpose:** Explain what the Portfolio Optimizer is and how it differs from current approach

---

## WHAT IS PORTFOLIO OPTIMIZER?

**Short Answer:** It's NOT about picking the best model. It's about converting signals into optimal portfolio weights with risk management.

---

## CURRENT APPROACH (test_signals.py)

**What you do now:**

1. **Calculate signals** for each stock (supply chain, sentiment, momentum, etc.)
2. **Rank stocks** by combined signal score
3. **Select top N** stocks (e.g., top 10)
4. **Assign weights:**
   - Proportional: `weight = score / sum(all_scores)`
   - Equal: `weight = 1/N` for all selected stocks
5. **Done** - simple and works!

**Example:**
```
Stock  Signal Score  Weight
AAPL   0.85         0.35 (35%)
NVDA   0.72         0.30 (30%)
MSFT   0.68         0.28 (28%)
TSLA   0.15         0.07 (7%)
```

---

## PORTFOLIO OPTIMIZER APPROACH

**What it does differently:**

### 1. Risk-Scaled Weighting (Not Just Signal Scores)

**Current:** Weight = signal score / sum(scores)

**Optimizer:** Weight = (signal_score / volatility) / sum(all)

**Why:** A stock with high signal but high volatility gets less weight. A stock with medium signal but low volatility gets more weight.

**Example:**
```
Stock  Signal  Volatility  Risk-Scaled Weight
AAPL   0.85    0.25        0.40 (higher - low vol)
NVDA   0.90    0.45        0.20 (lower - high vol)
```

---

### 2. Model Blending (Multiple Signal Sources)

**Current:** You have ONE signal source (your combined signals)

**Optimizer:** Can blend MULTIPLE models/signal sources:
- Model A: Supply chain signals
- Model B: Technical signals  
- Model C: ML predictions
- **Blend them** with weights based on performance

**Example:**
```
Model A (supply chain): 40% weight
Model B (technical):    30% weight
Model C (ML):           30% weight
→ Final weights = weighted average
```

**Note:** This is useful if you have multiple independent signal sources, but you might not need it if you're already combining signals.

---

### 3. Portfolio-Level Constraints

**Current:** No constraints (just top N with weights)

**Optimizer:** Applies constraints:
- **Single position cap:** Max 15% per stock
- **Net exposure:** Total long - short must be between -20% and +50%
- **Gross exposure:** Total |long| + |short| must be < 200%
- **Volatility target:** Portfolio volatility must be ≤ 10% annualized

**Example:**
```
Without constraints:
  AAPL: 40% weight (too high!)
  NVDA: 35% weight (too high!)

With constraints:
  AAPL: 15% weight (capped)
  NVDA: 15% weight (capped)
  MSFT: 12% weight
  ... (redistributed)
```

---

### 4. Risk Targeting (Volatility Control)

**Current:** No volatility control

**Optimizer:** Uses covariance matrix to calculate portfolio risk:
- Calculates: `portfolio_variance = weights' × covariance_matrix × weights`
- If portfolio volatility > target (e.g., 10%), scales down all weights
- Ensures portfolio risk stays within limits

**Example:**
```
Target volatility: 10% annualized
Calculated volatility: 15% (too high!)
→ Scale all weights by 10%/15% = 0.67
→ Final portfolio volatility: 10% ✅
```

---

### 5. Cost-Aware Optimization

**Current:** Simple transaction costs (10 bps per rebalance)

**Optimizer:** More sophisticated cost calculation:
- Commission per share
- Spread costs (bid-ask)
- Market impact (large orders move price)
- **No-trade bands:** Don't trade if costs > benefit

**Example:**
```
Want to buy $1000 of AAPL
Commission: $3
Spread: $2
Total cost: $5
Expected benefit: $4
→ Don't trade (costs > benefit)
```

---

## COMPARISON TABLE

| Feature | Current Approach | Portfolio Optimizer |
|---------|------------------|-------------------|
| **Signal → Weight** | Direct (score/sum) | Risk-scaled (score/vol) |
| **Multiple Models** | ❌ No | ✅ Yes (blending) |
| **Position Limits** | ❌ No | ✅ Yes (15% cap) |
| **Volatility Control** | ❌ No | ✅ Yes (target 10%) |
| **Net/Gross Limits** | ❌ No | ✅ Yes |
| **Cost Optimization** | ⚠️ Basic | ✅ Advanced |
| **Covariance Matrix** | ❌ No | ✅ Yes (risk calc) |

---

## DO YOU NEED IT?

### ✅ **YES, if you need:**

1. **Risk management:**
   - Position size limits (max 15% per stock)
   - Volatility targeting (keep portfolio risk at 10%)
   - Net/gross exposure limits

2. **Multiple signal sources:**
   - You have separate models (supply chain model, technical model, ML model)
   - You want to blend them intelligently

3. **Sophisticated cost management:**
   - Large positions that might move prices
   - Need to avoid trades where costs > benefit

### ❌ **NO, if:**

1. **Current approach works:**
   - Simple proportional/equal weighting is sufficient
   - You don't need position limits
   - You don't need volatility targeting

2. **Single signal source:**
   - You're already combining signals (supply chain + sentiment + technical)
   - You don't have separate models to blend

3. **Small positions:**
   - Positions are small enough that costs/impact don't matter
   - No need for sophisticated cost optimization

---

## SIMPLIFIED VERSION

If you want some features but not all, you could create a **simplified optimizer** that:
- ✅ Applies position size limits (max 15% per stock)
- ✅ Risk-scales weights (weight = score / volatility)
- ❌ Skips model blending (you have one signal source)
- ❌ Skips covariance matrix (simpler risk calculation)

**This would be much simpler** than the full optimizer and might be sufficient.

---

## RECOMMENDATION

**For your current system:**

1. **You probably DON'T need the full Portfolio Optimizer** because:
   - You already combine signals (supply chain + sentiment + technical)
   - Simple proportional weighting works
   - You don't have multiple independent models to blend

2. **You MIGHT want simplified features:**
   - Position size limits (max 15% per stock) - **Easy to add**
   - Risk-scaled weighting (weight = score / volatility) - **Easy to add**
   - Volatility targeting - **Medium complexity**

3. **You DON'T need:**
   - Model blending (you have one signal source)
   - Complex covariance matrix calculations
   - Advanced cost optimization (unless trading large sizes)

---

## SUMMARY

**Portfolio Optimizer is NOT about:**
- ❌ Picking the best model
- ❌ Model selection

**Portfolio Optimizer IS about:**
- ✅ Converting signals to optimal weights
- ✅ Risk management (position limits, volatility control)
- ✅ Blending multiple models (if you have them)
- ✅ Cost-aware optimization

**For your use case:** You probably don't need the full optimizer, but you might want simplified position limits and risk-scaled weighting.

---

**See `docs/NOT_PORTED_COMPONENTS.md` for more details on what it does and why it wasn't ported.**
