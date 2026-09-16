#!/usr/bin/env python3
"""Пороговый анализ yur_buy на H4."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

tickers = ['CE', 'MG', 'GD', 'SN', 'GZ', 'RI', 'SBERF', 'GAZPF']
futoi = pd.read_parquet(DATA_ROOT / 'futoi_4h' / 'futoi_4h.parquet')

print('=== H4: yur_buy пороги → future_move ===')
print(f'{"ticker":<8} {"yur>60":>10} {"40<yur<60":>10} {"yur<40":>10}')
print('-' * 50)

for ticker in tickers:
    df = pd.read_parquet(CANDLES / f'{ticker}_H4.parquet')
    df_f = futoi[futoi['ticker'] == ticker].copy()
    if len(df_f) == 0:
        continue
    
    df['dt'] = pd.to_datetime(df['tradedate'].astype(str) + ' ' + df['block'].astype(str))
    df_f['dt'] = pd.to_datetime(df_f['hour'])
    
    df = pd.merge_asof(
        df.sort_values('dt'),
        df_f[['dt', 'yur_buy_ratio']].sort_values('dt'),
        on='dt',
        direction='backward'
    )
    df = df.ffill()
    df['future_move'] = df['close'].shift(-4) - df['close']
    df = df.dropna(subset=['yur_buy_ratio', 'future_move'])
    
    g1 = df[df['yur_buy_ratio'] > 60]['future_move']
    g2 = df[(df['yur_buy_ratio'] >= 40) & (df['yur_buy_ratio'] <= 60)]['future_move']
    g3 = df[df['yur_buy_ratio'] < 40]['future_move']
    
    def avg(g):
        return f'{g.mean():+.2f} (n={len(g)})' if len(g) > 0 else '—'
    
    print(f'{ticker:<8} {avg(g1):>15} {avg(g2):>15} {avg(g3):>15}')
