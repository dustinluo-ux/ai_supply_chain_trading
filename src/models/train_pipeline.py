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
        
        # Iteration 2 (docs/ml_ic_diagnosis.md): cross-sectional z-score label — group by date,
        # replace each raw return with (return − date_mean) / date_std; if std=0 keep raw return.
        # Applied identically for train and test (evaluate_ic uses prepare_training_data).
        metadata = pd.DataFrame(meta_list)
        y_arr = np.array(y_list, dtype=float)
        for date in metadata['date'].unique():
            mask = (metadata['date'] == date).values
            indices = np.where(mask)[0]
            returns = y_arr[indices]
            date_mean = float(np.mean(returns))
            date_std = float(np.std(returns))
            if date_std > 0:
                z = (returns - date_mean) / date_std
                y_arr[indices] = z
                for k, idx in enumerate(indices):
                    meta_list[idx]['forward_return'] = float(z[k])
        y = y_arr
        metadata = pd.DataFrame(meta_list)
        X = np.array(X_list)
        
        print(f"[Pipeline] Prepared {len(X)} training samples")
        print(f"  Features: {X.shape[1]}")
        if len(metadata) > 0:
            print(f"  Date range: {metadata['date'].min()} to {metadata['date'].max()}")
        
        return X, y, metadata
    
    def extract_features_for_date(self, ticker: str, date: pd.Timestamp, prices_dict: Dict, news_signals: Optional[Dict] = None) -> Optional[list]:
        """
        Extract feature vector for one ticker/date from prices_dict using calculate_all_indicators.
        Requires at least 60 rows of price history before date. News from news_signals (default 0.5 = neutral).
        Public API for Phase 3 ML blend (target_weight_pipeline).
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
            ticker_news = (news_signals or {}).get(ticker, {})
            news = ticker_news.get(date_str) or ticker_news.get(date) or {}
            if news is None:
                news = {}
            # Fix 2 (docs/ml_ic_result.md): NEWS NEUTRAL DEFAULT — pre-2025 rows have no news;
            # use 0.5 (neutral) not 0.0 (bearish) per Phase 3 technical-first ML policy.
            news_supply = float(news.get('supply_chain_score', news.get('supply_chain', 0.5)))
            news_sentiment = float(news.get('sentiment_score', news.get('sentiment', 0.5)))

            # sentiment_velocity: change in sentiment vs a recent past day (first match in [5,6,7,4,3] days back)
            past_sentiment = None
            for offset in [5, 6, 7, 4, 3]:
                past_date = date - pd.Timedelta(days=offset)
                past_str = past_date.strftime("%Y-%m-%d")
                if past_str in ticker_news:
                    past_news = ticker_news.get(past_str) or {}
                    if past_news is None:
                        past_news = {}
                    past_sentiment = float(past_news.get('sentiment_score', past_news.get('sentiment', 0.5)))
                    break
            sentiment_velocity = (news_sentiment - past_sentiment) if past_sentiment is not None else 0.0

            # news_spike: current news_supply relative to mean of prior 20 calendar days (need >= 5 entries)
            supply_values = []
            for d in range(1, 21):
                back_date = date - pd.Timedelta(days=d)
                back_str = back_date.strftime("%Y-%m-%d")
                if back_str not in ticker_news:
                    continue
                back_news = ticker_news.get(back_str) or {}
                if back_news is None:
                    back_news = {}
                supply_values.append(float(back_news.get('supply_chain_score', back_news.get('supply_chain', 0.5))))
            if len(supply_values) >= 5:
                mean_supply = float(np.mean(supply_values))
                news_spike = (news_supply / mean_supply) if mean_supply > 0 else 1.0
            else:
                news_spike = 1.0

            return [momentum_avg, volume_ratio_norm, rsi_norm, news_supply, news_sentiment, sentiment_velocity, news_spike]
        except Exception:
            return None

    # Backward compatibility: private alias for use inside the class (prepare_training_data, etc.)
    _extract_features = extract_features_for_date

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
        Anchored walk-forward IC per DECISIONS.md D021: anchor fixed at config train_start,
        step through test period in 13-week folds. Fold k: train anchor→fold_k_start,
        test next 13 weeks. Refit model each fold; gate metric = mean IC >= 0.02.
        """
        from scipy.stats import spearmanr

        # DECISIONS.md D021: anchored walk-forward — anchor fixed at train_start;
        # Fold 1: train anchor→test_start, test next 13 weeks; Fold 2: train anchor→fold1_end, test next 13 weeks; etc.
        anchor = pd.to_datetime(self.config['training']['train_start'])
        test_start_dt = pd.to_datetime(test_start)
        test_end_dt = pd.to_datetime(test_end)
        news_signals = news_signals or {}
        fold_weeks = 13
        week_days = 7 * fold_weeks
        ic_list = []
        val_split = self.config['training']['validation_split']
        fold_start = test_start_dt

        while fold_start + pd.Timedelta(days=week_days) <= test_end_dt:
            train_end_fold = fold_start
            test_end_fold = fold_start + pd.Timedelta(days=week_days)
            # Train: [anchor, train_end_fold]
            X_train, y_train, _ = self.prepare_training_data(
                prices_dict,
                technical_signals=None,
                news_signals=news_signals,
                train_start=anchor,
                train_end=train_end_fold,
            )
            if len(X_train) < 10:
                fold_start = test_end_fold
                continue
            split_idx = int(len(X_train) * (1 - val_split))
            X_t, X_v = X_train[:split_idx], X_train[split_idx:]
            y_t, y_v = y_train[:split_idx], y_train[split_idx:]
            model_fold = create_model(
                {**{'type': self.active_model_type}, **self.model_config},
                self.feature_names
            )
            model_fold.fit(X_t, y_t, X_v, y_v)
            # Test: [fold_start, test_end_fold]
            X_test, y_test, _ = self.prepare_training_data(
                prices_dict,
                technical_signals=None,
                news_signals=news_signals,
                train_start=fold_start,
                train_end=test_end_fold,
            )
            if len(X_test) == 0:
                fold_start = test_end_fold
                continue
            pred = model_fold.predict(X_test)
            ic, _ = spearmanr(pred, y_test)
            ic_f = float(ic) if not np.isnan(ic) else 0.0
            ic_list.append(ic_f)
            print(f"[IC] fold {len(ic_list)} (test {fold_start.date()}–{test_end_fold.date()}) Spearman IC = {ic_f:.4f} (n={len(y_test)})")
            fold_start = test_end_fold

        if not ic_list:
            print("[IC] No walk-forward folds; mean IC = 0.0000")
            return 0.0
        mean_ic = float(np.mean(ic_list))
        print(f"[IC] Walk-forward mean Spearman IC = {mean_ic:.4f} (folds={len(ic_list)})")
        return mean_ic
    
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
