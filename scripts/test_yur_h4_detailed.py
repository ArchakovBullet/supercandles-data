#!/usr/bin/env python3
"""Детальный тест yur_buy на H4."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

tickers = ['CE', 'MG', 'GD', 'SN', 'GZ', 'RI', 'SBERF', 'GAZPF']
futoi = pd.read_parquet(DATA_ROOT / 'futoi_4h' / 'futoi_4h.parquet')

print('=== H4: yur_buy с разными горизонтами (n) ===')
print(f'{"ticker":<8} {"n=1":>10} {"n=2":>10} {"n=3":>10} {"n=4":>10} {"n=6":>10} {"n=8":>10}')
print('-' * 75)

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
    
    corrs = []
    for n in [1, 2, 3, 4, 6, 8]:
        df['future'] = df['close'].shift(-n) - df['close']
        valid = df.dropna(subset=['yur_buy_ratio', 'future'])
        if len(valid) > 10:
            corrs.append(valid['yur_buy_ratio'].corr(valid['future']))
        else:
            corrs.append(None)
    
    def fmt(c):
        return f'{c:+.4f}' if c is not None else '—'
    
    print(f'{ticker:<8} ' + ' '.join(f'{fmt(c):>10}' for c in corrs))
