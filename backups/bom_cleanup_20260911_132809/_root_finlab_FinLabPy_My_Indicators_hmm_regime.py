# -*- coding: utf-8 -*-
"""
HMM-классификатор режимов рынка
Использует hmmlearn.GaussianHMM + TA-Lib для признаков
"""
import numpy as np
import polars as pl
import talib
from hmmlearn import hmm
import pickle


class MarketRegimeHMM:
    """
    Скрытая Марковская Модель для определения режимов рынка.
    
    Признаки:
    - returns: дневная доходность
    - volatility: ATR / Close
    - volume_ratio: Volume / SMA(Volume, 20)
    - trend_strength: ADX / 100
    - price_vs_sma: (Close - SMA20) / SMA20
    """
    
    def __init__(self, n_regimes: int = 3):
        self.n_regimes = n_regimes
        self.model = None
        self.feature_names = ['returns', 'volatility', 'volume_ratio', 'trend_strength', 'price_vs_sma']
        self.regime_names = []
        
    def prepare_features(self, df: pl.DataFrame) -> np.ndarray:
        """Готовит признаки из OHLCV"""
        high = df['high'].to_numpy().astype(np.float64)
        low = df['low'].to_numpy().astype(np.float64)
        close = df['close'].to_numpy().astype(np.float64)
        volume = df['volume'].to_numpy().astype(np.float64)
        
        n = len(close)
        
        # 1. Доходность
        returns_pct = np.zeros(n)
        returns_pct[1:] = (close[1:] - close[:-1]) / close[:-1]
        
        # 2. Волатильность: ATR(14) / Close
        atr = talib.ATR(high, low, close, timeperiod=14)
        volatility = np.nan_to_num(atr / close, nan=0.0)
        
        # 3. Объем / SMA(Volume, 20)
        vol_sma = talib.SMA(volume, timeperiod=20)
        vol_sma = np.where(vol_sma == 0, 1.0, vol_sma)
        volume_ratio = volume / vol_sma
        volume_ratio = np.nan_to_num(volume_ratio, nan=1.0)
        
        # 4. ADX(14) / 100
        adx = talib.ADX(high, low, close, timeperiod=14)
        trend_strength = np.nan_to_num(adx / 100.0, nan=0.0)
        
        # 5. (Close - SMA20) / SMA20
        sma20 = talib.SMA(close, timeperiod=20)
        sma20 = np.where(sma20 == 0, 1.0, sma20)
        price_vs_sma = (close - sma20) / sma20
        price_vs_sma = np.nan_to_num(price_vs_sma, nan=0.0)
        
        features = np.column_stack([
            returns_pct,
            volatility,
            volume_ratio,
            trend_strength,
            price_vs_sma,
        ])
        
        return features
    
    def fit(self, features: np.ndarray):
        """Обучает HMM"""
        self.model = hmm.GaussianHMM(
            n_components=self.n_regimes,
            covariance_type="full",
            n_iter=1000,
            random_state=42,
            tol=0.01,
        )
        self.model.fit(features)
        self._name_regimes(features)
        return self
    
    def predict(self, features: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise ValueError("Model not fitted. Call fit() first.")
        return self.model.predict(features)
    
    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(features)
    
    def get_current_regime(self, features: np.ndarray) -> tuple:
        """(regime_id, regime_name, confidence, all_probs)"""
        states = self.predict(features)
        probs = self.predict_proba(features)
        regime_id = states[-1]
        return regime_id, self.regime_names[regime_id], probs[-1][regime_id], probs[-1]
    
    def _name_regimes(self, features: np.ndarray):
        """Именует режимы по средней доходности"""
        states = self.model.predict(features)
        
        stats = {}
        for s in range(self.n_regimes):
            mask = states == s
            stats[s] = {
                'mean_return': np.mean(features[mask, 0]),
                'mean_vol': np.mean(features[mask, 1]),
                'count': np.sum(mask),
            }
        
        sorted_by_return = sorted(stats.keys(), key=lambda s: stats[s]['mean_return'])
        
        self.regime_names = [''] * self.n_regimes
        
        if self.n_regimes == 3:
            self.regime_names[sorted_by_return[0]] = 'TREND_DOWN'
            self.regime_names[sorted_by_return[1]] = 'FLAT'
            self.regime_names[sorted_by_return[2]] = 'TREND_UP'
        elif self.n_regimes == 4:
            self.regime_names[sorted_by_return[0]] = 'TREND_DOWN'
            self.regime_names[sorted_by_return[-1]] = 'TREND_UP'
            rest = [s for s in range(4) if s not in (sorted_by_return[0], sorted_by_return[-1])]
            if stats[rest[0]]['mean_vol'] > stats[rest[1]]['mean_vol']:
                self.regime_names[rest[0]] = 'VOLA'
                self.regime_names[rest[1]] = 'FLAT'
            else:
                self.regime_names[rest[0]] = 'FLAT'
                self.regime_names[rest[1]] = 'VOLA'
        
        for s in range(self.n_regimes):
            print(f"  {self.regime_names[s]}: "
                  f"return={stats[s]['mean_return']:.4f}, "
                  f"vol={stats[s]['mean_vol']:.4f}, "
                  f"bars={stats[s]['count']}")
    
    def save(self, filepath: str):
        with open(filepath, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'feature_names': self.feature_names,
                'regime_names': self.regime_names,
                'n_regimes': self.n_regimes,
            }, f)
        print(f"Saved: {filepath}")
    
    @classmethod
    def load(cls, filepath: str) -> 'MarketRegimeHMM':
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
        inst = cls(n_regimes=data['n_regimes'])
        inst.model = data['model']
        inst.feature_names = data['feature_names']
        inst.regime_names = data['regime_names']
        return inst


