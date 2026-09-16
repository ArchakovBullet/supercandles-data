#!/usr/bin/env python3
"""Проверить корреляцию других метрик FutOI."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

tickers = ['CE', 'MG', 'GD', 'SN', 'GZ', 'RI', 'SBERF', 'GAZPF']

metrics = ['fiz_buy_ratio', 'yur_buy_ratio', 'fiz_ratio_delta', 'yur_ratio_delta']

for metric in metrics:
    print(f'=== {metric} ===')
    corrs = []
    for ticker in tickers:
        df = pd.read_parquet(CANDLES / f'{ticker}_H1.parquet')
        futoi = pd.read_parquet(DATA_ROOT / 'futoi_1h' / 'futoi_1h.parquet')
        df_f = futoi[futoi['ticker'] == ticker].copy()
        if len(df_f) == 0 or metric not in df_f.columns:
            continue
        
        df['dt'] = pd.to_datetime(df['begin'])
        df_f['hour'] = pd.to_datetime(df_f['hour'])
        df = pd.merge(df, df_f[['hour', metric]], left_on='dt', right_on='hour', how='left')
        df = df.ffill()
        df['future_move'] = df['close'].shift(-4) - df['close']
        df_valid = df.dropna(subset=[metric, 'future_move'])
        if len(df_valid) > 10:
            corr = df_valid[metric].corr(df_valid['future_move'])
            corrs.append(corr)
            print(f'  {ticker}: {corr:+.4f}')
    if corrs:
        print(f'  Средняя: {sum(corrs)/len(corrs):+.4f}')
    print()
