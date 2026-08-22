#!/usr/bin/env python3
"""Агрегация H1 свечей фьючерсов в H4 за всю историю."""
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

CANDLES_DIR = Path('/root/finlab/data/candles')

# Фьючерсы из tickers_config.json
FUTURES = [
    "BR", "CE", "CNYRUBF", "ED", "EURRUBF", "FF", "GAZPF", "GD", "GLDRUBF",
    "IMOEXF", "MX", "OJ", "PD", "PT", "RI", "SBERF", "SI", "SV", "USDRUBF", "VI", "W4"
]

def aggregate_h1_to_h4(df_h1, ticker):
    """Агрегировать H1 в H4."""
    if df_h1.empty:
        return None
    
    df = df_h1.copy()
    df['begin'] = pd.to_datetime(df['begin'])
    df = df.sort_values('begin')
    
    # H4 блоки: 00:00-04:00, 04:00-08:00, 08:00-12:00, 12:00-16:00, 16:00-20:00, 20:00-00:00
    df['h4_block'] = df['begin'].dt.floor('4h')
    
    # Агрегируем
    df_h4 = df.groupby('h4_block').agg({
        'open': 'first',
        'close': 'last',
        'high': 'max',
        'low': 'min',
        'volume': 'sum',
        'begin': 'first',
        'end': 'last'
    }).reset_index(drop=True)
    
    # Добавляем колонки ticker и tradedate
    df_h4['ticker'] = ticker
    df_h4['tradedate'] = df_h4['begin'].dt.date.astype(str)
    
    # Переставляем колонки в правильном порядке
    df_h4 = df_h4[['ticker', 'tradedate', 'begin', 'open', 'high', 'low', 'close', 'volume', 'end']]
    
    return df_h4

# Обработка всех фьючерсов
for ticker in FUTURES:
    h1_file = CANDLES_DIR / f"{ticker}_H1.parquet"
    h4_file = CANDLES_DIR / f"{ticker}_H4.parquet"
    
    if not h1_file.exists():
        print(f"⚠️ {ticker}: нет H1 данных")
        continue
    
    try:
        df_h1 = pd.read_parquet(h1_file)
        df_h4 = aggregate_h1_to_h4(df_h1, ticker)
        
        if df_h4 is not None and len(df_h4) > 0:
            df_h4.to_parquet(h4_file, index=False)
            print(f"✅ {ticker}: H1({len(df_h1)}) → H4({len(df_h4)})")
        else:
            print(f"❌ {ticker}: ошибка агрегации")
    except Exception as e:
        print(f"❌ {ticker}: {e}")

print("\n✅ Агрегация завершена")
