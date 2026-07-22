"""
Парная торговля: расчёт спреда, Z-score, Spread Volatility, сигналов.
"""

import pandas as pd
import numpy as np


def calculate_spread(price_a, price_b, beta=None, log_spread=True):
    """Рассчитывает спред между двумя активами.
    log_spread=True — логарифмический спред (рекомендуется для парной торговли)."""
    if log_spread:
        log_a = np.log(price_a)
        log_b = np.log(price_b)
        if beta is None:
            beta = np.mean(log_a) / np.mean(log_b) if np.mean(log_b) != 0 else 1
        spread = log_a - beta * log_b
    else:
        if beta is None:
            beta = np.mean(price_a) / np.mean(price_b) if np.mean(price_b) != 0 else 1
        spread = price_a - beta * price_b
    return spread, beta


def calculate_zscore(spread, window=20):
    """Z-score спреда (отклонение от среднего в сигмах)."""
    mean = spread.rolling(window).mean()
    std = spread.rolling(window).std()
    zscore = (spread - mean) / std
    return zscore


def calculate_half_life(spread):
    """Период полураспада спреда (скорость возврата к среднему)."""
    spread_lag = spread.shift(1)
    spread_diff = spread - spread_lag
    spread_lag = spread_lag.iloc[1:]
    spread_diff = spread_diff.iloc[1:]
    
    if len(spread_lag) < 2:
        return 0
    
    # OLS: spread_diff = alpha + beta * spread_lag
    beta = np.cov(spread_diff, spread_lag)[0, 1] / np.var(spread_lag)
    
    if beta >= 0:
        return 0  # Нет возврата к среднему
    
    half_life = -np.log(2) / beta
    return round(half_life, 1)


def calculate_spread_volatility(spread, window=20):
    """Волатильность спреда."""
    return spread.diff().rolling(window).std().iloc[-1]


def analyze_pair(df_a, df_b, price_col='close', window=20):
    """
    Полный анализ пары.
    
    Возвращает:
    - spread: последнее значение спреда
    - zscore: текущий Z-score
    - correlation: корреляция
    - half_life: период полураспада
    - spread_vol: волатильность спреда
    - signal: LONG_SPREAD / SHORT_SPREAD / NEUTRAL
    - action: рекомендация
    """
    if df_a is None or df_b is None:
        return None
    
    # Выравниваем по датам
    if 'begin' in df_a.columns:
        df_a['date'] = pd.to_datetime(df_a['begin'])
    if 'begin' in df_b.columns:
        df_b['date'] = pd.to_datetime(df_b['begin'])
    
    merged = pd.merge(
        df_a[['date', price_col]].rename(columns={price_col: 'price_a'}),
        df_b[['date', price_col]].rename(columns={price_col: 'price_b'}),
        on='date', how='inner'
    ).dropna()
    
    if len(merged) < window:
        return None
    
    # Спред (логарифмический — правильнее для парной торговли)
    spread, beta = calculate_spread(merged['price_a'], merged['price_b'], log_spread=True)
    
    # Z-score
    zscore = calculate_zscore(spread, window)
    
    # Half-life
    half_life = calculate_half_life(spread)
    
    # Корреляция
    correlation = merged['price_a'].corr(merged['price_b'])
    
    # Волатильность спреда
    spread_vol = calculate_spread_volatility(spread, window)
    
    # Текущие значения
    current_spread = spread.iloc[-1]
    current_zscore = zscore.iloc[-1]
    
    # Сигнал
    if current_zscore > 2:
        signal = "SHORT_SPREAD"
        action = f"Z={current_zscore:.1f} > 2 → Шорт спреда (A переоценён)"
    elif current_zscore < -2:
        signal = "LONG_SPREAD"
        action = f"Z={current_zscore:.1f} < -2 → Лонг спреда (A недооценён)"
    else:
        signal = "NEUTRAL"
        action = f"Z={current_zscore:.1f} в диапазоне [-2, 2] → Ждать"
    
    return {
        'spread': round(current_spread, 4),
        'zscore': round(current_zscore, 2),
        'correlation': round(correlation, 3),
        'half_life': half_life,
        'spread_vol': round(spread_vol, 4) if not np.isnan(spread_vol) else 0,
        'beta': round(beta, 4),
        'signal': signal,
        'action': action,
        'merged': merged,
        'spread_series': spread,
        'zscore_series': zscore,
    }
