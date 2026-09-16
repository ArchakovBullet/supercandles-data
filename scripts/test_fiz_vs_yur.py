#!/usr/bin/env python3
"""Сравнить fiz_buy и yur_buy на H4 и H1."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

tickers = ['CE', 'MG', 'GD', 'SN', 'GZ', 'RI', 'SBERF', 'GAZPF']

for tf, futoi_path in [('H4', 'futoi_4h'), ('H1', 'futoi_1h')]:
    futoi = pd.read_parquet(DATA_ROOT / futoi_path / f'{futoi_path}.parquet')
    print(f'=== {tf} ===')
    
    fiz_corrs = []
    yur_corrs = []
    
    for ticker in tickers:
        df = pd.read_parquet(CANDLES / f'{ticker}_{tf}.parquet')
        df_f = futoi[futoi['ticker'] == ticker].copy()
        if len(df_f) == 0:
            continue
        
        if tf == 'H4':
            df['dt'] = pd.to_datetime(df['tradedate'].astype(str) + ' ' + df['block'].astype(str))
        else:
            df['dt'] = pd.to_datetime(df['begin'])
        
        df_f['dt'] = pd.to_datetime(df_f['hour'])
        
        df = pd.merge_asof(
            df.sort_values('dt'),
            df_f[['dt', 'yur_buy_ratio', 'fiz_buy_ratio']].sort_values('dt'),
            on='dt',
            direction='backward'
        )
        df = df.ffill()
        
        df['future_move'] = df['close'].shift(-4) - df['close']
        df_valid = df.dropna(subset=['yur_buy_ratio', 'fiz_buy_ratio', 'future_move'])
        
        if len(df_valid) > 10:
            fiz_corr = df_valid['fiz_buy_ratio'].corr(df_valid['future_move'])
            yur_corr = df_valid['yur_buy_ratio'].corr(df_valid['future_move'])
            fiz_corrs.append(fiz_corr)
            yur_corrs.append(yur_corr)
            print(f'  {ticker}: fiz={fiz_corr:+.4f}, yur={yur_corr:+.4f}')
    
    if fiz_corrs:
        print(f'  Средняя fiz: {sum(fiz_corrs)/len(fiz_corrs):+.4f}')
        print(f'  Средняя yur: {sum(yur_corrs)/len(yur_corrs):+.4f}')
    print()