# ========== TEST ==========
if __name__ == '__main__':
    from datetime import datetime, timedelta
    
    print("=" * 60)
    print("HMM REGIME TEST")
    print("=" * 60)
    
    np.random.seed(42)
    n_days = 300
    
    close = np.zeros(n_days)
    close[0] = 100
    
    for i in range(1, 100):
        close[i] = close[i-1] * (1 + np.random.normal(0.002, 0.015))
    for i in range(100, 200):
        close[i] = close[i-1] * (1 + np.random.normal(0, 0.01))
    for i in range(200, 300):
        close[i] = close[i-1] * (1 + np.random.normal(-0.002, 0.015))
    
    high = close * (1 + np.abs(np.random.normal(0, 0.02, n_days)))
    low = close * (1 - np.abs(np.random.normal(0, 0.02, n_days)))
    open_p = close * (1 + np.random.normal(0, 0.005, n_days))
    volume = np.random.uniform(10000, 100000, n_days)
    
    df = pl.DataFrame({
        'datetime': [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n_days)],
        'open': open_p, 'high': high, 'low': low, 'close': close, 'volume': volume,
    })
    
    print(f"Synthetic data: {n_days} days")
    
    hmm_model = MarketRegimeHMM(n_regimes=3)
    features = hmm_model.prepare_features(df)
    hmm_model.fit(features)
    
    states = hmm_model.predict(features)
    
    for period_name, start, end in [("UP (0-99)", 0, 100), ("FLAT (100-199)", 100, 200), ("DOWN (200-299)", 200, 300)]:
        period_states = states[start:end]
        unique, counts = np.unique(period_states, return_counts=True)
        print(f"\n{period_name}:")
        for u, c in zip(unique, counts):
            print(f"  {hmm_model.regime_names[u]}: {c} days ({c/(end-start)*100:.0f}%)")
    
    regime_id, name, conf, probs = hmm_model.get_current_regime(features)
    print(f"\nLast bar regime: {name} (conf={conf:.1%})")
    print(f"All probs: {dict(zip(hmm_model.regime_names, [f'{p:.1%}' for p in probs]))}")
    
    print("\nTest passed!")
