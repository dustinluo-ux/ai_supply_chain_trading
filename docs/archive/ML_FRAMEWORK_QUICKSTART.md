# ML Regression Framework - Quick Start Guide

## Overview

The trading system now supports **machine learning-based return prediction** as an alternative to weighted signal combination. You can switch between ML models and weighted signals with **zero code changes** - just edit the config file.

---

## Quick Start

### 1. Enable ML Model

Edit `config/model_config.yaml`:

```yaml
# Enable ML model
use_ml: true  # Change from false to true

# Choose your model
active_model: 'linear'  # Options: linear, ridge, lasso, xgboost
```

### 2. Run Backtest

```bash
python test_signals.py
```

The system will:
1. Train the model on historical data (training period from config)
2. Use model predictions to rank stocks (instead of weighted signals)
3. Select top N stocks based on predicted returns

### 3. Switch Models

To try a different model, just change one line:

```yaml
active_model: 'xgboost'  # Was 'linear'
```

No code changes needed!

---

## How It Works

### Training Phase (Automatic)

1. **Feature Extraction**: For each stock/date in training period:
   - Technical: momentum, volume ratio, RSI
   - News: supply chain score, sentiment score

2. **Target Calculation**: Forward 1-week return (actual return from date to date+7 days)

3. **Model Training**: Train selected model (Linear, Ridge, Lasso, XGBoost)

4. **Validation**: Evaluate on validation set (20% of training data)

### Prediction Phase (During Backtest)

1. **Feature Extraction**: Extract same features for current date
2. **Prediction**: Model predicts forward return
3. **Ranking**: Stocks ranked by predicted return (higher = better)
4. **Selection**: Top N stocks selected for portfolio

---

## Configuration

### Model Selection

```yaml
active_model: 'linear'  # Current model
```

Available models:
- `linear` - Linear regression (baseline)
- `ridge` - Ridge regression (L2 regularization)
- `lasso` - Lasso regression (L1 regularization, feature selection)
- `xgboost` - XGBoost gradient boosting (non-linear)

### Model Hyperparameters

```yaml
models:
  ridge:
    alpha: 1.0  # Regularization strength
    
  lasso:
    alpha: 0.1  # Higher = more feature selection
    
  xgboost:
    n_estimators: 100
    max_depth: 3
    learning_rate: 0.1
```

### Training Period

```yaml
training:
  train_start: '2022-09-01'  # Training period start
  train_end: '2022-10-31'     # Training period end
  validation_split: 0.2       # 20% for validation
```

**Important**: Training period must be **before** backtest period!

---

## Comparison: ML vs Weighted Signals

### Weighted Signals (use_ml: false)
- **Method**: Fixed weights (e.g., 40% supply chain, 30% sentiment, 20% momentum, 10% volume)
- **Pros**: Simple, interpretable, no training needed
- **Cons**: Assumes fixed relationships, doesn't learn from data

### ML Model (use_ml: true)
- **Method**: Learns optimal feature weights from historical data
- **Pros**: Adapts to data, can capture non-linear relationships (XGBoost)
- **Cons**: Requires training data, may overfit

---

## Feature Importance

After training, view which features matter most:

**Console Output:**
```
[Feature Importance]
  news_supply_chain      :  0.4523
  momentum_20d          :  0.3121
  news_sentiment        :  0.1987
  volume_ratio_30d      :  0.0234
  rsi_14d               :  0.0135
```

**Saved to:** `logs/models/feature_importance_*.json`

---

## A/B Testing Models

Compare different models:

1. **Run with Linear:**
```yaml
active_model: 'linear'
use_ml: true
```
```bash
python test_signals.py > outputs/backtest_linear.txt
```

2. **Run with XGBoost:**
```yaml
active_model: 'xgboost'
use_ml: true
```
```bash
python test_signals.py > outputs/backtest_xgboost.txt
```

3. **Compare Results:**
- Check Sharpe ratios
- Check total returns
- Check feature importance

---

## Troubleshooting

### "No training samples found"

**Problem:** Training period has no data or no overlapping dates.

**Solution:**
1. Check `training.train_start` and `training.train_end` in config
2. Ensure these dates have price data and signals
3. Adjust date range to match your data

### "Model prediction failed"

**Problem:** Features don't match training format.

**Solution:**
- Ensure feature names in config match signal names
- Check that all 5 features are available (momentum, volume, RSI, supply_chain, sentiment)

### Model Overfitting

**Problem:** High train R² but low validation R².

**Solution:**
- Use simpler model (Linear/Ridge instead of XGBoost)
- Reduce XGBoost `max_depth` (e.g., 3 instead of 5)
- Increase regularization (higher `alpha` for Ridge/Lasso)

---

## Model Selection Guide

**Start Here:**
```yaml
use_ml: true
active_model: 'linear'
```

**If features are correlated:**
```yaml
active_model: 'ridge'
```

**If unsure which features matter:**
```yaml
active_model: 'lasso'  # Automatically selects important features
```

**If linear models plateau:**
```yaml
active_model: 'xgboost'
```

---

## Saved Models

Trained models are saved to `models/saved/`:

```
models/saved/linear_20260125_120000.pkl
models/saved/xgboost_20260125_120500.pkl
```

**Load a saved model:**
```python
from src.models.base_predictor import BaseReturnPredictor

model = BaseReturnPredictor.load_model('models/saved/linear_20260125_120000.pkl')
predictions = model.predict(X_features)
```

---

## Next Steps

1. **Try Linear First**: Baseline model, fast, interpretable
2. **Compare to Weighted Signals**: Run both, see which performs better
3. **Experiment with XGBoost**: If linear plateaus, try non-linear
4. **Tune Hyperparameters**: Adjust model config for better performance
5. **Add More Features**: Extend feature list in config (requires code changes)

---

**Last Updated:** 2026-01-25
