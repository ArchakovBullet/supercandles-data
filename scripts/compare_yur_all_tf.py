#!/usr/bin/env python3
"""Сопоставить yur_buy на всех ТФ."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

tickers = ['CE', 'MG', 'GD', 'SN', 'GZ', 'RI', 'SBERF', 'GAZPF']

results = {}

# H4
futoi_h4 = pd.read_parquet(DATA_ROOT / 'futoi_4h' / 'futoi_4h.parquet')
# H1
futoi_h1 = pd.read_parquet(DATA_ROOT / 'futoi_1h' / 'futoi_1h.parquet')

for tf, futoi in [('H4', futoi_h4), ('H1', futoi_h1)]:
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
            df_f[['dt', 'yur_buy_ratio']].sort_values('dt'),
            on='dt',
            direction='backward'
        )
        df = df.ffill()
        
        # Проверяем разные горизонты
        best_corr = 0
        best_n = 0
        for n in [1, 2, 4, 8, 12, 24]:
            df['future'] = df['close'].shift(-n) - df['close']
            valid = df.dropna(subset=['yur_buy_ratio', 'future'])
            if len(valid) > 20:
                corr = valid['yur_buy_ratio'].corr(valid['future'])
                if abs(corr) > abs(best_corr):
                    best_corr = corr
                    best_n = n
        
        results.setdefault(ticker, {})[tf] = (best_corr, best_n)

print('=== Лучшая корреляция yur_buy по ТФ ===')
print(f'{"ticker":<8} {"H4 corr":>10} {"n":>4} {"H1 corr":>10} {"n":>4}')
print('-' * 45)
for ticker in tickers:
    if ticker in results:
        h4 = results[ticker].get('H4', (None, None))
        h1 = results[ticker].get('H1', (None, None))
        def fmt(x):
            return f'{x[0]:+.4f}' if x[0] is not None else '—'
        def fmtn(x):
            return f'{x[1]}' if x[1] is not None else '—'
        print(f'{ticker:<8} {fmt(h4):>10} {fmtn(h4):>4} {fmt(h1):>10} {fmtn(h1):>4}')
