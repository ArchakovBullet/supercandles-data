#!/usr/bin/env python3
"""Точный пороговый анализ yur_buy на D1."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

tickers = ['RI', 'SBERF', 'GAZPF', 'GZ', 'SN', 'CE', 'MG', 'GD']

futoi = pd.read_parquet(DATA_ROOT / 'futoi_4h' / 'futoi_4h.parquet')
futoi['hour'] = pd.to_datetime(futoi['hour'])
futoi['date'] = futoi['hour'].dt.floor('D')
futoi_d1 = futoi.groupby(['ticker', 'date']).agg({
    'yur_buy_ratio': 'last'
}).reset_index()
futoi_d1['dt'] = pd.to_datetime(futoi_d1['date']).astype('datetime64[ns]')

# Квартили
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
    
    print(f'=== {ticker} (n={len(df)}) ===')
    print(f'  Квантили yur_buy:')
    for q in [0.25, 0.5, 0.75]:
        print(f'    {q*100:.0f}%: {df["yur_buy_ratio"].quantile(q):.1f}')
    
    # Группы по квартилям
    q25 = df['yur_buy_ratio'].quantile(0.25)
    q75 = df['yur_buy_ratio'].quantile(0.75)
    
    g_low = df[df['yur_buy_ratio'] <= q25]['future']
    g_high = df[df['yur_buy_ratio'] >= q75]['future']
    
    print(f'  yur <= {q25:.1f} (низкий): future_mean = {g_low.mean():+.1f} (n={len(g_low)})')
    print(f'  yur >= {q75:.1f} (высокий): future_mean = {g_high.mean():+.1f} (n={len(g_high)})')
    print()
