#!/usr/bin/env python3
"""Проверить, что fiz_buy_ratio попадает в свечи после merge."""
import sys
sys.path.insert(0, '/root/finlab/FinLabPy')
sys.path.insert(0, '/root/finlab')

import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

for ticker in ['CE', 'MG', 'GD', 'SN', 'GZ']:
    print(f'\n=== {ticker} ===')
    
    # Загружаем свечи
    df_d1 = pd.read_parquet(CANDLES / f'{ticker}_D1.parquet')
    df_4h = pd.read_parquet(CANDLES / f'{ticker}_H4.parquet')
    df_1h = pd.read_parquet(CANDLES / f'{ticker}_H1.parquet')
    
    # Загружаем FutOI
    futoi_4h = pd.read_parquet(DATA_ROOT / 'futoi_4h' / 'futoi_4h.parquet')
    futoi_1h = pd.read_parquet(DATA_ROOT / 'futoi_1h' / 'futoi_1h.parquet')
    
    df_futoi_4h = futoi_4h[futoi_4h['ticker'] == ticker].copy()
    df_futoi_1h = futoi_1h[futoi_1h['ticker'] == ticker].copy()
    
    print(f'  futoi_4h: {len(df_futoi_4h)} строк, колонки: {list(df_futoi_4h.columns)}')
    print(f'  futoi_1h: {len(df_futoi_1h)} строк')
    
    if len(df_futoi_4h) == 0:
        print(f'  ⚠️ НЕТ FutOI 4H для {ticker}')
        continue
    
    # Merge как в роботе
    df_4h['tradedate'] = pd.to_datetime(df_4h['tradedate'])
    df_futoi_4h['hour'] = pd.to_datetime(df_futoi_4h['hour'])
    df_4h_merged = pd.merge(df_4h, df_futoi_4h[['hour', 'fiz_buy_ratio', 'fiz_ratio_delta']],
                             left_on='tradedate', right_on='hour', how='left')
    df_4h_merged = df_4h_merged.ffill()
    df_4h_merged['fiz_buy_ratio'] = df_4h_merged['fiz_buy_ratio'].fillna(50)
    
    last = df_4h_merged.iloc[-1]
    print(f'  df_4h (last): tradedate={last["tradedate"]}, fiz_buy={last["fiz_buy_ratio"]:.1f}')
    
    # Проверяем, что merge сработал
    n_nan = df_4h_merged['fiz_buy_ratio'].isna().sum()
    n_50 = (df_4h_merged['fiz_buy_ratio'] == 50).sum()
    print(f'  NaN: {n_nan}, =50: {n_50}, всего: {len(df_4h_merged)}')
