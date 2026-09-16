#!/usr/bin/env python3
"""Собрать статистику yur_buy для всех тикеров (D1)."""
import pandas as pd
import json
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

# Все тикеры из futoi_4h
futoi = pd.read_parquet(DATA_ROOT / 'futoi_4h' / 'futoi_4h.parquet')
tickers = sorted(futoi['ticker'].unique())

futoi['hour'] = pd.to_datetime(futoi['hour'])
futoi['date'] = futoi['hour'].dt.floor('D')
futoi_d1 = futoi.groupby(['ticker', 'date']).agg({
    'yur_buy_ratio': 'last'
}).reset_index()
futoi_d1['dt'] = pd.to_datetime(futoi_d1['date']).astype('datetime64[ns]')

stats = {}
for ticker in tickers:
    df_f = futoi_d1[futoi_d1['ticker'] == ticker]
    if len(df_f) < 10:
        continue
    
    yur = df_f['yur_buy_ratio'].dropna()
    if len(yur) < 10:
        continue
    
    stats[ticker] = {
        'median': round(float(yur.median()), 2),
        'std': round(float(yur.std()), 2),
        'q25': round(float(yur.quantile(0.25)), 2),
        'q75': round(float(yur.quantile(0.75)), 2),
        'n': int(len(yur))
    }

with open('/root/finlab/robots/yur_stats.json', 'w') as f:
    json.dump(stats, f, indent=2, ensure_ascii=False)

print(f'✅ Сохранено {len(stats)} тикеров в yur_stats.json')
print()
print(f'{"ticker":<8} {"median":>8} {"std":>8} {"q25":>8} {"q75":>8} {"n":>5}')
print('-' * 50)
for t in ['RI', 'SBERF', 'GAZPF', 'GZ', 'SN', 'CE', 'MG', 'GD']:
    if t in stats:
        s = stats[t]
        print(f'{t:<8} {s["median"]:>8.1f} {s["std"]:>8.1f} {s["q25"]:>8.1f} {s["q75"]:>8.1f} {s["n"]:>5}')
