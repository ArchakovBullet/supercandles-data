import os, sys
from pathlib import Path
project_root = Path('.').absolute()
sys.path.insert(0, str(project_root))

import numpy as np
import polars as pl
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

FEATURES = ['returns', 'volatility', 'volume_ratio', 'trend_strength',
            'price_vs_sma20', 'price_vs_sma50', 'rsi', 'macd_hist', 'bb_position']

def analyze_clusters(df, n_clusters=3):
    X = df[FEATURES].to_numpy()
    closes = df['close'].to_numpy()
    
    mask = ~np.isnan(X).any(axis=1) & ~np.isinf(X).any(axis=1)
    X = X[mask]
    closes = closes[mask]
    
    if len(X) == 0:
        print('Empty data!')
        return None
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X_scaled)
    
    returns_arr = np.diff(closes) / closes[:-1]
    c_returns = returns_arr
    c_labels = labels[:-1]
    
    print(f'\nK-MEANS ({n_clusters} clusters)')
    print('='*50)
    
    for c in range(n_clusters):
        mask_c = c_labels == c
        count = mask_c.sum()
        pct = 100 * count / len(c_labels)
        avg_ret = c_returns[mask_c].mean() * 100 if count > 0 else 0
        std_ret = c_returns[mask_c].std() * 100 if count > 0 else 0
        
        if avg_ret > 0.02: name = 'UP'
        elif avg_ret < -0.02: name = 'DOWN'
        elif std_ret < 0.3: name = 'FLAT'
        else: name = 'VOLA'
        
        print(f'  Cluster {c} ({name:4s}): {count:2d}d ({pct:3.0f}%), ret={avg_ret:+.3f}%/d, vol={std_ret:.3f}%')
    
    switches = (labels[1:] != labels[:-1]).sum()
    print(f'  Switches: {switches}/{len(labels)-1} ({100*switches/(len(labels)-1):.0f}%)')
    return labels

# MAIN
try:
    df = pl.read_parquet('data/sber_d1_features.parquet')
    print(f'Loaded from cache: {len(df)} days')
except:
    print('No cache, loading from API...')
    from MOEXPy.MOEXPy import MOEXPy
    from FinLabPy.DataCollectors.m10_to_d1_converter import M10ToD1Converter
    from FinLabPy.My_Indicators.technical_features import add_technical_features
    
    api = MOEXPy(token=os.getenv('MOEX_TOKEN'))
    converter = M10ToD1Converter(api)
    df = converter.convert('TQBR', 'SBER', days=90, include_trades=False)
    df = add_technical_features(df)
    df.write_parquet('data/sber_d1_features.parquet')
    print(f'Saved: {len(df)} days')

for k in [3, 4]:
    analyze_clusters(df, n_clusters=k)
