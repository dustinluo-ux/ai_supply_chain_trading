# Model Registry

## Currently Active Model
See `config/model_config.yaml` → `active_model`

## Available Models

### Linear Regression
**Type:** `linear`
**Class:** `LinearReturnPredictor`
**Hyperparameters:** None
**Pros:** Simple, interpretable, fast
**Cons:** Assumes linear relationships
**When to use:** Baseline, interpretability needed

### Ridge Regression  
**Type:** `ridge`
**Class:** `RidgeReturnPredictor`
**Hyperparameters:**
- `alpha`: Regularization strength (default: 1.0)
**Pros:** Handles multicollinearity, prevents overfitting
**Cons:** Still assumes linearity
**When to use:** Features are correlated (momentum + RSI)

### Lasso Regression
**Type:** `lasso`
**Class:** `LassoReturnPredictor`
**Hyperparameters:**
- `alpha`: Regularization strength (default: 0.1)
**Pros:** Automatic feature selection (sets weak features to 0)
**Cons:** May drop useful features
**When to use:** Unsure which features matter

### XGBoost
**Type:** `xgboost`
**Class:** `XGBoostReturnPredictor`
**Hyperparameters:**
- `n_estimators`: Number of trees (default: 100)
- `max_depth`: Tree depth (default: 3)
- `learning_rate`: Step size (default: 0.1)
**Pros:** Captures non-linear relationships, robust
**Cons:** Harder to interpret, can overfit
**When to use:** After linear models plateau

## How to Add New Models

1. Create model class in `src/models/your_model.py`:
```python
from .base_predictor import BaseReturnPredictor

class YourModel(BaseReturnPredictor):
    def _build_model(self):
        return YourModelImplementation()
    
    def get_feature_importance(self):
        return {...}
```

2. Register in `src/models/model_factory.py`:
```python
MODEL_REGISTRY = {
    ...
    'your_model': YourModel,
}
```

3. Add config in `config/model_config.yaml`:
```yaml
models:
  your_model:
    hyperparam1: value
    hyperparam2: value
```

4. Switch to it:
```yaml
active_model: 'your_model'
```

That's it! No other code changes needed.

## Model Selection Guide

**Start with:** `linear` (baseline)
**If correlated features:** `ridge`
**If too many features:** `lasso`
**If linear plateaus:** `xgboost`
**For time series:** (TODO: add LSTM/GRU)

## Feature Importance

All models provide feature importance:
- **Linear/Ridge/Lasso:** Coefficients (positive = bullish, negative = bearish)
- **XGBoost:** Feature importance scores (higher = more predictive)

View feature importance after training in:
- Console output
- `logs/models/feature_importance_*.json`

## Model Persistence

Trained models are saved to `models/saved/` with format:
```
{model_type}_{timestamp}.pkl
```

Load a saved model:
```python
from src.models.base_predictor import BaseReturnPredictor

model = BaseReturnPredictor.load_model('models/saved/linear_20260125_120000.pkl')
predictions = model.predict(X)
```

## A/B Testing Multiple Models

To compare models:

1. Train model A:
```yaml
# config/model_config.yaml
active_model: 'linear'
```
```bash
python test_signals.py  # Saves results
```

2. Train model B:
```yaml
# config/model_config.yaml
active_model: 'xgboost'
```
```bash
python test_signals.py  # Saves results
```

3. Compare results in backtest logs

---

**Last Updated:** 2026-01-25
