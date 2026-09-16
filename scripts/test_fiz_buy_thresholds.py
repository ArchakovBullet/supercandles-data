#!/usr/bin/env python3
"""Проверить пороговые зависимости fiz_buy с будущим движением."""
import pandas as pd
import numpy as np
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

tickers = ['CE', 'MG', 'GD', 'SN', 'GZ', 'RI', 'SBERF', 'GAZPF']

print('=== Пороговый анализ fiz_buy ===')
print(f'{"ticker":<8} {"fiz>80":>10} {"fiz<20":>10} {"60<fiz<80":>10} {"40<fiz<60":>10} {"fiz<40":>10}')
print('-' * 70)

for ticker in tickers:
    df = pd.read_parquet(CANDLES / f'{ticker}_H1.parquet')
    futoi = pd.read_parquet(DATA_ROOT / 'futoi_1h' / 'futoi_1h.parquet')
    df_f = futoi[futoi['ticker'] == ticker].copy()
    if len(df_f) == 0:
        continue
    
    df['dt'] = pd.to_datetime(df['begin'])
    df_f['hour'] = pd.to_datetime(df_f['hour'])
    df = pd.merge(df, df_f[['hour', 'fiz_buy_ratio']], left_on='dt', right_on='hour', how='left')
    df = df.ffill()
    df['future_move'] = df['close'].shift(-4) - df['close']
    df = df.dropna(subset=['fiz_buy_ratio', 'future_move'])
    
    # Группы
    g1 = df[df['fiz_buy_ratio'] > 80]['future_move']
    g2 = df[df['fiz_buy_ratio'] < 20]['future_move']
    g3 = df[(df['fiz_buy_ratio'] > 60) & (df['fiz_buy_ratio'] <= 80)]['future_move']
    g4 = df[(df['fiz_buy_ratio'] > 40) & (df['fiz_buy_ratio'] <= 60)]['future_move']
    g5 = df[(df['fiz_buy_ratio'] > 20) & (df['fiz_buy_ratio'] <= 40)]['future_move']
    
    def avg(g):
        return f'{g.mean():+.2f}' if len(g) > 0 else '—'
    
    print(f'{ticker:<8} {avg(g1):>10} {avg(g2):>10} {avg(g3):>10} {avg(g4):>10} {avg(g5):>10}')

print()
print('Если fiz>80 → future_move < 0 → SHORT работает')
print('Если fiz<20 → future_move > 0 → LONG работает')
