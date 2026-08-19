#!/usr/bin/env python3
"""Агрегация H1 свечей в H4 для акций."""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Конфигурация
CANDLES_DIR = Path('/root/finlab/data/candles')

# Акции из tickers_config.json
STOCKS = [
    "AFLT", "SBER", "GAZP", "GMKN", "LKOH", "HYDR", 
    "IRAO", "PLZL", "ROSN", "TATN", "VTBR", "AFKS", 
    "T", "YDEX", "RUAL"
]

def aggregate_h1_to_h4(df_h1):
    """Агрегировать H1 данные в H4."""
    if df_h1.empty:
        return None
    
    # Убедимся, что begin в datetime формате
    df = df_h1.copy()
    df['begin'] = pd.to_datetime(df['begin'])
    df = df.sort_values('begin')
    
    # Создаём метку H4 блока
    # H4 блоки: 00:00-04:00, 04:00-08:00, 08:00-12:00, 12:00-16:00, 16:00-20:00, 20:00-00:00
    df['h4_block'] = df['begin'].dt.floor('4h')
    
    # Агрегируем
    df_h4 = df.groupby('h4_block').agg({
        'open': 'first',
        'close': 'last',
        'high': 'max',
        'low': 'min',
        'value': 'sum',
        'volume': 'sum',
        'begin': 'first',
        'end': 'last'
    }).reset_index(drop=True)
    
    return df_h4

# Обработка всех акций
for ticker in STOCKS:
    h1_file = CANDLES_DIR / f"{ticker}_H1.parquet"
    h4_file = CANDLES_DIR / f"{ticker}_H4.parquet"
    
    if not h1_file.exists():
        print(f"⚠️ {ticker}: нет H1 данных")
        continue
    
    if h4_file.exists():
        print(f"✅ {ticker}: H4 уже существует ({len(pd.read_parquet(h4_file))} строк)")
        continue
    
    try:
        df_h1 = pd.read_parquet(h1_file)
        df_h4 = aggregate_h1_to_h4(df_h1)
        
        if df_h4 is not None and len(df_h4) > 0:
            df_h4.to_parquet(h4_file, index=False)
            print(f"✅ {ticker}: H1→H4 агрегировано ({len(df_h1)}→{len(df_h4)} строк)")
        else:
            print(f"❌ {ticker}: ошибка агрегации")
    
    except Exception as e:
        print(f"❌ {ticker}: {e}")

print("\n✅ Агрегация завершена")
