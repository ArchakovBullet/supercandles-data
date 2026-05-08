"""
Скринер режимов рынка: HMM 4 режима на всех инструментах OsEngine.
"""
import os, sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import numpy as np
import polars as pl
from hmmlearn import hmm
from sklearn.preprocessing import StandardScaler
from FinLabPy.DataCollectors.osengine_loader import OsEngineLoader
from FinLabPy.My_Indicators.technical_features import add_technical_features

FEATURES = ['returns', 'volatility', 'volume_ratio', 'trend_strength',
            'price_vs_sma20', 'price_vs_sma50', 'rsi', 'macd_hist', 'bb_position']


def analyze_one(instrument, loader):
    """Прогнать HMM 4 режима на одном инструменте."""
    try:
        df_raw = loader.load(instrument)
        df_daily = loader.to_daily(df_raw)
        
        if len(df_daily) < 100:
            return None
        
        df_features = add_technical_features(df_daily)
        
        # Очистка
        df_clean = df_features[FEATURES + ['date', 'close']].drop_nulls()
        for col in FEATURES:
            df_clean = df_clean.filter(pl.col(col).is_finite())
        
        if len(df_clean) < 50:
            return None
        
        X = df_clean[FEATURES].to_numpy()
        closes = df_clean['close'].to_numpy()
        
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        model = hmm.GaussianHMM(n_components=4, covariance_type='full', n_iter=1000, random_state=42)
        model.fit(X_scaled)
        labels = model.predict(X_scaled)
        
        # Анализ режимов
        returns = np.diff(closes) / closes[:-1]
        regime_for_return = labels[:-1]
        
        regimes_info = []
        for r in range(4):
            mask = regime_for_return == r
            count = mask.sum()
            if count == 0:
                continue
            avg_ret = returns[mask].mean() * 100
            total_ret = (np.prod(1 + returns[mask]) - 1) * 100
            
            if avg_ret > 0.05: name = 'UP'
            elif avg_ret < -0.05: name = 'DOWN'
            else: name = 'FLAT'
            
            regimes_info.append({
                'name': name,
                'count': count,
                'pct': 100 * count / len(returns),
                'avg_ret': avg_ret,
                'total_ret': total_ret,
            })
        
        # Находим лучший режим
        best = max(regimes_info, key=lambda x: x['avg_ret'])
        
        switches = (labels[1:] != labels[:-1]).sum()
        
        return {
            'instrument': instrument,
            'days': len(df_clean),
            'period': f'{df_clean["date"].min()} — {df_clean["date"].max()}',
            'best_regime': best['name'],
            'best_pct': best['pct'],
            'best_avg_ret': best['avg_ret'],
            'best_total_ret': best['total_ret'],
            'switches_pct': 100 * switches / (len(labels) - 1),
            'regimes': regimes_info,
        }
    except Exception as e:
        print(f'  {instrument}: ОШИБКА — {e}')
        return None


if __name__ == '__main__':
    loader = OsEngineLoader()
    instruments = loader.list_instruments()
    
    # Фильтруем: только с историей > 2 лет
    print('СКРИНЕР HMM 4 РЕЖИМА\n')
    
    results = []
    for name in instruments:
        print(f'Анализ: {name}...')
        result = analyze_one(name, loader)
        if result:
            results.append(result)
    
    # Сортируем по доходности лучшего режима
    results.sort(key=lambda x: x['best_avg_ret'], reverse=True)
    
    print(f'\n{"="*80}')
    print(f'{"Инструмент":20s} | {"Дней":5s} | {"Режим":6s} | {"Доля":6s} | {"Дох/день":>8s} | {"Общая":>8s} | {"Смен":5s}')
    print(f'{"-"*80}')
    for r in results:
        print(f'{r["instrument"]:20s} | {r["days"]:5d} | {r["best_regime"]:6s} | {r["best_pct"]:5.0f}% | {r["best_avg_ret"]:+7.3f}% | {r["best_total_ret"]:+7.1f}% | {r["switches_pct"]:4.0f}%')
    
    print(f'\n{"="*80}')
    print('ДЕТАЛЬНО ПО ВСЕМ РЕЖИМАМ:')
    for r in results:
        print(f'\n{r["instrument"]} ({r["days"]}д, {r["period"]}):')
        for reg in r['regimes']:
            print(f'  {reg["name"]:6s}: {reg["count"]:4d}д ({reg["pct"]:4.0f}%) | {reg["avg_ret"]:+6.3f}%/д | {reg["total_ret"]:+7.1f}%')
