#!/usr/bin/env python3
"""Проверить корреляцию других факторов с будущим движением."""
import pandas as pd
import numpy as np
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')
CANDLES = DATA_ROOT / 'candles'

tickers = ['CE', 'MG', 'GD', 'SN', 'GZ', 'RI', 'SBERF', 'GAZPF']

# 1. Тренд (SMA20)
print('=== 1. Тренд (close vs SMA20) ===')
for ticker in tickers:
    df = pd.read_parquet(CANDLES / f'{ticker}_H1.parquet')
    df['sma20'] = df['close'].rolling(20).mean()
    df['trend'] = (df['close'] - df['sma20']) / df['sma20']
    df['future_move'] = df['close'].shift(-4) - df['close']
    df_valid = df.dropna(subset=['trend', 'future_move'])
    if len(df_valid) > 10:
        corr = df_valid['trend'].corr(df_valid['future_move'])
        print(f'{ticker}: corr(trend, future) = {corr:+.4f}')

# 2. Momentum (close - close[4])
print()
print('=== 2. Momentum (close - close[4]) ===')
for ticker in tickers:
    df = pd.read_parquet(CANDLES / f'{ticker}_H1.parquet')
    df['momentum'] = df['close'] - df['close'].shift(4)
    df['future_move'] = df['close'].shift(-4) - df['close']
    df_valid = df.dropna(subset=['momentum', 'future_move'])
    if len(df_valid) > 10:
        corr = df_valid['momentum'].corr(df_valid['future_move'])
        print(f'{ticker}: corr(momentum, future) = {corr:+.4f}')

# 3. Волатильность (std close[20])
print()
print('=== 3. Волатильность (std close[20]) ===')
for ticker in tickers:
    df = pd.read_parquet(CANDLES / f'{ticker}_H1.parquet')
    df['vol'] = df['close'].rolling(20).std()
    df['future_move'] = df['close'].shift(-4) - df['close']
    df_valid = df.dropna(subset=['vol', 'future_move'])
    if len(df_valid) > 10:
        corr = df_valid['vol'].corr(df_valid['future_move'])
        print(f'{ticker}: corr(vol, future) = {corr:+.4f}')

# 4. Объём
print()
print('=== 4. Объём (volume) ===')
for ticker in tickers:
    df = pd.read_parquet(CANDLES / f'{ticker}_H1.parquet')
    df['vol_ma'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma']
    df['future_move'] = df['close'].shift(-4) - df['close']
    df_valid = df.dropna(subset=['vol_ratio', 'future_move'])
    if len(df_valid) > 10:
        corr = df_valid['vol_ratio'].corr(df_valid['future_move'])
        print(f'{ticker}: corr(vol_ratio, future) = {corr:+.4f}')
