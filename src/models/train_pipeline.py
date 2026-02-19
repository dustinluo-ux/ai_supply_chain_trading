"""
Model training pipeline.

Handles:
- Feature extraction (from prices_dict via calculate_all_indicators)
- Train/test split
- Model training
- Validation
- IC evaluation (Spearman)
- Logging
"""

import yaml
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple, Optional, Any

from .model_factory import create_model
from .base_predictor import BaseReturnPredictor

# Minimum price rows required for indicator computation (T-1 safety)
_MIN_PRICE_ROWS = 60

class ModelTrainingPipeline:
    """
    End-to-end model training pipeline.
    
    Usage:
        pipeline = ModelTrainingPipeline('config/model_config.yaml')
        model = pipeline.train(prices_dict, news_signals={})
        ic = pipeline.evaluate_ic(model, prices_dict, test_start='...', test_end='...')
        predictions = model.predict(current_features)
    """
    
    def __init__(self, config_path: str = 'config/model_config.yaml'):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        
        self.active_model_type = self.config['active_model']
        self.model_config = self.config['models'][self.active_model_type]
        self.feature_names = self.config['features']['feature_names']
        
        print(f"[Pipeline] Loaded config: {config_path}")
        print(f"[Pipeline] Active model: {self.active_model_type}")
    
    def prepare_training_data(self,
                             prices_dict: Dict,
                             technical_signals: Optional[Dict] = None,
                             news_signals: Optional[Dict] = None,
                             train_start: Optional[pd.Timestamp] = None,
                             train_end: Optional[pd.Timestamp] = None,
                             ) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        """
        Build training dataset. Features computed from prices_dict via calculate_all_indicators.
        
        For each stock, for each week in period:
            X = [momentum_avg, volume_ratio_norm, rsi_norm, news_supply, news_sentiment]
            y = forward 1-week return
        
        Returns:
            X: Features (n_samples, n_features)
            y: Forward returns (n_samples,)
            metadata: DataFrame with [ticker, date, forward_return]
        """
        train_config = self.config['training']
        start = train_start if train_start is not None else pd.to_datetime(train_config['train_start'])
        end = train_end if train_end is not None else pd.to_datetime(train_config['train_end'])
        news_signals = news_signals or {}
        
        X_list, y_list, meta_list = [], [], []
        
        for ticker in prices_dict.keys():
            dates = pd.date_range(start, end, freq='W-MON')
            for date in dates:
                features = self._extract_features(ticker, date, prices_dict, news_signals)
                if features is None:
                    continue
                forward_return = self._calculate_forward_return(ticker, date, prices_dict)
                if forward_return is None:
                    continue
                X_list.append(features)
                y_list.append(forward_return)
                meta_list.append({
                    'ticker': ticker,
                    'date': date,
                    'forward_return': forward_return
                })
        
        if len(X_list) == 0:
            raise ValueError("No training samples found. Check date ranges and data availability.")
        
        X = np.array(X_list)
        y = np.array(y_list)
        metadata = pd.DataFrame(meta_list)
        
        print(f"[Pipeline] Prepared {len(X)} training samples")
        print(f"  Features: {X.shape[1]}")
        if len(metadata) > 0:
            print(f"  Date range: {metadata['date'].min()} to {metadata['date'].max()}")
        
        return X, y, metadata
    
    def _extract_features(self, ticker: str, date: pd.Timestamp, prices_dict: Dict, news_signals: Optional[Dict] = None) -> Optional[list]:
        """
        Extract feature vector for one ticker/date from prices_dict using calculate_all_indicators.
        Requires at least 60 rows of price history before date. News from news_signals (default 0.0).
        """
        if ticker not in prices_dict:
            return None
        df = prices_dict[ticker]
        if df.empty or 'close' not in df.columns:
            return None
        slice_df = df[df.index <= date]
        if slice_df is None or slice_df.empty or len(slice_df) < _MIN_PRICE_ROWS:
            return None
        try:
            from src.signals.technical_library import calculate_all_indicators
            from src.data.csv_provider import ensure_ohlcv
            slice_df = ensure_ohlcv(slice_df.copy())
            if not all(c in slice_df.columns for c in ['open', 'high', 'low', 'close', 'volume']):
                return None
            ind = calculate_all_indicators(slice_df)
            if ind is None or ind.empty:
                return None
            row = ind.iloc[-1]
            rsi_norm = float(row.get('rsi_norm', 0.5))
            volume_ratio_norm = float(row.get('volume_ratio_norm', 0.5))
            m5 = float(row.get('momentum_5d_norm', 0.5))
            m20 = float(row.get('momentum_20d_norm', 0.5))
            momentum_avg = (m5 + m20) / 2.0
            news_signals = news_signals or {}
            date_str = date.strftime("%Y-%m-%d") if isinstance(date, pd.Timestamp) else str(date)
            news = news_signals.get(ticker, {}).get(date_str) or news_signals.get(ticker, {}).get(date) or {}
            if news is None:
                news = {}
            news_supply = float(news.get('supply_chain_score', news.get('supply_chain', 0.0)))
            news_sentiment = float(news.get('sentiment_score', news.get('sentiment', 0.0)))
            return [momentum_avg, volume_ratio_norm, rsi_norm, news_supply, news_sentiment]
        except Exception:
            return None
    
    def _calculate_forward_return(self, ticker: str, date: pd.Timestamp, prices_dict: Dict, horizon_days: int = 7) -> Optional[float]:
        """Calculate forward return using asof to handle non-trading days. Returns None if NaN."""
        try:
            prices = prices_dict[ticker]
            close = prices['close'] if isinstance(prices['close'], pd.Series) else prices.loc[:, 'close']
            price_current = close.asof(date)
            future_date = date + pd.Timedelta(days=horizon_days)
            price_future = close.asof(future_date)
            if pd.isna(price_current) or pd.isna(price_future) or price_current <= 0:
                return None
            return float((price_future - price_current) / price_current)
        except (KeyError, TypeError, AttributeError):
            return None
    
    def train(self, prices_dict: Dict, technical_signals: Optional[Dict] = None, news_signals: Optional[Dict] = None) -> BaseReturnPredictor:
        """
        Train the active model.
        
        Returns:
            Trained model
        """
        # Prepare data (technical_signals no longer used; features from prices_dict)
        X, y, metadata = self.prepare_training_data(
            prices_dict, technical_signals=technical_signals, news_signals=news_signals
        )
        
        # Train/validation split
        val_split = self.config['training']['validation_split']
        split_idx = int(len(X) * (1 - val_split))
        
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        print(f"[Pipeline] Train: {len(X_train)} samples, Val: {len(X_val)} samples")
        
        # Create model from config
        model = create_model(
            {**{'type': self.active_model_type}, **self.model_config},
            self.feature_names
        )
        
        # Train
        metrics = model.fit(X_train, y_train, X_val, y_val)
        
        # Log feature importance
        if self.config['logging']['log_feature_importance']:
            self._log_feature_importance(model)
        
        # Save model (caller may skip if IC gate fails)
        if self.config['training']['save_models']:
            save_dir = Path(self.config['training']['model_save_dir'])
            save_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            save_path = save_dir / f"{self.active_model_type}_{timestamp}.pkl"
            model.save_model(str(save_path))
        
        return model
    
    def evaluate_ic(self, model: BaseReturnPredictor, prices_dict: Dict,
                    test_start: str, test_end: str,
                    news_signals: Optional[Dict] = None) -> float:
        """
        Build test dataset, predict, compute Spearman IC between predictions and actual forward returns.
        Prints [IC] Spearman IC = {value:.4f} (n={n}). Returns IC as float.
        """
        test_start_dt = pd.to_datetime(test_start)
        test_end_dt = pd.to_datetime(test_end)
        X_test, y_test, meta = self.prepare_training_data(
            prices_dict,
            technical_signals=None,
            news_signals=news_signals or {},
            train_start=test_start_dt,
            train_end=test_end_dt,
        )
        if len(X_test) == 0:
            print("[IC] No test samples; IC = 0.0000 (n=0)")
            return 0.0
        pred = model.predict(X_test)
        from scipy.stats import spearmanr
        ic, _ = spearmanr(pred, y_test)
        ic = float(ic) if not np.isnan(ic) else 0.0
        n = len(y_test)
        print(f"[IC] Spearman IC = {ic:.4f} (n={n})")
        return ic
    
    def _log_feature_importance(self, model):
        """Log feature importance to console and file."""
        importance = model.get_feature_importance()
        
        print("\n[Feature Importance]")
        for feature, value in sorted(importance.items(), key=lambda x: abs(x[1]), reverse=True):
            print(f"  {feature:25s}: {value:8.4f}")
        
        # Save to file
        if self.config['logging'].get('log_dir'):
            log_dir = Path(self.config['logging']['log_dir'])
            log_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = log_dir / f"feature_importance_{timestamp}.json"
            
            import json
            with open(log_file, 'w') as f:
                json.dump(importance, f, indent=2)
