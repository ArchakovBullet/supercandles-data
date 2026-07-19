"""
Агрессивность рынка для 1H на основе свечного анализа + FutOI.
Показывает общую агрессивность и по группам (физики/юрики).
"""

import pandas as pd
import numpy as np


def calculate_aggression_1h(df_h1, df_1h_ticker=None):
    """
    Рассчитывает агрессивность на основе H1-свечей и FutOI 1H.
    
    Returns:
    - score: 0-100 общая агрессивность
    - level: низкая/средняя/высокая
    - direction: покупатели/продавцы (рыночная)
    - fiz_aggression: кто агрессивнее из физиков (покупают/продают) + сила
    - yur_aggression: кто агрессивнее из юриков + сила
    """
    result = {
        'score': 0, 'level': 'Нет данных', 'direction': '—',
        'fiz_direction': '—', 'fiz_strength': 0,
        'yur_direction': '—', 'yur_strength': 0,
    }
    
    if df_h1 is None or len(df_h1) < 5:
        return result
    
    recent = df_h1.tail(5)
    last = recent.iloc[-1]
    
    # === 1. Рыночная агрессивность (свечной анализ) ===
    avg_range_pct = ((recent['high'] - recent['low']) / recent['close'] * 100).mean()
    range_score = min(avg_range_pct * 20, 30)
    
    candle_range = last['high'] - last['low']
    if candle_range > 0:
        close_pos = (last['close'] - last['low']) / candle_range
        if close_pos > 0.8:
            direction = 'Покупатели'
            pos_score = 25
        elif close_pos < 0.2:
            direction = 'Продавцы'
            pos_score = 25
        else:
            direction = 'Нейтрально'
            pos_score = 10
    else:
        direction = '—'
        pos_score = 0
    
    avg_vol = recent['volume'].mean()
    last_vol = last['volume']
    vol_score = min(last_vol / avg_vol * 15, 25) if avg_vol > 0 else 0
    
    prev_close = recent.iloc[-2]['close'] if len(recent) >= 2 else last['open']
    price_change = (last['close'] - prev_close) / prev_close * 100
    mom_score = min(abs(price_change) * 10, 20)
    
    total_score = range_score + pos_score + vol_score + mom_score
    
    if total_score > 60:
        level = 'Высокая'
    elif total_score > 35:
        level = 'Средняя'
    else:
        level = 'Низкая'
    
    result['score'] = round(total_score)
    result['level'] = level
    result['direction'] = direction
    
    # === 2. Агрессивность по группам (FutOI 1H) ===
    if df_1h_ticker is not None and len(df_1h_ticker) >= 3:
        df_futoi = df_1h_ticker.tail(3)
        
        # Физики: изменение fiz_buy_ratio
        if 'fiz_buy_ratio' in df_futoi.columns:
            fiz_delta = df_futoi['fiz_buy_ratio'].iloc[-1] - df_futoi['fiz_buy_ratio'].iloc[0]
            if fiz_delta > 0.5:
                result['fiz_direction'] = 'Покупают'
                result['fiz_strength'] = round(min(abs(fiz_delta) * 20, 100))
            elif fiz_delta < -0.5:
                result['fiz_direction'] = 'Продают'
                result['fiz_strength'] = round(min(abs(fiz_delta) * 20, 100))
            else:
                result['fiz_direction'] = 'Нейтрально'
                result['fiz_strength'] = 0
        
        # Юрики: изменение yur_buy_ratio
        if 'yur_buy_ratio' in df_futoi.columns:
            yur_delta = df_futoi['yur_buy_ratio'].iloc[-1] - df_futoi['yur_buy_ratio'].iloc[0]
            if yur_delta > 0.5:
                result['yur_direction'] = 'Покупают'
                result['yur_strength'] = round(min(abs(yur_delta) * 20, 100))
            elif yur_delta < -0.5:
                result['yur_direction'] = 'Продают'
                result['yur_strength'] = round(min(abs(yur_delta) * 20, 100))
            else:
                result['yur_direction'] = 'Нейтрально'
                result['yur_strength'] = 0
    
    return result
