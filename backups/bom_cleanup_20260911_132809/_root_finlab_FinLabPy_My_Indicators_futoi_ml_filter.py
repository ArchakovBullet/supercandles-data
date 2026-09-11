"""
ML-фильтр v2.2 — XGBoost + лаги + проценты
"""

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score
import joblib
from pathlib import Path
import talib
import warnings
warnings.filterwarnings('ignore')


class FutOIMLFilter:
    """ML-фильтр v2.2: XGBoost + лаговые признаки + проценты"""
    
    def __init__(self, model_path=None):
        self.model = None
        self.model_path = model_path or Path(__file__).parent / "futoi_ml_model_xgb.pkl"
        self.feature_names = [
            'phys_net', 'phys_change', 'jur_net',
            'price_vs_sma', 'rsi', 'atr_pct',
            'volume_ratio', 'trend_strength', 'futoi_divergence',
            'phys_net_lag1', 'phys_net_lag2', 'phys_net_lag3',
            'phys_net_ma3', 'phys_acceleration', 'volatility_10'
        ]
        
        if self.model_path.exists():
            self.model = joblib.load(self.model_path)
            print(f"   ML: модель XGBoost загружена")
    
    def prepare_features(self, df):
        features = pd.DataFrame(index=df.index)
        
        features['phys_net'] = df['phys_net']
        features['phys_change'] = df['phys_change']
        features['jur_net'] = df['jur_net']
        
        close = df['close'].values.astype(np.float64)
        high = df['high'].values.astype(np.float64)
        low = df['low'].values.astype(np.float64)
        volume = df['volume'].values.astype(np.float64)
        
        sma20 = talib.SMA(close, timeperiod=20)
        features['price_vs_sma'] = np.where(sma20 > 0, (close - sma20) / sma20 * 100, 0)
        features['rsi'] = talib.RSI(close, timeperiod=14)
        
        atr14 = talib.ATR(high, low, close, timeperiod=14)
        features['atr_pct'] = np.where(close > 0, atr14 / close * 100, 0)
        
        avg_vol = talib.SMA(volume, timeperiod=20)
        features['volume_ratio'] = np.where(avg_vol > 0, volume / avg_vol, 1)
        features['trend_strength'] = talib.ADX(high, low, close, timeperiod=14)
        features['futoi_divergence'] = df['phys_net'] - df['jur_net'].abs()
        features['volatility_10'] = df['close'].pct_change().rolling(10).std() * 100
        
        features['phys_net_lag1'] = df['phys_net'].shift(1)
        features['phys_net_lag2'] = df['phys_net'].shift(2)
        features['phys_net_lag3'] = df['phys_net'].shift(3)
        features['phys_net_ma3'] = df['phys_net'].rolling(3).mean()
        features['phys_acceleration'] = df['phys_change'].diff()
        
        features = features.fillna(0)
        return features
    
    def prepare_target(self, df, forward_days=1):
        close = df['close'].values
        future = np.roll(close, -forward_days)
        future[-forward_days:] = np.nan
        target = (future > close).astype(int)
        return pd.Series(target, index=df.index)
    
    def train(self, df, forward_days=1):
        print(f"\n   ML XGBoost: обучение...")
        
        X = self.prepare_features(df)
        y = self.prepare_target(df, forward_days)
        
        valid_idx = y.notna() & (y.index < len(y) - forward_days)
        X = X[valid_idx]
        y = y[valid_idx]
        
        if len(X) < 15:
            print(f"   ⚠️ ML: недостаточно данных ({len(X)} строк, нужно >=15)")
            return None
        
        split = int(len(X) * 0.7)
        X_train, X_test = X.iloc[:split], X.iloc[split:]
        y_train, y_test = y.iloc[:split], y.iloc[split:]
        
        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=1,
            reg_lambda=1,
            random_state=42,
            eval_metric='logloss'
        )
        
        self.model.fit(X_train, y_train)
        y_pred = self.model.predict(X_test)
        
        accuracy = accuracy_score(y_test, y_pred)
        precision_buy = precision_score(y_test, y_pred, pos_label=1, zero_division=0)
        precision_sell = precision_score(y_test, y_pred, pos_label=0, zero_division=0)
        
        print(f"   ML XGBoost: общая точность = {accuracy:.1%}")
        print(f"   ML: точность BUY = {precision_buy:.1%} | точность SELL = {precision_sell:.1%}")
        print(f"   ML: обучающая выборка = {len(X_train)} | тестовая = {len(X_test)}")
        
        # Топ-5 признаков (в %%)
        importances = self.model.feature_importances_
        total_imp = importances.sum()
        top5 = sorted(zip(self.feature_names, importances), key=lambda x: x[1], reverse=True)[:5]
        print(f"   ML: топ-5 признаков:")
        for name, imp in top5:
            pct = imp / total_imp * 100
            bar = '█' * int(pct)
            print(f"      {name:<22} {pct:5.1f}% {bar}")
        
        joblib.dump(self.model, self.model_path)
        print(f"   ML: модель XGBoost сохранена")
        
        return accuracy
    
    def predict_proba(self, features_df):
        if self.model is None:
            return 0.5
        
        X = self.prepare_features(features_df)
        last = X.iloc[-1:]
        proba = self.model.predict_proba(last)[0]
        return proba[1] if len(proba) > 1 else proba[0]
    
    def should_enter(self, features_df, min_probability=0.55):
        proba = self.predict_proba(features_df)
        
        if proba >= min_probability:
            return True, proba, 'BUY'
        elif proba <= (1 - min_probability):
            return True, 1 - proba, 'SELL'
        else:
            return False, proba, 'HOLD'
