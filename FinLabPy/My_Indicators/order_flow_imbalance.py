"""
Order Flow Imbalance — дисбаланс потока ордеров.
Работает с TradeStats или Super Candles (нужны vol_b, vol_s, trades_b, trades_s).
"""

import pandas as pd
import numpy as np


def calculate_ofi(df, price_col='pr_close'):
    """
    Рассчитывает Order Flow Imbalance.
    
    Принимает DataFrame с колонками: vol_b, vol_s (обязательно), trades_b, trades_s (опционально), price_col.
    """
    if df is None or len(df) < 5:
        return {'ofi': 0, 'pressure': 'Нет данных', 'divergence': False}
    
    recent = df.tail(5)
    
    # OFI по объёму
    total_vol = recent['vol_b'] + recent['vol_s']
    ofi_vol = ((recent['vol_b'] - recent['vol_s']) / total_vol.replace(0, 1)).mean()
    
    # Давление
    if ofi_vol > 0.1:
        pressure = 'Покупатели'
    elif ofi_vol < -0.1:
        pressure = 'Продавцы'
    else:
        pressure = 'Нейтрально'
    
    # Дивергенция
    last = recent.iloc[-1]
    prev = recent.iloc[0]
    if price_col in recent.columns and prev[price_col] > 0:
        price_change = (last[price_col] - prev[price_col]) / prev[price_col]
        divergence = (price_change > 0.005 and ofi_vol < -0.05) or (price_change < -0.005 and ofi_vol > 0.05)
    else:
        divergence = False
    
    return {
        'ofi': round(ofi_vol, 3),
        'pressure': pressure,
        'divergence': divergence,
    }
