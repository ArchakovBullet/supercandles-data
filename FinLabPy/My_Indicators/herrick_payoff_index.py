"""
Индекс выплат Херрика (Herrick Payoff Index, HPI).
Объединяет Цену + Объём + Открытый интерес для фьючерсов.
"""

import pandas as pd
import numpy as np


def calculate_hpi(df_d1, df_oi=None, period=14):
    """
    Рассчитывает индекс выплат Херрика.
    
    Параметры:
    - df_d1: D1-свечи (open, high, low, close, volume)
    - df_oi: данные открытого интереса (open_interest)
    - period: период сглаживания
    
    Возвращает:
    - hpi: значения HPI
    - hpi_signal: LONG/SHORT/NEUTRAL
    - divergence: True если есть дивергенция с ценой
    """
    if df_d1 is None or len(df_d1) < period + 1:
        return None
    
    df = df_d1.copy()
    
    # Средняя цена
    df['avg_price'] = (df['high'] + df['low'] + df['close']) / 3
    df['avg_price_prev'] = df['avg_price'].shift(1)
    
    # Изменение средней цены
    df['price_change'] = df['avg_price'] - df['avg_price_prev']
    
    # Объём
    df['volume'] = df['volume'].fillna(0)
    
    # Открытый интерес
    if df_oi is not None and 'oi_close' in df_oi.columns:
        df['oi'] = df_oi['oi_close']
    elif 'oi' in df.columns:
        df['oi'] = df['oi']
    else:
        # Без ОИ используем только цену и объём
        df['oi'] = 1
        df['oi_change'] = 0
        df['oi_factor'] = 1
        hpi_raw = df['price_change'] * df['volume']
        hpi = hpi_raw.rolling(period).mean()
        
        last_hpi = hpi.iloc[-1]
        if last_hpi > 0:
            signal = 'LONG'
        elif last_hpi < 0:
            signal = 'SHORT'
        else:
            signal = 'NEUTRAL'
        
        return {
            'hpi': round(last_hpi, 2),
            'hpi_signal': signal,
            'divergence': False,
            'hpi_series': hpi,
            'note': 'Без учёта ОИ (данные недоступны)'
        }
    
    # Изменение ОИ
    df['oi_prev'] = df['oi'].shift(1)
    df['oi_change'] = df['oi'] - df['oi_prev']
    
    # Фактор ОИ: 1 + (ΔOI / |ΔOI|)
    df['oi_factor'] = 1 + np.where(df['oi_change'].abs() > 0, 
                                     df['oi_change'] / df['oi_change'].abs(), 
                                     0)
    
    # HPI raw = изменение цены × объём × фактор ОИ
    df['hpi_raw'] = df['price_change'] * df['volume'] * df['oi_factor']
    
    # Сглаживание
    df['hpi'] = df['hpi_raw'].rolling(period).mean()
    
    last_hpi = df['hpi'].iloc[-1]
    prev_hpi = df['hpi'].iloc[-2] if len(df) >= 2 else last_hpi
    
    # Сигнал
    if last_hpi > 0 and last_hpi > prev_hpi:
        signal = 'LONG'
    elif last_hpi < 0 and last_hpi < prev_hpi:
        signal = 'SHORT'
    else:
        signal = 'NEUTRAL'
    
    # Дивергенция: цена растёт, HPI падает (или наоборот)
    last_close = df['close'].iloc[-1]
    prev_close = df['close'].iloc[-5] if len(df) >= 5 else df['close'].iloc[0]
    price_up = last_close > prev_close
    hpi_up = last_hpi > df['hpi'].iloc[-5] if len(df) >= 5 else last_hpi > 0
    
    divergence = (price_up and not hpi_up) or (not price_up and hpi_up)
    
    return {
        'hpi': round(last_hpi, 2),
        'hpi_signal': signal,
        'divergence': divergence,
        'hpi_series': df['hpi'],
        'price_change': round(df['price_change'].iloc[-1], 4),
        'volume': int(df['volume'].iloc[-1]),
        'oi_change': int(df['oi_change'].iloc[-1]) if 'oi_change' in df.columns and not pd.isna(df['oi_change'].iloc[-1]) else 0,
    }
