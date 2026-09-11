"""
Расширенный HMM на 10 технических признаках.
Сравнение с базовым HMM (5 признаков).
"""
import os, sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import numpy as np
import polars as pl
from hmmlearn import hmm
from sklearn.preprocessing import StandardScaler
from MOEXPy.MOEXPy import MOEXPy
from FinLabPy.DataCollectors.m10_to_d1_converter import M10ToD1Converter
from FinLabPy.My_Indicators.technical_features import add_technical_features
from FinLabPy.Utils import setup_logger

logger = setup_logger('hmm_enhanced')

FEATURES_10 = ['returns', 'volatility', 'volume_ratio', 'trend_strength',
               'price_vs_sma20', 'price_vs_sma50', 'rsi', 'macd_hist', 'bb_position']
FEATURES_5 = ['returns', 'volatility', 'volume_ratio', 'trend_strength', 'price_vs_sma20']


def prepare_data(df, feature_cols, n_regimes=4):
    df_clean = df[feature_cols + ['date', 'close']].drop_nulls()
    
    for col in feature_cols:
        df_clean = df_clean.filter(pl.col(col).is_finite())
    
    if df_clean.is_empty() or len(df_clean) < n_regimes * 2:
        print(f'  Недостаточно данных: {len(df_clean)} строк')
        return None, None, None, None, None
    
    X = df_clean[feature_cols].to_numpy()
    dates = df_clean['date'].to_list()
    closes = df_clean['close'].to_numpy()
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    model = hmm.GaussianHMM(n_components=n_regimes, covariance_type='full', n_iter=1000, random_state=42)
    model.fit(X_scaled)
    regimes = model.predict(X_scaled)
    return model, regimes, dates, closes, X_scaled


def analyze_regimes(regimes, dates, closes, n_regimes):
    # Считаем returns для ВСЕХ дней кроме первого
    returns = np.diff(closes) / closes[:-1]  # длина N-1
    
    # Берём режимы для всех дней кроме последнего (предсказание на сегодня → доходность завтра)
    regime_for_return = regimes[:-1]  # длина N-1
    
    # Теперь returns и regime_for_return одинаковой длины
    n_days = len(returns)
    
    print(f'\n{"="*60}')
    print(f'АНАЛИЗ РЕЖИМОВ ({n_regimes} режимов, {len(closes)} дней, {n_days} returns)')
    print(f'{"="*60}')
    
    for r in range(n_regimes):
        mask = regime_for_return == r
        count = mask.sum()
        pct = 100 * count / n_days if n_days > 0 else 0
        avg_ret = returns[mask].mean() * 100 if count > 0 else 0
        std_ret = returns[mask].std() * 100 if count > 0 else 0
        total_ret = (np.prod(1 + returns[mask]) - 1) * 100 if count > 0 else 0
        
        if avg_ret > 0.03: name = 'TREND_UP'
        elif avg_ret < -0.03: name = 'TREND_DOWN'
        elif std_ret > 0.8: name = 'VOLA'
        else: name = 'FLAT'
        
        print(f'\nРежим {r} ({name}):')
        print(f'  Дней: {count} ({pct:.1f}%)')
        print(f'  Средняя дох: {avg_ret:+.3f}%/день')
        print(f'  Вола: {std_ret:.3f}%')
        print(f'  Общая дох: {total_ret:+.1f}%')
    
    switches = (regimes[1:] != regimes[:-1]).sum()
    print(f'\nСмен режима: {switches} из {len(regimes)-1} ({100*switches/(len(regimes)-1):.1f}%)')


if __name__ == '__main__':
    api = MOEXPy(token=os.getenv('MOEX_TOKEN'))
    converter = M10ToD1Converter(api)
    
    print('Загрузка SBER D1...')
    df = converter.convert('TQBR', 'SBER', days=90, include_trades=False)
    print('Расчёт признаков...')
    df = add_technical_features(df)
    print(f'Данных: {len(df)} дней')
    
    for name, features, regimes_n in [
        ('БАЗОВЫЙ HMM (5 признаков)', FEATURES_5, 4),
        ('РАСШИРЕННЫЙ HMM (9 признаков)', FEATURES_10, 4),
        ('РАСШИРЕННЫЙ HMM (9 признаков, 3 режима)', FEATURES_10, 3),
    ]:
        print(f'\n{"="*60}')
        print(f'ТЕСТ: {name}')
        print(f'{"="*60}')
        _, regimes, dates, closes, _ = prepare_data(df, features, n_regimes=regimes_n)
        if regimes is not None:
            analyze_regimes(regimes, dates, closes, n_regimes=regimes_n)
