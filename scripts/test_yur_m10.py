#!/usr/bin/env python3
"""Тест yur_buy на M10. Нужны M10-агрегаты FutOI."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

tickers = ['CE', 'MG', 'GD', 'SN', 'GZ', 'RI', 'SBERF', 'GAZPF']

# Проверяем наличие M10-агрегатов FutOI
m10_futoi_paths = [
    DATA_ROOT / 'futoi_m10' / 'futoi_m10.parquet',
    DATA_ROOT / 'futoi' / 'futoi_m10.parquet',
]

m10_futoi = None
for p in m10_futoi_paths:
    if p.exists():
        m10_futoi = pd.read_parquet(p)
        print(f'✅ Найден: {p}, {len(m10_futoi)} строк')
        break

if m10_futoi is None:
    print('❌ M10-агрегат FutOI не найден')
    print()
    print('Проверяем, что есть в data/:')
    for d in DATA_ROOT.iterdir():
        if d.is_dir() and 'futoi' in d.name.lower():
            print(f'  {d.name}/')
            for f in d.glob('*.parquet'):
                print(f'    {f.name}')
    exit(0)

# Если есть — тестируем
print()
print('=== M10: yur_buy vs future_move ===')
print(f'{"ticker":<8} {"+1":>10} {"+2":>10} {"+4":>10} {"+8":>10}')
print('-' * 50)

for ticker in tickers:
    df = pd.read_parquet(CANDLES / f'{ticker}_M10.parquet')
    df_f = m10_futoi[m10_futoi['ticker'] == ticker].copy()
    if len(df_f) == 0:
        continue
    
    df['dt'] = pd.to_datetime(df['begin'])
    
    # Определяем колонку в M10 futoi
    if 'hour' in df_f.columns:
        df_f['dt'] = pd.to_datetime(df_f['hour'])
    elif 'block' in df_f.columns:
        df_f['dt'] = pd.to_datetime(df_f['block'])
    
    df = pd.merge_asof(
        df.sort_values('dt'),
        df_f[['dt', 'yur_buy_ratio', 'fiz_buy_ratio']].sort_values('dt'),
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
    
    def fmt(c):
        return f'{c:+.4f}' if c is not None else '—'
    
    print(f'{ticker:<8} {fmt(corr_at(1)):>10} {fmt(corr_at(2)):>10} {fmt(corr_at(4)):>10} {fmt(corr_at(8)):>10}')
