"""
Base class for all return prediction models.

All models (Linear, Ridge, XGBoost, LSTM, etc.) inherit from this.
Ensures consistent interface across different model types.
"""

from abc import ABC, abstractmethod
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json
from pathlib import Path

class BaseReturnPredictor(ABC):
    """
    Abstract base class for stock return prediction models.
    
    All models must implement:
    - fit(X, y): Train the model
    - predict(X): Generate predictions
    - get_feature_importance(): Return feature weights/importance
    
    Models automatically handle:
    - Feature name tracking
    - Training metadata
    - Model versioning
    - Performance logging
    """
    
    def __init__(self, 
                 model_name: str,
                 model_type: str,
                 feature_names: List[str],
                 config: Dict = None):
        """
        Args:
            model_name: Human-readable name (e.g., "linear_baseline_v1")
            model_type: Model class (e.g., "LinearRegression", "XGBoost")
            feature_names: List of feature column names in order
            config: Model-specific hyperparameters
        """
        self.model_name = model_name
        self.model_type = model_type
        self.feature_names = feature_names
        self.config = config or {}
        
        # Training state
        self.is_trained = False
        self.training_date = None
        self.training_samples = None
        self.model = None  # Actual sklearn/xgboost/etc model
        
        # Performance tracking
        self.train_metrics = {}
        self.test_metrics = {}
        
    @abstractmethod
    def _build_model(self):
        """
        Build the actual model instance.
        
        Each subclass implements this to create their specific model.
        Example:
            return LinearRegression()
            return Ridge(alpha=self.config['alpha'])
            return XGBRegressor(**self.config)
        """
        pass
    
    def fit(self, X: np.ndarray, y: np.ndarray, 
            X_val: Optional[np.ndarray] = None,
            y_val: Optional[np.ndarray] = None) -> Dict:
        """
        Train the model.
        
        Args:
            X: Training features (n_samples, n_features)
            y: Training targets (n_samples,)
            X_val: Optional validation features
            y_val: Optional validation targets
            
        Returns:
            Training metrics dict
        """
        # Validate input dimensions
        if X.shape[1] != len(self.feature_names):
            raise ValueError(
                f"Feature count mismatch: got {X.shape[1]}, "
                f"expected {len(self.feature_names)}"
            )
        
        # Build model if not exists
        if self.model is None:
            self.model = self._build_model()
        
        # Train
        print(f"[{self.model_name}] Training on {len(X)} samples...")
        self.model.fit(X, y)
        
        # Record training metadata
        self.is_trained = True
        self.training_date = datetime.now().isoformat()
        self.training_samples = len(X)
        
        # Calculate training metrics
        y_pred_train = self.model.predict(X)
        self.train_metrics = self._calculate_metrics(y, y_pred_train, "train")
        
        # Calculate validation metrics if provided
        if X_val is not None and y_val is not None:
            y_pred_val = self.model.predict(X_val)
            self.test_metrics = self._calculate_metrics(y_val, y_pred_val, "validation")
        
        print(f"[{self.model_name}] Training complete.")
        print(f"  Train R²: {self.train_metrics['r2']:.4f}")
        if self.test_metrics:
            print(f"  Val R²: {self.test_metrics['r2']:.4f}")
        
        return {
            'train': self.train_metrics,
            'validation': self.test_metrics
        }
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Generate predictions.
        
        Args:
            X: Features (n_samples, n_features)
            
        Returns:
            Predicted returns (n_samples,)
        """
        if not self.is_trained:
            raise RuntimeError("Model not trained. Call fit() first.")
        
        return self.model.predict(X)
    
    @abstractmethod
    def get_feature_importance(self) -> Dict[str, float]:
        """
        Return feature importance/coefficients.
        
        Each model type implements this differently:
        - Linear/Ridge/Lasso: coefficients
        - Tree-based: feature_importances_
        - Neural nets: requires separate analysis
        
        Returns:
            Dict mapping feature_name → importance score
        """
        pass
    
    def _calculate_metrics(self, y_true: np.ndarray, 
                          y_pred: np.ndarray,
                          split_name: str) -> Dict:
        """Calculate standard regression metrics."""
        from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
        
        # Correlation (Information Coefficient for ranking)
        ic = np.corrcoef(y_true, y_pred)[0, 1] if len(y_true) > 1 else 0.0
        
        return {
            'r2': r2_score(y_true, y_pred),
            'mse': mean_squared_error(y_true, y_pred),
            'rmse': np.sqrt(mean_squared_error(y_true, y_pred)),
            'mae': mean_absolute_error(y_true, y_pred),
            'ic': ic,  # Rank correlation (key metric for trading)
            'n_samples': len(y_true)
        }
    
    def save_model(self, path: str):
        """Save trained model to disk."""
        import pickle
        
        save_data = {
            'model': self.model,
            'model_name': self.model_name,
            'model_type': self.model_type,
            'feature_names': self.feature_names,
            'config': self.config,
            'training_date': self.training_date,
            'train_metrics': self.train_metrics,
            'test_metrics': self.test_metrics
        }
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump(save_data, f)
        
        print(f"[{self.model_name}] Saved to {path}")
    
    @classmethod
    def load_model(cls, path: str) -> 'BaseReturnPredictor':
        """Load trained model from disk."""
        import pickle
        
        with open(path, 'rb') as f:
            save_data = pickle.load(f)
        
        # Reconstruct model instance: subclasses only accept (feature_names, config=...)
        # (task6_validation.md BUG 1). Set model_name/model_type on instance after construction.
        instance = cls(
            feature_names=save_data['feature_names'],
            config=save_data.get('config')
        )
        instance.model_name = save_data['model_name']
        instance.model_type = save_data['model_type']
        instance.model = save_data['model']
        instance.is_trained = True
        instance.training_date = save_data['training_date']
        instance.train_metrics = save_data['train_metrics']
        instance.test_metrics = save_data['test_metrics']
        
        return instance
    
    def to_dict(self) -> Dict:
        """Export model metadata as dictionary."""
        return {
            'model_name': self.model_name,
            'model_type': self.model_type,
            'feature_names': self.feature_names,
            'config': self.config,
            'is_trained': self.is_trained,
            'training_date': self.training_date,
            'training_samples': self.training_samples,
            'train_metrics': self.train_metrics,
            'test_metrics': self.test_metrics,
            'feature_importance': self.get_feature_importance() if self.is_trained else None
        }
