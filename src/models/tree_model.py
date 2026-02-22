"""Tree-based models (RandomForest, XGBoost, LightGBM)."""

from .base_predictor import BaseReturnPredictor
from typing import Dict
import numpy as np

class XGBoostReturnPredictor(BaseReturnPredictor):
    """
    XGBoost gradient boosting.
    
    Config options:
        n_estimators: Number of trees (default: 100)
        max_depth: Tree depth (default: 3)
        learning_rate: Step size (default: 0.1)
        ... (all XGBoost hyperparameters supported)
    """
    
    def __init__(self, feature_names, config=None):
        config = config or {}
        super().__init__(
            model_name=f"xgboost_n{config.get('n_estimators', 100)}",
            model_type="XGBoost",
            feature_names=feature_names,
            config=config
        )
    
    def _build_model(self):
        try:
            import xgboost as xgb
        except ImportError:
            raise ImportError(
                "XGBoost not installed. Install with: pip install xgboost"
            )
        
        # Default hyperparameters for financial data
        default_config = {
            'n_estimators': 100,
            'max_depth': 3,
            'learning_rate': 0.1,
            'objective': 'reg:squarederror',
            'random_state': 42
        }
        
        # Merge with user config
        final_config = {**default_config, **self.config}
        
        return xgb.XGBRegressor(**final_config)
    
    def get_feature_importance(self) -> Dict[str, float]:
        if not self.is_trained:
            return {}
        
        return {
            name: float(importance)
            for name, importance in zip(self.feature_names, self.model.feature_importances_)
        }

# TODO: Add RandomForestReturnPredictor, LightGBMReturnPredictor when needed
