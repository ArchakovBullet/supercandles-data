#!/usr/bin/env python3
"""Тест yur_buy_ratio на разных ТФ (исправленные пути)."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

tickers = ['CE', 'MG', 'GD', 'SN', 'GZ', 'RI', 'SBERF', 'GAZPF']

# Правильные пути
FUTOI_PATHS = {
    'H4': DATA_ROOT / 'futoi_4h' / 'futoi_4h.parquet',
    'H1': DATA_ROOT / 'futoi_1h' / 'futoi_1h.parquet',
}

for tf, futoi_file in FUTOI_PATHS.items():
    if not futoi_file.exists():
        print(f'{tf}: нет {futoi_file}')
        continue
    
    futoi = pd.read_parquet(futoi_file)
    print(f'=== {tf} — yur_buy_ratio (n={len(futoi)}) ===')
    corrs = []
    for ticker in tickers:
        df = pd.read_parquet(CANDLES / f'{ticker}_{tf}.parquet')
        df_f = futoi[futoi['ticker'] == ticker].copy()
        if len(df_f) == 0 or 'yur_buy_ratio' not in df_f.columns:
            continue
        
        # Определяем колонку для merge
        if tf == 'H4':
            df['dt'] = pd.to_datetime(df['tradedate'].astype(str) + ' ' + df['block'].astype(str))
        else:  # H1
            df['dt'] = pd.to_datetime(df['begin'])
        
        df_f['dt'] = pd.to_datetime(df_f['hour'])
        
        # Merge
        df = pd.merge_asof(
            df.sort_values('dt'),
            df_f[['dt', 'yur_buy_ratio', 'fiz_buy_ratio']].sort_values('dt'),
            on='dt',
            direction='backward'
        )
        df = df.ffill()
        
        # Future move (через 4 свечи)
        df['future_move'] = df['close'].shift(-4) - df['close']
        df_valid = df.dropna(subset=['yur_buy_ratio', 'future_move'])
        if len(df_valid) > 10:
            corr = df_valid['yur_buy_ratio'].corr(df_valid['future_move'])
            corrs.append(corr)
            print(f'  {ticker}: {corr:+.4f}')
    if corrs:
        print(f'  Средняя yur: {sum(corrs)/len(corrs):+.4f}')
    print()
