"""
Cumulative Delta — накопленная разница покупок/продаж.
Работает с TradeStats или Super Candles (нужны vol_b, vol_s, дата, цена).
"""

import pandas as pd
import numpy as np


def calculate_cumulative_delta(df, date_col='tradedate', price_col='pr_close'):
    """
    Рассчитывает кумулятивную дельту.
    
    Принимает DataFrame с колонками: vol_b, vol_s, date_col, price_col.
    """
    if df is None or len(df) < 5:
        return {'cum_delta': 0, 'delta_trend': '—', 'divergence': False, 'last_delta': 0}
    
    # Агрегируем по дням
    df['_date'] = pd.to_datetime(df[date_col])
    daily = df.groupby('_date').agg(
        vol_b=('vol_b', 'sum'),
        vol_s=('vol_s', 'sum'),
        pr_close=(price_col, 'last')
    ).reset_index()
    
    daily['delta'] = daily['vol_b'] - daily['vol_s']
    daily['cum_delta'] = daily['delta'].cumsum()
    
    last = daily.iloc[-1]
    prev_5d = daily.iloc[-5] if len(daily) >= 5 else daily.iloc[0]
    
    delta_trend = "растёт" if last['cum_delta'] > prev_5d['cum_delta'] else "падает"
    
    # Дивергенция
    if prev_5d['pr_close'] > 0:
        price_change = (last['pr_close'] - prev_5d['pr_close']) / prev_5d['pr_close']
        delta_change = last['cum_delta'] - prev_5d['cum_delta']
        divergence = (price_change > 0.01 and delta_change < 0) or (price_change < -0.01 and delta_change > 0)
    else:
        divergence = False
    
    return {
        'cum_delta': round(last['cum_delta'], 0),
        'delta_trend': delta_trend,
        'divergence': divergence,
        'last_delta': round(last['delta'], 0),
    }
