"""
Улучшенные уровни поддержки/сопротивления:
Volume Profile (VA High/Low) + FutOI-уровни + HI2-уровни
"""

import pandas as pd
import numpy as np


def calculate_advanced_levels(df_d1, df_analytics, hi2_data, ticker, atr=None):
    """
    Возвращает словарь с уровнями поддержки/сопротивления.
    
    Источники:
    1. Volume Profile — VA High (сопр.), VA Low (подд.), POC
    2. FutOI — уровни пересечения fiz_buy_ratio 60/40
    3. HI2 — high/low дней с аномальной концентрацией (>150)
    
    Уровни усиливаются, если совпадают из разных источников (в пределах ATR).
    """
    result = {
        'support': None,       # Основная поддержка
        'resistance': None,    # Основное сопротивление
        'support_sources': [], # Из каких источников поддержка
        'resistance_sources': [],# Из каких источников сопротивление
        'support_strength': 'слабый',
        'resistance_strength': 'слабый',
        'poc': None,
        'va_high': None,
        'va_low': None,
        'details': []
    }
    
    if df_d1 is None or len(df_d1) < 20:
        return result
    
    last_close = df_d1['close'].iloc[-1]
    if atr is None:
        atr = (df_d1['high'] - df_d1['low']).tail(14).mean()
    
    atr_tolerance = atr * 0.5  # Допуск совпадения уровней
    
    # === 1. Volume Profile уровни ===
    if 'typical_price' not in df_d1.columns:
        df_d1['typical_price'] = (df_d1['high'] + df_d1['low'] + df_d1['close']) / 3
    
    # VA = 70% объёма вокруг POC
    df_vp = df_d1.copy()
    df_vp['price_round'] = df_vp['typical_price'].round(1)
    vp = df_vp.groupby('price_round')['volume'].sum().reset_index()
    vp = vp.sort_values('volume', ascending=False)
    
    poc = vp.iloc[0]['price_round']
    total_vol = vp['volume'].sum()
    
    # VA High/Low (70% объёма)
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
    
    # === 2. FutOI уровни (пересечения fiz_buy_ratio) ===
    if df_analytics is not None and len(df_analytics) >= 3:
        futoi_support = None
        futoi_resistance = None
        
        for i in range(3, len(df_analytics)):
            curr = df_analytics.iloc[i]
            prev = df_analytics.iloc[i - 1]
            
            # LONG-уровень: fiz_buy_ratio пересекает 60% вверх
            if prev['fiz_buy_ratio'] <= 60 and curr['fiz_buy_ratio'] > 60:
                if df_d1 is not None and len(df_d1) > 0:
                    try:
                        curr_date = pd.to_datetime(curr['datetime']).date()
                        d1_row = df_d1[pd.to_datetime(df_d1['begin']).dt.date == curr_date]
                        if len(d1_row) > 0:
                            futoi_support = d1_row.iloc[-1]['low']
                    except:
                        pass
            
            # SHORT-уровень: fiz_buy_ratio пересекает 40% вниз
            if prev['fiz_buy_ratio'] >= 40 and curr['fiz_buy_ratio'] < 40:
                if df_d1 is not None and len(df_d1) > 0:
                    try:
                        curr_date = pd.to_datetime(curr['datetime']).date()
                        d1_row = df_d1[pd.to_datetime(df_d1['begin']).dt.date == curr_date]
                        if len(d1_row) > 0:
                            futoi_resistance = d1_row.iloc[-1]['high']
                    except:
                        pass
        
        if futoi_support and futoi_support < last_close:
            # Проверяем совпадение с VA
            if result['support'] and abs(futoi_support - result['support']) <= atr_tolerance:
                result['support'] = (futoi_support + result['support']) / 2
                result['support_sources'].append('FutOI (fiz>60%)')
                result['support_strength'] = 'сильный'
                result['details'].append(f"FutOI-поддержка (fiz>60%): {futoi_support:.2f} — УСИЛЕНА (совпадает с VA)")
            elif not result['support'] or futoi_support < result['support']:
                result['support'] = futoi_support
                result['support_sources'] = ['FutOI (fiz>60%)']
                result['details'].append(f"FutOI-поддержка (fiz>60%): {futoi_support:.2f}")
        
        if futoi_resistance and futoi_resistance > last_close:
            if result['resistance'] and abs(futoi_resistance - result['resistance']) <= atr_tolerance:
                result['resistance'] = (futoi_resistance + result['resistance']) / 2
                result['resistance_sources'].append('FutOI (fiz<40%)')
                result['resistance_strength'] = 'сильный'
                result['details'].append(f"FutOI-сопротивление (fiz<40%): {futoi_resistance:.2f} — УСИЛЕНО (совпадает с VA)")
            elif not result['resistance'] or futoi_resistance > result['resistance']:
                result['resistance'] = futoi_resistance
                result['resistance_sources'] = ['FutOI (fiz<40%)']
                result['details'].append(f"FutOI-сопротивление (fiz<40%): {futoi_resistance:.2f}")
    
    # === 3. HI2 уровни (дни с аномальной концентрацией) ===
    if hi2_data is not None and len(hi2_data) > 0:
        hi2_ticker = hi2_data[hi2_data['ticker'] == ticker]
        if len(hi2_ticker) > 0:
            hi2_agressive = hi2_ticker[hi2_ticker['metric'] == 'hhi_agressive']
            hi2_high = hi2_agressive[hi2_agressive['value'] > 150]
            
            if len(hi2_high) > 0:
                hi2_dates = hi2_high['tradedate'].unique()
                
                hi2_levels_high = []
                hi2_levels_low = []
                
                for date in hi2_dates:
                    try:
                        d1_row = df_d1[pd.to_datetime(df_d1['begin']).dt.date == pd.to_datetime(date).date()]
                        if len(d1_row) > 0:
                            hi2_levels_high.append(d1_row.iloc[-1]['high'])
                            hi2_levels_low.append(d1_row.iloc[-1]['low'])
                    except:
                        pass
                
                if hi2_levels_high:
                    hi2_resist = max(hi2_levels_high)
                    hi2_support = min(hi2_levels_low)
                    
                    if hi2_resist > last_close:
                        if result['resistance'] and abs(hi2_resist - result['resistance']) <= atr_tolerance:
                            result['resistance'] = (hi2_resist + result['resistance']) / 2
                            result['resistance_sources'].append('HI2 (>150)')
                            result['resistance_strength'] = 'сильный'
                            result['details'].append(f"HI2-сопротивление (конц. >150): {hi2_resist:.2f} — УСИЛЕНО")
                        elif not result['resistance'] or hi2_resist > result['resistance']:
                            result['resistance'] = hi2_resist
                            result['resistance_sources'].append('HI2 (>150)')
                            result['details'].append(f"HI2-сопротивление (конц. >150): {hi2_resist:.2f}")
                    
                    if hi2_support < last_close:
                        if result['support'] and abs(hi2_support - result['support']) <= atr_tolerance:
                            result['support'] = (hi2_support + result['support']) / 2
                            result['support_sources'].append('HI2 (>150)')
                            result['support_strength'] = 'сильный'
                            result['details'].append(f"HI2-поддержка (конц. >150): {hi2_support:.2f} — УСИЛЕНА")
                        elif not result['support'] or hi2_support < result['support']:
                            result['support'] = hi2_support
                            result['support_sources'].append('HI2 (>150)')
                            result['details'].append(f"HI2-поддержка (конц. >150): {hi2_support:.2f}")
    
    return result
