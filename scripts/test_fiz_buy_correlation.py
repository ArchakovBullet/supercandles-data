#!/usr/bin/env python3
"""Проверить корреляцию fiz_buy с будущим движением цены."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

results = []

for ticker in ['CE', 'MG', 'GD', 'SN', 'GZ', 'RI', 'SBERF', 'GAZPF']:
    # Загружаем H1 (там merge работает)
    df_h1 = pd.read_parquet(CANDLES / f'{ticker}_H1.parquet')
    futoi_1h = pd.read_parquet(DATA_ROOT / 'futoi_1h' / 'futoi_1h.parquet')
    
    df_futoi = futoi_1h[futoi_1h['ticker'] == ticker].copy()
    if len(df_futoi) == 0:
        continue
    
    # Merge
    df_h1['dt'] = pd.to_datetime(df_h1['begin'])
    df_futoi['hour'] = pd.to_datetime(df_futoi['hour'])
    df_h1 = pd.merge(df_h1, df_futoi[['hour', 'fiz_buy_ratio']],
                     left_on='dt', right_on='hour', how='left')
    df_h1 = df_h1.ffill()
    
    # Будущее движение (через 4 часа)
    df_h1['future_close'] = df_h1['close'].shift(-4)
    df_h1['future_move'] = df_h1['future_close'] - df_h1['close']
    
    # Корреляция fiz_buy с future_move
    df_valid = df_h1.dropna(subset=['fiz_buy_ratio', 'future_move'])
    if len(df_valid) > 10:
        corr = df_valid['fiz_buy_ratio'].corr(df_valid['future_move'])
        results.append((ticker, corr, len(df_valid)))
        print(f'{ticker}: correlation = {corr:+.4f}, n = {len(df_valid)}')

print()
if results:
    avg_corr = sum(r[1] for r in results) / len(results)
    print(f'Средняя корреляция: {avg_corr:+.4f}')
    if avg_corr > 0.05:
        print('✅ fiz_buy > 50 → цена растёт (тренд)')
    elif avg_corr < -0.05:
        print('⚠️ fiz_buy > 50 → цена падает (контр-тренд)')
    else:
        print('❌ Корреляция отсутствует')
