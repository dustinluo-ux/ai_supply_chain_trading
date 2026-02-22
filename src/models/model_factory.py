"""
Model factory - creates models from config.

This is the ONLY place that knows about specific model classes.
Everything else just uses the factory.
"""

from typing import Dict, List
from .base_predictor import BaseReturnPredictor
from .linear_model import LinearReturnPredictor, RidgeReturnPredictor, LassoReturnPredictor
from .tree_model import XGBoostReturnPredictor

# Model registry - maps config names to classes
MODEL_REGISTRY = {
    'linear': LinearReturnPredictor,
    'ridge': RidgeReturnPredictor,
    'lasso': LassoReturnPredictor,
    'xgboost': XGBoostReturnPredictor,
    # Add new models here:
    # 'random_forest': RandomForestReturnPredictor,
    # 'lightgbm': LightGBMReturnPredictor,
    # 'lstm': LSTMReturnPredictor,
}

def create_model(model_config: Dict, feature_names: List[str]) -> BaseReturnPredictor:
    """
    Create a model from configuration.
    
    Args:
        model_config: Dict with 'type' and optional hyperparameters
        feature_names: List of feature names
        
    Returns:
        Model instance (not yet trained)
        
    Example config:
        {
            'type': 'xgboost',
            'n_estimators': 200,
            'max_depth': 5,
            'learning_rate': 0.05
        }
    """
    model_type = model_config.get('type', 'linear')
    
    if model_type not in MODEL_REGISTRY:
        raise ValueError(
            f"Unknown model type: {model_type}. "
            f"Available: {list(MODEL_REGISTRY.keys())}"
        )
    
    # Extract hyperparameters (everything except 'type')
    hyperparams = {k: v for k, v in model_config.items() if k != 'type'}
    
    # Create model instance
    model_class = MODEL_REGISTRY[model_type]
    return model_class(feature_names=feature_names, config=hyperparams)

def list_available_models() -> List[str]:
    """Return list of available model types."""
    return list(MODEL_REGISTRY.keys())
