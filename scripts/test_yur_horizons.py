#!/usr/bin/env python3
"""Проверить корреляцию yur_buy с разными горизонтами (H4)."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

tickers = ['CE', 'MG', 'GD', 'SN', 'GZ', 'RI', 'SBERF', 'GAZPF']

futoi = pd.read_parquet(DATA_ROOT / 'futoi_4h' / 'futoi_4h.parquet')

print('=== H4: yur_buy vs future_move (разные горизонты) ===')
print(f'{"ticker":<8} {"+1 свеча":>10} {"+2 свечи":>10} {"+4 свечи":>10} {"+8 свечей":>10}')
print('-' * 60)

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
    
    def corr_at(n):
        df['future'] = df['close'].shift(-n) - df['close']
        valid = df.dropna(subset=['yur_buy_ratio', 'future'])
        if len(valid) > 10:
            return valid['yur_buy_ratio'].corr(valid['future'])
        return None
    
    c1 = corr_at(1)
    c2 = corr_at(2)
    c4 = corr_at(4)
    c8 = corr_at(8)
    
    def fmt(c):
        return f'{c:+.4f}' if c is not None else '—'
    
    print(f'{ticker:<8} {fmt(c1):>10} {fmt(c2):>10} {fmt(c4):>10} {fmt(c8):>10}')
