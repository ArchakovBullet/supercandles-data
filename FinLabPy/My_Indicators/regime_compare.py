"""
Сравнение 3 методов определения режимов рынка на данных OsEngine:
1. HMM (GaussianHMM)
2. K-Means кластеризация
3. Трендовый фильтр (ADX + SMA)
"""
import os, sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import numpy as np
import polars as pl
from hmmlearn import hmm
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from FinLabPy.DataCollectors.osengine_loader import OsEngineLoader
from FinLabPy.My_Indicators.technical_features import add_technical_features
from FinLabPy.Utils import setup_logger

logger = setup_logger('regime_compare')

FEATURES_10 = ['returns', 'volatility', 'volume_ratio', 'trend_strength',
               'price_vs_sma20', 'price_vs_sma50', 'rsi', 'macd_hist', 'bb_position']


def prepare_data(df, feature_cols):
    """Очистка данных от NaN и Inf."""
    df_clean = df[feature_cols + ['date', 'close']].drop_nulls()
    for col in feature_cols:
        df_clean = df_clean.filter(pl.col(col).is_finite())
    return df_clean


def analyze_regimes(labels, dates, closes, method_name, n_regimes):
    """Анализ доходности по режимам."""
    returns = np.diff(closes) / closes[:-1]
    regime_for_return = labels[:-1]
    n_days = len(returns)
    
    print(f'\n{"="*60}')
    print(f'{method_name} ({n_regimes} режимов, {len(closes)} дней, {n_days} returns)')
    print(f'{"="*60}')
    
    results = []
    for r in range(n_regimes):
        mask = regime_for_return == r
        count = mask.sum()
        if count == 0:
            continue
        pct = 100 * count / n_days
        avg_ret = returns[mask].mean() * 100
        std_ret = returns[mask].std() * 100
        total_ret = (np.prod(1 + returns[mask]) - 1) * 100
        
        if avg_ret > 0.05: name = 'TREND_UP'
        elif avg_ret < -0.05: name = 'TREND_DOWN'
        elif std_ret > 1.0: name = 'VOLA'
        else: name = 'FLAT'
        
        print(f'  Режим {r} ({name}): {count}д ({pct:.1f}%) | дох: {avg_ret:+.3f}%/д | вола: {std_ret:.3f}% | общ: {total_ret:+.1f}%')
        results.append({'regime': r, 'name': name, 'count': count, 'avg_ret': avg_ret, 'total_ret': total_ret})
    
    switches = (labels[1:] != labels[:-1]).sum()
    print(f'  Смен: {switches}/{len(labels)-1} ({100*switches/(len(labels)-1):.0f}%)')
    return results


def hmm_method(df_clean, feature_cols, n_regimes=4):
    """HMM Gaussian."""
    X = df_clean[feature_cols].to_numpy()
    closes = df_clean['close'].to_numpy()
    dates = df_clean['date'].to_list()
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    model = hmm.GaussianHMM(n_components=n_regimes, covariance_type='full', n_iter=1000, random_state=42)
    model.fit(X_scaled)
    labels = model.predict(X_scaled)
    
    return analyze_regimes(labels, dates, closes, 'HMM', n_regimes)


def kmeans_method(df_clean, feature_cols, n_regimes=4):
    """K-Means кластеризация."""
    X = df_clean[feature_cols].to_numpy()
    closes = df_clean['close'].to_numpy()
    dates = df_clean['date'].to_list()
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    kmeans = KMeans(n_clusters=n_regimes, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X_scaled)
    
    return analyze_regimes(labels, dates, closes, 'K-MEANS', n_regimes)


def trend_filter_method(df_clean):
    """Трендовый фильтр ADX + SMA (без ML)."""
    closes = df_clean['close'].to_numpy()
    dates = df_clean['date'].to_list()
    trend = df_clean['trend_strength'].to_numpy()  # ADX
    price_sma = df_clean['price_vs_sma20'].to_numpy()  # close/SMA20
    
    # Правила:
    # 0 = UP: price > SMA20 и ADX > 25
    # 1 = DOWN: price < SMA20 и ADX > 25
    # 2 = FLAT: всё остальное
    labels = np.full(len(closes), 2, dtype=int)
    labels[(price_sma > 1.0) & (trend > 25)] = 0  # UP
    labels[(price_sma < 1.0) & (trend > 25)] = 1  # DOWN
    
    return analyze_regimes(labels, dates, closes, 'ADX+SMA FILTER', 3)


if __name__ == '__main__':
    loader = OsEngineLoader()
    
    # Выбираем инструмент с самой длинной историей
    INSTRUMENT = 'Аэрофлот'
    
    print(f'=== ЗАГРУЗКА ДАННЫХ: {INSTRUMENT} ===')
    df_raw = loader.load(INSTRUMENT)
    df_daily = loader.to_daily(df_raw)
    print(f'Свечей: {len(df_raw)}, дней: {len(df_daily)}')
    print(f'Период: {df_daily["date"].min()} — {df_daily["date"].max()}')
    
    # Переименовываем колонки для совместимости с technical_features
    # (osengine_loader.to_daily уже даёт open, high, low, close, volume)
    
    print('\nРасчёт технических признаков...')
    df_features = add_technical_features(df_daily)
    
    # Очищаем
    print('Очистка данных...')
    df_clean_10 = prepare_data(df_features, FEATURES_10)
    print(f'После очистки: {len(df_clean_10)} дней')
    
    # Сравниваем методы
    print(f'\n{"#"*60}')
    print(f'СРАВНЕНИЕ МЕТОДОВ НА {INSTRUMENT}')
    print(f'{"#"*60}')
    
    print('\n>>> Метод 1: ADX + SMA фильтр (baseline)')
    trend_filter_method(df_clean_10)
    
    print('\n>>> Метод 2: K-Means (4 кластера)')
    kmeans_method(df_clean_10, FEATURES_10, n_regimes=4)
    
    print('\n>>> Метод 3: K-Means (3 кластера)')
    kmeans_method(df_clean_10, FEATURES_10, n_regimes=3)
    
    print('\n>>> Метод 4: HMM (4 режима)')
    hmm_method(df_clean_10, FEATURES_10, n_regimes=4)
    
    print('\n>>> Метод 5: HMM (3 режима)')
    hmm_method(df_clean_10, FEATURES_10, n_regimes=3)
    
    print(f'\n{"="*60}')
    print('ГОТОВО!')
    print(f'{"="*60}')
