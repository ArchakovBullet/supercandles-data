"""
Анализ акции относительно секторального индекса.
"""

import pandas as pd
import numpy as np


def analyze_vs_sector(df_stock, df_sector, window=20):
    """
    Сравнивает акцию с секторальным индексом.
    
    Возвращает:
    - relative_strength: отношение доходности акции к сектору (>1 = опережает)
    - sector_trend: тренд сектора (LONG/SHORT/NEUTRAL)
    - correlation: корреляция с сектором
    - signal: опережает/отстаёт/нейтрально
    """
    if df_stock is None or df_sector is None:
        return None
    
    if 'begin' in df_stock.columns:
        df_stock['date'] = pd.to_datetime(df_stock['begin'])
    if 'begin' in df_sector.columns:
        df_sector['date'] = pd.to_datetime(df_sector['begin'])
    
    merged = pd.merge(
        df_stock[['date', 'close']].rename(columns={'close': 'stock'}),
        df_sector[['date', 'close']].rename(columns={'close': 'sector'}),
        on='date', how='inner'
    ).dropna()
    
    if len(merged) < window:
        return None
    
    # Доходность за 20 дней
    stock_return = merged['stock'].iloc[-1] / merged['stock'].iloc[-window] - 1
    sector_return = merged['sector'].iloc[-1] / merged['sector'].iloc[-window] - 1
    
    relative_strength = (1 + stock_return) / (1 + sector_return) if sector_return != -1 else 1
    
    # Корреляция
    correlation = merged['stock'].pct_change().corr(merged['sector'].pct_change())
    
    # Тренд сектора
    merged['sma20'] = merged['sector'].rolling(20).mean()
    last = merged['sector'].iloc[-1]
    sma = merged['sma20'].iloc[-1]
    
    if last > sma * 1.02:
        sector_trend = 'LONG'
    elif last < sma * 0.98:
        sector_trend = 'SHORT'
    else:
        sector_trend = 'NEUTRAL'
    
    # Сигнал
    if relative_strength > 1.02:
        signal = '🟢 Опережает'
    elif relative_strength < 0.98:
        signal = '🔴 Отстаёт'
    else:
        signal = '⚪ Нейтрально'
    
    return {
        'relative_strength': round(relative_strength, 3),
        'sector_trend': sector_trend,
        'correlation': round(correlation, 3) if not np.isnan(correlation) else 0,
        'signal': signal,
        'stock_return': round(stock_return * 100, 1),
        'sector_return': round(sector_return * 100, 1),
    }
