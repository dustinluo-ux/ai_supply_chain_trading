"""Linear regression models (Linear, Ridge, Lasso)."""

from sklearn.linear_model import LinearRegression, Ridge, Lasso
from .base_predictor import BaseReturnPredictor
from typing import Dict
import numpy as np

class LinearReturnPredictor(BaseReturnPredictor):
    """
    Linear regression predictor.
    
    Config options:
        (none - basic linear regression)
    """
    
    def __init__(self, feature_names, config=None):
        super().__init__(
            model_name="linear_regression",
            model_type="LinearRegression",
            feature_names=feature_names,
            config=config or {}
        )
    
    def _build_model(self):
        return LinearRegression()
    
    def get_feature_importance(self) -> Dict[str, float]:
        if not self.is_trained:
            return {}
        
        return {
            name: float(coef) 
            for name, coef in zip(self.feature_names, self.model.coef_)
        }

class RidgeReturnPredictor(BaseReturnPredictor):
    """
    Ridge regression (L2 regularization).
    
    Config options:
        alpha: Regularization strength (default: 1.0)
    """
    
    def __init__(self, feature_names, config=None):
        config = config or {}
        super().__init__(
            model_name=f"ridge_alpha{config.get('alpha', 1.0)}",
            model_type="Ridge",
            feature_names=feature_names,
            config=config
        )
    
    def _build_model(self):
        return Ridge(alpha=self.config.get('alpha', 1.0))
    
    def get_feature_importance(self) -> Dict[str, float]:
        if not self.is_trained:
            return {}
        
        return {
            name: float(coef) 
            for name, coef in zip(self.feature_names, self.model.coef_)
        }

class LassoReturnPredictor(BaseReturnPredictor):
    """
    Lasso regression (L1 regularization, feature selection).
    
    Config options:
        alpha: Regularization strength (default: 0.1)
    """
    
    def __init__(self, feature_names, config=None):
        config = config or {}
        super().__init__(
            model_name=f"lasso_alpha{config.get('alpha', 0.1)}",
            model_type="Lasso",
            feature_names=feature_names,
            config=config
        )
    
    def _build_model(self):
        return Lasso(alpha=self.config.get('alpha', 0.1))
    
    def get_feature_importance(self) -> Dict[str, float]:
        if not self.is_trained:
            return {}
        
        return {
            name: float(coef) 
            for name, coef in zip(self.feature_names, self.model.coef_)
        }
