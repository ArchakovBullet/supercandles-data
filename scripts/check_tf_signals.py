#!/usr/bin/env python3
"""Проверить сигналы ТФ для конкретного тикера."""
import sys
sys.path.insert(0, '/root/finlab/FinLabPy')
sys.path.insert(0, '/root/finlab')

import pandas as pd
from pathlib import Path
from My_Indicators.unified_scanner import get_tf_signal

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

for ticker in ['CE', 'MG', 'GD', 'SN', 'GZ']:
    print(f'\n=== {ticker} ===')
    
    df_d1 = pd.read_parquet(CANDLES / f'{ticker}_D1.parquet')
    df_4h = pd.read_parquet(CANDLES / f'{ticker}_H4.parquet')
    df_1h = pd.read_parquet(CANDLES / f'{ticker}_H1.parquet')
    
    # Merge FutOI
    futoi_4h = pd.read_parquet(DATA_ROOT / 'futoi_4h' / 'futoi_4h.parquet')
    futoi_1h = pd.read_parquet(DATA_ROOT / 'futoi_1h' / 'futoi_1h.parquet')
    
    df_futoi_4h = futoi_4h[futoi_4h['ticker'] == ticker].copy()
    df_futoi_1h = futoi_1h[futoi_1h['ticker'] == ticker].copy()
    
    if len(df_futoi_4h) > 0:
        df_4h['tradedate'] = pd.to_datetime(df_4h['tradedate'])
        df_futoi_4h['hour'] = pd.to_datetime(df_futoi_4h['hour'])
        df_4h = pd.merge(df_4h, df_futoi_4h[['hour', 'fiz_buy_ratio']],
                          left_on='tradedate', right_on='hour', how='left')
        df_4h = df_4h.ffill()
        df_4h['fiz_buy_ratio'] = df_4h['fiz_buy_ratio'].fillna(50)
    
    if len(df_futoi_1h) > 0:
        df_1h['tradedate'] = pd.to_datetime(df_1h['begin'])
        df_futoi_1h['hour'] = pd.to_datetime(df_futoi_1h['hour'])
        df_1h = pd.merge(df_1h, df_futoi_1h[['hour', 'fiz_buy_ratio']],
                          left_on='tradedate', right_on='hour', how='left')
        df_1h = df_1h.ffill()
        df_1h['fiz_buy_ratio'] = df_1h['fiz_buy_ratio'].fillna(50)
    
    # D1
    if len(df_futoi_4h) > 0:
        df_futoi_4h['tradedate_only'] = df_futoi_4h['hour'].dt.date
        df_d1_futoi = df_futoi_4h.groupby('tradedate_only').agg({'fiz_buy_ratio': 'last'}).reset_index()
        df_d1['begin'] = pd.to_datetime(df_d1['begin'])
        df_d1['tradedate_only'] = df_d1['begin'].dt.date
        df_d1 = pd.merge(df_d1, df_d1_futoi, on='tradedate_only', how='left')
        df_d1 = df_d1.ffill()
        df_d1['fiz_buy_ratio'] = df_d1['fiz_buy_ratio'].fillna(50)
    
    # Сигналы
    sig_d1, score_d1, det_d1 = get_tf_signal(df_d1, '1D')
    sig_4h, score_4h, det_4h = get_tf_signal(df_4h, '4H')
    sig_1h, score_1h, det_1h = get_tf_signal(df_1h, '1H')
    
    print(f'  D1: fiz_buy={det_d1.get("fiz_buy", "N/A")}, delta={det_d1.get("fiz_delta", "N/A")}, signal={sig_d1}')
    print(f'  H4: fiz_buy={det_4h.get("fiz_buy", "N/A")}, delta={det_4h.get("fiz_delta", "N/A")}, signal={sig_4h}')
    print(f'  H1: fiz_buy={det_1h.get("fiz_buy", "N/A")}, delta={det_1h.get("fiz_delta", "N/A")}, signal={sig_1h}')
