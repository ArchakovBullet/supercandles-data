"""
Уровни поддержки/сопротивления для 1H:
Volume Profile (VA High/Low) + FutOI-уровни + Агрессивность рынка
"""

import pandas as pd
import numpy as np


def calculate_advanced_levels_1h(df_h1, df_1h, ticker):
    """
    Возвращает словарь с уровнями поддержки/сопротивления для 1H.
    
    Источники:
    1. Volume Profile — VA High, VA Low, POC
    2. FutOI 1H — уровни пересечения fiz_buy_ratio 60/40
    3. Агрессивность — high/low часов с агрессивностью >70
    """
    result = {
        'support': None,
        'resistance': None,
        'support_sources': [],
        'resistance_sources': [],
        'support_strength': 'слабый',
        'resistance_strength': 'слабый',
        'poc': None,
        'va_high': None,
        'va_low': None,
        'details': []
    }
    
    if df_h1 is None or len(df_h1) < 20:
        return result
    
    last_close = df_h1['close'].iloc[-1]
    atr = (df_h1['high'] - df_h1['low']).tail(14).mean()
    atr_tolerance = atr * 0.5
    
    # === 1. Volume Profile ===
    if 'typical_price' not in df_h1.columns:
        df_h1['typical_price'] = (df_h1['high'] + df_h1['low'] + df_h1['close']) / 3
    
    df_vp = df_h1.copy()
    df_vp['price_round'] = df_vp['typical_price'].round(1)
    vp = df_vp.groupby('price_round')['volume'].sum().reset_index()
    vp = vp.sort_values('volume', ascending=False)
    
    poc = vp.iloc[0]['price_round']
    total_vol = vp['volume'].sum()
    
    cum_vol = 0
    va_prices = []
    for _, row in vp.iterrows():
        cum_vol += row['volume']
        va_prices.append(row['price_round'])
        if cum_vol >= total_vol * 0.7:
            break
    
    va_high = max(va_prices) if va_prices else poc
    va_low = min(va_prices) if va_prices else poc
    
    result['poc'] = poc
    result['va_high'] = va_high
    result['va_low'] = va_low
    
    if va_high > last_close or True:  # Всегда показываем
        result['resistance'] = va_high
        result['resistance_sources'].append('VA High')
        result['details'].append(f"VA High (70% объёма): {va_high:.2f}")
    
    if va_low < last_close or True:  # Всегда показываем
        result['support'] = va_low
        result['support_sources'].append('VA Low')
        result['details'].append(f"VA Low (70% объёма): {va_low:.2f}")
    
    # === 2. FutOI 1H уровни ===
    if df_1h is not None and len(df_1h) >= 3:
        futoi_support = None
        futoi_resistance = None
        
        for i in range(3, len(df_1h)):
            curr = df_1h.iloc[i]
            prev = df_1h.iloc[i - 1]
            
            if prev['fiz_buy_ratio'] <= 60 and curr['fiz_buy_ratio'] > 60:
                if df_h1 is not None and len(df_h1) > 0:
                    try:
                        curr_hour = pd.to_datetime(curr['hour'])
                        h1_row = df_h1[pd.to_datetime(df_h1['begin']).dt.floor('1h') == curr_hour]
                        if len(h1_row) > 0:
                            futoi_support = h1_row.iloc[-1]['low']
                    except:
                        pass
            
            if prev['fiz_buy_ratio'] >= 40 and curr['fiz_buy_ratio'] < 40:
                if df_h1 is not None and len(df_h1) > 0:
                    try:
                        curr_hour = pd.to_datetime(curr['hour'])
                        h1_row = df_h1[pd.to_datetime(df_h1['begin']).dt.floor('1h') == curr_hour]
                        if len(h1_row) > 0:
                            futoi_resistance = h1_row.iloc[-1]['high']
                    except:
                        pass
        
        if futoi_support and futoi_support < last_close:
            if result['support'] and abs(futoi_support - result['support']) <= atr_tolerance:
                result['support'] = (futoi_support + result['support']) / 2
                result['support_sources'].append('FutOI (fiz>60%)')
                result['support_strength'] = 'сильный'
                result['details'].append(f"FutOI-поддержка: {futoi_support:.2f} — УСИЛЕНА")
            elif not result['support'] or futoi_support < result['support']:
                result['support'] = futoi_support
                result['support_sources'] = ['FutOI (fiz>60%)']
                result['details'].append(f"FutOI-поддержка: {futoi_support:.2f}")
        
        if futoi_resistance and futoi_resistance > last_close:
            if result['resistance'] and abs(futoi_resistance - result['resistance']) <= atr_tolerance:
                result['resistance'] = (futoi_resistance + result['resistance']) / 2
                result['resistance_sources'].append('FutOI (fiz<40%)')
                result['resistance_strength'] = 'сильный'
                result['details'].append(f"FutOI-сопротивление: {futoi_resistance:.2f} — УСИЛЕНО")
            elif not result['resistance'] or futoi_resistance > result['resistance']:
                result['resistance'] = futoi_resistance
                result['resistance_sources'] = ['FutOI (fiz<40%)']
                result['details'].append(f"FutOI-сопротивление: {futoi_resistance:.2f}")
    
    return result
