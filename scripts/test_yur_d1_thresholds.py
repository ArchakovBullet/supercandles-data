#!/usr/bin/env python3
"""Пороговый анализ yur_buy на D1."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

tickers = ['CE', 'MG', 'GD', 'SN', 'GZ', 'RI', 'SBERF', 'GAZPF']
futoi = pd.read_parquet(DATA_ROOT / 'futoi_4h' / 'futoi_4h.parquet')

futoi['hour'] = pd.to_datetime(futoi['hour'])
futoi['date'] = futoi['hour'].dt.floor('D')
futoi_d1 = futoi.groupby(['ticker', 'date']).agg({
    'yur_buy_ratio': 'last'
}).reset_index()
futoi_d1['dt'] = pd.to_datetime(futoi_d1['date']).astype('datetime64[ns]')

print('=== D1: yur_buy пороги → future_move (n=3) ===')
print(f'{"ticker":<8} {"yur>50":>15} {"19<yur<50":>15} {"yur<19":>15}')
print('-' * 60)

for ticker in tickers:
    df = pd.read_parquet(CANDLES / f'{ticker}_D1.parquet')
    df_f = futoi_d1[futoi_d1['ticker'] == ticker].copy()
    if len(df_f) == 0:
        continue
    
    if 'begin' in df.columns:
        df['dt'] = pd.to_datetime(df['begin']).astype('datetime64[ns]').dt.floor('D')
    elif 'tradedate' in df.columns:
        df['dt'] = pd.to_datetime(df['tradedate']).astype('datetime64[ns]').dt.floor('D')
    
    df = df.drop_duplicates(subset=['dt']).sort_values('dt')
    df_f = df_f.drop_duplicates(subset=['dt']).sort_values('dt')
    
    df = pd.merge_asof(df, df_f[['dt', 'yur_buy_ratio']], on='dt', direction='backward')
    df = df.ffill()
    df['future'] = df['close'].shift(-3) - df['close']
    df = df.dropna(subset=['yur_buy_ratio', 'future'])
    
    g1 = df[df['yur_buy_ratio'] > 50]['future']
    g2 = df[(df['yur_buy_ratio'] >= 19) & (df['yur_buy_ratio'] <= 50)]['future']
    g3 = df[df['yur_buy_ratio'] < 19]['future']
    
    def avg(g):
        return f'{g.mean():+.1f} (n={len(g)})' if len(g) > 0 else '—'
    
    print(f'{ticker:<8} {avg(g1):>15} {avg(g2):>15} {avg(g3):>15}')
