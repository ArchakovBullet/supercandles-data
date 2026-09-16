#!/usr/bin/env python3
"""Тест yur_buy на D1 (агрегация из H4)."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

tickers = ['CE', 'MG', 'GD', 'SN', 'GZ', 'RI', 'SBERF', 'GAZPF']
futoi = pd.read_parquet(DATA_ROOT / 'futoi_4h' / 'futoi_4h.parquet')

# Агрегируем FutOI до D1
futoi['hour'] = pd.to_datetime(futoi['hour'])
futoi['date'] = futoi['hour'].dt.floor('D')
futoi_d1 = futoi.groupby(['ticker', 'date']).agg({
    'yur_buy_ratio': 'last',
    'fiz_buy_ratio': 'last'
}).reset_index()
futoi_d1['dt'] = pd.to_datetime(futoi_d1['date']).astype('datetime64[ns]')

print('=== D1: yur_buy vs future_move ===')
print(f'{"ticker":<8} {"n=1":>10} {"n=2":>10} {"n=3":>10} {"n=5":>10}')
print('-' * 50)

for ticker in tickers:
    df = pd.read_parquet(CANDLES / f'{ticker}_D1.parquet')
    df_f = futoi_d1[futoi_d1['ticker'] == ticker].copy()
    if len(df_f) == 0:
        continue
    
    # Определяем колонку для даты в свечах D1
    if 'begin' in df.columns:
        df['dt'] = pd.to_datetime(df['begin']).astype('datetime64[ns]').dt.floor('D')
    elif 'tradedate' in df.columns:
        df['dt'] = pd.to_datetime(df['tradedate']).astype('datetime64[ns]').dt.floor('D')
    else:
        print(f'{ticker}: нет колонки с датой')
        continue
    
    # Убираем дубликаты по dt
    df = df.drop_duplicates(subset=['dt']).sort_values('dt')
    df_f = df_f.drop_duplicates(subset=['dt']).sort_values('dt')
    
    df = pd.merge_asof(
        df,
        df_f[['dt', 'yur_buy_ratio']],
        on='dt',
        direction='backward'
    )
    df = df.ffill()
    
    corrs = []
    for n in [1, 2, 3, 5]:
        df['future'] = df['close'].shift(-n) - df['close']
        valid = df.dropna(subset=['yur_buy_ratio', 'future'])
        if len(valid) > 10:
            corrs.append(valid['yur_buy_ratio'].corr(valid['future']))
        else:
            corrs.append(None)
    
    def fmt(c):
        return f'{c:+.4f}' if c is not None else '—'
    
    print(f'{ticker:<8} ' + ' '.join(f'{fmt(c):>10}' for c in corrs))
